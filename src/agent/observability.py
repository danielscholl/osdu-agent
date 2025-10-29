"""Observability module for OSDU Agent using OpenTelemetry.

This module provides tracing and metrics capabilities through Microsoft Agent Framework's
OpenTelemetry integration, enabling monitoring via Azure AI Foundry dashboards.
"""

import logging
import os
import subprocess
from contextvars import ContextVar
from typing import TYPE_CHECKING, Dict, Optional

from agent_framework.observability import get_meter, get_tracer, setup_observability

if TYPE_CHECKING:
    from opentelemetry import trace

logger = logging.getLogger(__name__)

# Suppress Azure Monitor statsbeat re-initialization warnings
# These are harmless and occur due to parallel MCP initialization
logging.getLogger("azure.monitor.opentelemetry.exporter.statsbeat._manager").setLevel(logging.ERROR)

# Set default service name for OpenTelemetry if not already configured
os.environ.setdefault("OTEL_SERVICE_NAME", "osdu-agent")

# Context variables for user/session tracking across async contexts
_user_session_context: ContextVar[Dict[str, str]] = ContextVar("user_session_context", default={})

# Track if observability has been initialized (for idempotency)
_observability_initialized = False


async def fetch_app_insights_from_workspace(
    subscription_id: str, resource_group: str, workspace_name: str
) -> Optional[str]:
    """
    Fetch Application Insights connection string from Azure ML workspace using REST API.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Resource group containing the workspace
        workspace_name: Machine Learning workspace name

    Returns:
        Application Insights connection string if successful, None otherwise
    """
    try:
        # Step 1: Get the Application Insights resource ID from the workspace
        workspace_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.MachineLearningServices/workspaces/{workspace_name}"
            f"?api-version=2023-04-01"
        )

        result = subprocess.run(
            [
                "az",
                "rest",
                "--method",
                "get",
                "--url",
                workspace_url,
                "--query",
                "properties.applicationInsights",
                "--output",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"Failed to get workspace details: {result.stderr}")
            return None

        app_insights_resource_id = result.stdout.strip()
        if not app_insights_resource_id:
            logger.warning("No Application Insights resource linked to workspace")
            return None

        # Parse the resource ID to get resource group and app insights name
        # Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/microsoft.insights/components/{name}
        parts = app_insights_resource_id.split("/")
        if len(parts) < 9:
            logger.warning(
                f"Invalid Application Insights resource ID format: {app_insights_resource_id}"
            )
            return None

        app_insights_rg = parts[4]
        app_insights_name = parts[-1]

        logger.info(f"Found Application Insights: {app_insights_name} in {app_insights_rg}")

        # Step 2: Get the connection string from Application Insights
        result = subprocess.run(
            [
                "az",
                "monitor",
                "app-insights",
                "component",
                "show",
                "--app",
                app_insights_name,
                "--resource-group",
                app_insights_rg,
                "--query",
                "connectionString",
                "--output",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"Failed to get App Insights connection string: {result.stderr}")
            return None

        connection_string = result.stdout.strip()
        if connection_string:
            logger.info("✓ Successfully fetched Application Insights connection string from Azure")
            return connection_string

        return None

    except subprocess.TimeoutExpired:
        logger.debug(
            "Azure Management API call timed out while fetching App Insights connection string. "
            "To skip auto-discovery, set APPLICATIONINSIGHTS_CONNECTION_STRING directly."
        )
        return None
    except Exception as e:
        logger.warning(f"Error fetching App Insights connection string: {e}")
        return None


async def setup_azure_ai_foundry_observability() -> Optional[str]:
    """
    Auto-configure observability from Azure AI Foundry/ML workspace.

    Fetches Application Insights connection string from the Azure ML workspace
    without requiring users to manually configure it.

    Supports two input methods:
    1. AZURE_AI_PROJECT_ENDPOINT (extracts workspace details from endpoint URL)
    2. AZURE_AI_PROJECT_CONNECTION_STRING (explicit workspace coordinates)

    Returns:
        Application Insights connection string if successful, None otherwise

    Environment Variables:
        AZURE_AI_PROJECT_ENDPOINT: https://<workspace>.<region>.api.azureml.ms
        AZURE_AI_PROJECT_CONNECTION_STRING: <region>.api.azureml.ms;<sub-id>;<rg>;<workspace>
    """
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    connection_string_config = os.getenv("AZURE_AI_PROJECT_CONNECTION_STRING")

    workspace_name = None
    resource_group = None
    subscription_id = None

    # Try to parse from connection string first (most explicit)
    if connection_string_config:
        parts = connection_string_config.split(";")
        if len(parts) >= 4:
            # Format: <region>.api.azureml.ms;<subscription-id>;<resource-group>;<workspace-name>
            subscription_id = parts[1]
            resource_group = parts[2]
            workspace_name = parts[3]
            logger.info(f"Using workspace from connection string: {workspace_name}")

    # If not from connection string, try to parse from endpoint URL
    if not workspace_name and project_endpoint:
        # Format: https://<workspace>.<region>.api.azureml.ms
        # But this doesn't give us subscription/resource group, so we need to look it up
        logger.info("Trying to discover workspace from endpoint URL...")
        # For now, this is complex - require connection string format
        logger.warning(
            "AZURE_AI_PROJECT_ENDPOINT alone is not sufficient. "
            "Please use AZURE_AI_PROJECT_CONNECTION_STRING format: "
            "<region>.api.azureml.ms;<subscription-id>;<resource-group>;<workspace-name>"
        )
        return None

    if not all([subscription_id, resource_group, workspace_name]):
        logger.debug("Azure AI Foundry observability: insufficient configuration")
        return None

    # Type narrowing: all() check ensures these are not None
    assert subscription_id is not None
    assert resource_group is not None
    assert workspace_name is not None

    # Fetch connection string from workspace
    connection_string = await fetch_app_insights_from_workspace(
        subscription_id, resource_group, workspace_name
    )

    if connection_string:
        # Now setup observability with the fetched connection string
        enable_sensitive_data = os.getenv("ENABLE_SENSITIVE_DATA", "false").lower() == "true"

        setup_observability(
            enable_sensitive_data=enable_sensitive_data,
            applicationinsights_connection_string=connection_string,
        )

        logger.info("✓ Azure AI Foundry observability configured successfully (auto-fetched)")
        return connection_string

    return None


def initialize_observability() -> bool:
    """
    Initialize OpenTelemetry observability with automatic Azure AI Foundry support.

    This function should be called early in the application lifecycle to enable tracing and metrics
    export to Azure Application Insights. It is idempotent and safe to call multiple times.

    Initialization Order:
    1. Try Azure AI Foundry auto-discovery (if AZURE_AI_PROJECT_ENDPOINT set)
    2. Fall back to APPLICATIONINSIGHTS_CONNECTION_STRING from environment
    3. Fall back to OTLP_ENDPOINT from environment

    Returns:
        True if observability was initialized, False otherwise

    Environment Variables:
        AZURE_AI_PROJECT_ENDPOINT: Azure AI Foundry project endpoint (auto-fetches connection string)
        APPLICATIONINSIGHTS_CONNECTION_STRING: Azure Application Insights connection string (fallback)
        ENABLE_SENSITIVE_DATA: Set to 'true' to log prompts, responses, and tool arguments (default: false)
        OTLP_ENDPOINT: Optional OTLP endpoint for additional exporters (e.g., http://localhost:4317)
    """
    global _observability_initialized

    # Return early if already initialized (idempotency)
    if _observability_initialized:
        logger.debug("Observability already initialized, skipping")
        return True

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")

    # Try Azure AI Foundry auto-discovery first (requires async)
    # We'll handle this separately in agent initialization since we can't use async here
    # For now, only use env vars

    # Only initialize if we have at least one exporter configured
    if not connection_string and not otlp_endpoint:
        if project_endpoint:
            logger.info(
                "Azure AI Foundry endpoint detected. Observability will be configured when agent starts."
            )
            return True  # Signal that observability will be set up later
        logger.debug(
            "Observability not initialized: APPLICATIONINSIGHTS_CONNECTION_STRING, "
            "OTLP_ENDPOINT, and AZURE_AI_PROJECT_ENDPOINT not set"
        )
        return False

    try:
        # Enable sensitive data logging if requested (default: False for security)
        enable_sensitive_data = os.getenv("ENABLE_SENSITIVE_DATA", "false").lower() == "true"

        # Setup observability with configured endpoints
        setup_observability(
            enable_sensitive_data=enable_sensitive_data,
            otlp_endpoint=otlp_endpoint,
            applicationinsights_connection_string=connection_string,
        )

        # Install custom span processor for user/session context injection
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        tracer_provider = trace.get_tracer_provider()
        if isinstance(tracer_provider, TracerProvider):
            processor = UserSessionSpanProcessor()
            tracer_provider.add_span_processor(processor)  # type: ignore[arg-type]
            logger.info("  User/session span processor installed")

        logger.info("OpenTelemetry observability initialized successfully")
        if connection_string:
            # Mask the instrumentation key for security
            masked_key = (
                connection_string.split(";")[0].replace("InstrumentationKey=", "***")
                if "InstrumentationKey=" in connection_string
                else "***"
            )
            logger.info(f"  Application Insights: {masked_key}")
        if otlp_endpoint:
            logger.info(f"  OTLP Endpoint: {otlp_endpoint}")
        if enable_sensitive_data:
            logger.warning(
                "  Sensitive data logging ENABLED - prompts and responses will be logged"
            )

        _observability_initialized = True
        return True

    except Exception as e:
        logger.error(f"Failed to initialize observability: {e}", exc_info=True)
        return False


class UserSessionSpanProcessor:
    """Span processor that injects user/session context into spans on start.

    Implements the SpanProcessor protocol for OpenTelemetry.
    """

    def on_start(
        self, span: "trace.Span", parent_context: Optional["trace.Context"] = None
    ) -> None:
        """Called when a span is started - inject user/session attributes.

        Args:
            span: The span that was started
            parent_context: Optional parent context
        """
        try:
            user_context = get_user_session_context()
            if user_context:
                for key, value in user_context.items():
                    if value is not None:
                        span.set_attribute(key, value)
        except Exception as e:
            logger.debug(f"Error injecting user context into span: {e}")

    def on_end(self, span: "trace.Span") -> None:
        """Called when a span ends - no-op.

        Args:
            span: The span that ended
        """
        pass

    def shutdown(self) -> None:
        """Called on shutdown - performs cleanup (no-op for this processor)."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Called to force flush - no-op for this processor.

        Args:
            timeout_millis: Timeout in milliseconds

        Returns:
            bool: Always returns True (no flushing needed)
        """
        return True


# Note: Observability initialization is deferred to CLI startup to allow
# auto-discovery from AZURE_AI_PROJECT_CONNECTION_STRING to complete first.
# See _setup_foundry_observability_if_needed() in cli.py

# Initialize OpenTelemetry tracer and meter
# These will use the configured exporters if observability was initialized
tracer = get_tracer()
meter = get_meter()

# Define metrics for monitoring agent operations

# Tool invocation metrics
tool_calls_counter = meter.create_counter(
    "agent.tool_calls.total",
    description="Total number of tool calls made by the agent",
)

tool_duration_histogram = meter.create_histogram(
    "agent.tool_calls.duration_seconds",
    description="Duration of tool calls in seconds",
)

# Workflow metrics
workflow_runs_counter = meter.create_counter(
    "agent.workflows.runs.total",
    description="Total number of workflow runs",
)

workflow_duration_histogram = meter.create_histogram(
    "agent.workflows.duration_seconds",
    description="Duration of workflow execution in seconds",
)

# Vulnerability analysis metrics
vulns_scans_counter = meter.create_counter(
    "agent.vulns.scans.total",
    description="Total number of vulnerability scans performed",
)

vulns_vulnerabilities_counter = meter.create_counter(
    "agent.vulns.vulnerabilities.total",
    description="Total vulnerabilities found by severity",
)

# Test-specific metrics
test_runs_counter = meter.create_counter(
    "agent.tests.runs.total",
    description="Total number of test runs",
)

test_results_counter = meter.create_counter(
    "agent.tests.results.total",
    description="Test results by status (passed/failed)",
)

# LLM interaction metrics
llm_calls_counter = meter.create_counter(
    "agent.llm.calls.total",
    description="Total number of LLM calls",
)

llm_tokens_counter = meter.create_counter(
    "agent.llm.tokens.total",
    description="Total tokens used (prompt + completion)",
)


def record_tool_call(tool_name: str, duration: float, status: str = "success") -> None:
    """Record a tool call metric.

    Args:
        tool_name: Name of the tool that was called
        duration: Duration of the tool call in seconds
        status: Status of the tool call (success/error)
    """
    tool_calls_counter.add(1, {"tool": tool_name, "status": status})
    tool_duration_histogram.record(duration, {"tool": tool_name})


def record_workflow_run(
    workflow_type: str, duration: float, status: str = "success", service_count: int = 1
) -> None:
    """Record a workflow run metric.

    Args:
        workflow_type: Type of workflow (vulns, test, status, fork)
        duration: Duration of the workflow in seconds
        status: Status of the workflow (success/error)
        service_count: Number of services processed
    """
    workflow_runs_counter.add(
        1, {"workflow": workflow_type, "status": status, "services": service_count}
    )
    workflow_duration_histogram.record(duration, {"workflow": workflow_type})


def record_vulns_scan(
    service: str,
    critical: int,
    high: int,
    medium: int,
    low: int = 0,
    status: str = "success",
) -> None:
    """Record vulnerability scan metrics.

    Args:
        service: Service that was scanned
        critical: Number of critical vulnerabilities
        high: Number of high vulnerabilities
        medium: Number of medium vulnerabilities
        low: Number of low vulnerabilities
        status: Status of the scan (success/error)
    """
    vulns_scans_counter.add(1, {"service": service, "status": status})

    # Record vulnerability counts by severity
    if critical > 0:
        vulns_vulnerabilities_counter.add(critical, {"severity": "critical", "service": service})
    if high > 0:
        vulns_vulnerabilities_counter.add(high, {"severity": "high", "service": service})
    if medium > 0:
        vulns_vulnerabilities_counter.add(medium, {"severity": "medium", "service": service})
    if low > 0:
        vulns_vulnerabilities_counter.add(low, {"severity": "low", "service": service})


def record_test_run(
    service: str, passed: int, failed: int, skipped: int = 0, status: str = "success"
) -> None:
    """Record test run metrics.

    Args:
        service: Service that was tested
        passed: Number of tests that passed
        failed: Number of tests that failed
        skipped: Number of tests that were skipped
        status: Overall test run status (success/error)
    """
    test_runs_counter.add(1, {"service": service, "status": status})

    # Record test results by status
    if passed > 0:
        test_results_counter.add(passed, {"result": "passed", "service": service})
    if failed > 0:
        test_results_counter.add(failed, {"result": "failed", "service": service})
    if skipped > 0:
        test_results_counter.add(skipped, {"result": "skipped", "service": service})


def record_llm_call(
    model: str, prompt_tokens: int, completion_tokens: int, duration: Optional[float] = None
) -> None:
    """Record LLM interaction metrics.

    Args:
        model: Model name used for the call
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens generated
        duration: Duration of the LLM call in seconds (optional)
    """
    llm_calls_counter.add(1, {"model": model})
    llm_tokens_counter.add(prompt_tokens, {"type": "prompt", "model": model})
    llm_tokens_counter.add(completion_tokens, {"type": "completion", "model": model})


def set_user_context(user_id: Optional[str] = None, user_email: Optional[str] = None) -> None:
    """
    Set user context for current trace to identify who is running the agent.

    This adds user identification attributes to the current span, making it easy to
    filter and analyze traces by user in Application Insights.

    Args:
        user_id: User identifier (e.g., username, employee ID)
        user_email: User email address

    Example:
        >>> from agent.observability import set_user_context
        >>> set_user_context(user_id="john.doe", user_email="john.doe@example.com")

    In Application Insights:
        - Filter by custom property: `user.id = "john.doe"`
        - Query: `traces | where customDimensions.user_id == "john.doe"`
    """
    # Store in contextvar for later retrieval in middleware
    context = _user_session_context.get().copy()
    if user_id:
        context["user.id"] = user_id
    if user_email:
        context["user.email"] = user_email
    _user_session_context.set(context)

    # Also set on current span if available
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        if user_id:
            span.set_attribute("user.id", user_id)
        if user_email:
            span.set_attribute("user.email", user_email)


def set_session_context(session_id: str, thread_id: Optional[str] = None) -> None:
    """
    Set session context for current trace to track conversation threads.

    This adds session/thread identification to traces, allowing you to:
    - Group all queries from the same interactive session
    - Track conversation flow across multiple agent invocations
    - Analyze session duration and interaction patterns

    Args:
        session_id: Unique session identifier (e.g., UUID, timestamp-based ID)
        thread_id: Optional thread ID from agent framework for conversation tracking

    Example:
        >>> from agent.observability import set_session_context
        >>> import uuid
        >>> session_id = str(uuid.uuid4())
        >>> set_session_context(session_id=session_id, thread_id="thread_abc123")

    In Application Insights:
        - Filter by custom property: `session.id = "xyz"`
        - Query: `traces | where customDimensions.session_id == "xyz" | order by timestamp asc`
        - Analyze: See all operations in a conversation thread
    """
    # Store in contextvar for later retrieval in middleware
    context = _user_session_context.get().copy()
    context["session.id"] = session_id
    if thread_id:
        context["session.thread_id"] = thread_id
    _user_session_context.set(context)

    # Also set on current span if available
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("session.id", session_id)
        if thread_id:
            span.set_attribute("session.thread_id", thread_id)


def set_custom_attributes(**attributes: str) -> None:
    """
    Set custom attributes on the current span for flexible trace tagging.

    Allows adding arbitrary key-value pairs to traces for custom filtering and analysis.

    Args:
        **attributes: Key-value pairs to add as span attributes

    Example:
        >>> from agent.observability import set_custom_attributes
        >>> set_custom_attributes(
        ...     environment="production",
        ...     organization="danielscholl-osdu",
        ...     workflow_type="vulnerability_scan"
        ... )

    In Application Insights:
        - Filter by: `customDimensions.environment == "production"`
        - Group by custom dimensions in charts
    """
    # Store in contextvar for later retrieval in middleware
    context = _user_session_context.get().copy()
    context.update(attributes)
    _user_session_context.set(context)

    # Also set on current span if available
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def get_user_session_context() -> Dict[str, str]:
    """
    Retrieve the current user/session context.

    Returns:
        Dictionary of context attributes (user.id, session.id, etc.)

    This is used internally by middleware to inject context into agent spans.
    """
    return _user_session_context.get()


def get_observability_status() -> Dict[str, bool]:
    """
    Get the current observability configuration status.

    Returns:
        Dictionary with status information:
        - configured: Whether observability is configured (any exporter available)
        - app_insights: Whether Application Insights is configured
        - otlp: Whether OTLP endpoint is configured
        - initialized: Whether observability has been initialized

    Example:
        >>> from agent.observability import get_observability_status
        >>> status = get_observability_status()
        >>> if status["configured"]:
        ...     print("Observability is active")
    """
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")

    return {
        "configured": bool(connection_string or otlp_endpoint),
        "app_insights": bool(connection_string),
        "otlp": bool(otlp_endpoint),
        "initialized": _observability_initialized,
    }


def is_observability_active() -> bool:
    """
    Check if observability is currently active and sending telemetry.

    This is a convenience function that checks both configuration and initialization
    status. Observability is considered active only when:
    1. At least one exporter is configured (App Insights or OTLP)
    2. Observability has been successfully initialized

    Returns:
        bool: True if observability is active, False otherwise

    Example:
        >>> from agent.observability import is_observability_active
        >>> if is_observability_active():
        ...     print("Telemetry is being collected")
    """
    status = get_observability_status()
    return status["configured"] and status["initialized"]
