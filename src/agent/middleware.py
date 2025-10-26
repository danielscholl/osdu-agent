"""Agent middleware for logging and context injection.

This module provides middleware functions that intercept agent interactions
with tools and LLMs, enabling logging, metrics, and context injection.
"""

import logging
import time
from typing import Awaitable, Callable

from agent_framework import (
    AgentRunContext,
    ChatContext,
    FunctionInvocationContext,
    chat_middleware,
    function_middleware,
)

from agent.observability import record_tool_call, tracer

logger = logging.getLogger(__name__)


@function_middleware  # Explicitly mark as function middleware (per docs)
async def logging_function_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Function middleware that logs and traces tool execution.

    This middleware intercepts all tool calls (GitHub tools and Maven MCP tools)
    and provides:
    - Structured logging of tool name and arguments
    - OpenTelemetry tracing for observability
    - Execution duration metrics
    - Error tracking
    - Real-time activity updates for console display

    Args:
        context: Function invocation context containing tool name, arguments, and result
        next: Next middleware or the actual function execution
    """
    # Import activity tracker
    from agent.activity import get_activity_tracker

    # Pre-processing: Log before function execution
    tool_name = (
        context.function.name if hasattr(context.function, "name") else str(context.function)
    )

    logger.info(f"[Tool Call] {tool_name}")

    # Update console activity tracker
    activity_tracker = get_activity_tracker()
    formatted_name = activity_tracker.format_tool_name(tool_name)
    await activity_tracker.update(f"🔧 {formatted_name}...")

    # Emit tool start event (if in interactive mode)
    arguments = context.arguments if hasattr(context, "arguments") else None
    # Convert BaseModel to dict if needed
    arguments_dict = arguments.dict() if hasattr(arguments, "dict") else arguments  # type: ignore[union-attr]
    activity_tracker.emit_tool_start(tool_name, arguments_dict)  # type: ignore[arg-type]

    # Log arguments at debug level (can be verbose)
    if hasattr(context, "arguments") and context.arguments:
        logger.debug(f"[Tool Args] {context.arguments}")

    # Start OpenTelemetry span for tracing
    with tracer.start_as_current_span("tool_call") as span:
        span.set_attribute("tool.name", tool_name)

        # Add arguments as span attributes (sanitized)
        if hasattr(context, "arguments") and context.arguments:
            # Convert BaseModel to dict if needed, otherwise ensure it's a dict
            args_as_dict = (
                context.arguments.dict()
                if hasattr(context.arguments, "dict")
                else (context.arguments if isinstance(context.arguments, dict) else {})
            )
            # Only add non-sensitive arguments
            safe_args = {
                k: v for k, v in args_as_dict.items() if k not in ["token", "api_key", "password", "secret"]
            }
            if safe_args:
                span.set_attribute("tool.arguments", str(safe_args))

        start_time = time.time()
        status = "success"

        try:
            # Continue to next middleware or function execution
            await next(context)

            # Update activity tracker on success
            await activity_tracker.update(f"✓ {formatted_name}")

            # Emit tool complete event with result summary
            duration = time.time() - start_time
            result = context.result if hasattr(context, "result") else None

            # Format result summary
            from agent.display.result_formatter import format_tool_result

            result_summary = format_tool_result(tool_name, result)

            activity_tracker.emit_tool_complete(tool_name, result_summary, duration)

        except Exception as e:
            # Track errors
            status = "error"
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            logger.error(f"[Tool Error] {tool_name}: {str(e)}")

            # Update activity tracker on error
            await activity_tracker.update(f"✗ {formatted_name} failed")

            # Emit tool error event
            duration = time.time() - start_time
            activity_tracker.emit_tool_error(tool_name, str(e), duration)

            raise

        finally:
            # Post-processing: Log after function execution
            duration = time.time() - start_time
            span.set_attribute("tool.duration", duration)

            logger.info(f"[Tool Complete] {tool_name} ({duration:.2f}s)")

            # Log result at debug level
            if hasattr(context, "result") and context.result:
                result_preview = str(context.result)[:200]  # First 200 chars
                logger.debug(f"[Tool Result] {result_preview}...")

            # Record metrics
            record_tool_call(tool_name, duration, status)


@chat_middleware  # Explicitly mark as chat middleware (per docs)
async def logging_chat_middleware(
    context: ChatContext,
    next: Callable[[ChatContext], Awaitable[None]],
) -> None:
    """Chat middleware that logs and traces LLM interactions.

    This middleware intercepts all agent-to-LLM communications and provides:
    - Structured logging of message counts
    - OpenTelemetry tracing
    - Request/response logging at debug level
    - Real-time activity updates for console display

    Args:
        context: Chat context containing messages and model configuration
        next: Next middleware or the actual LLM service call
    """
    # Import activity tracker
    from agent.activity import get_activity_tracker

    # Pre-processing: Log before AI call
    message_count = len(context.messages) if hasattr(context, "messages") else 0
    logger.info(f"[LLM Request] {message_count} messages")

    # Update console activity tracker
    activity_tracker = get_activity_tracker()
    await activity_tracker.update("🤖 Thinking with AI...")

    # Emit LLM request event (if in interactive mode)
    from agent.display import LLMRequestEvent, get_event_emitter, is_interactive_mode

    llm_event_id = None
    if is_interactive_mode():
        event = LLMRequestEvent(message_count=message_count)
        llm_event_id = event.event_id
        emitter = get_event_emitter()
        emitter.emit(event)

    # Log last message at debug level (usually the user query)
    if hasattr(context, "messages") and context.messages:
        last_message = context.messages[-1]
        if isinstance(last_message, dict) and "content" in last_message:
            content_preview = str(last_message["content"])[:200]  # First 200 chars
            logger.debug(f"[LLM Query] {content_preview}...")

    # Start OpenTelemetry span for tracing
    with tracer.start_as_current_span("llm_call") as span:
        span.set_attribute("llm.message_count", message_count)

        # Add model info if available
        if hasattr(context, "model"):
            span.set_attribute("llm.model", context.model)

        start_time = time.time()

        try:
            # Continue to next middleware or AI service
            await next(context)

            # Post-processing: Log after AI response
            duration = time.time() - start_time
            span.set_attribute("llm.duration", duration)

            logger.info(f"[LLM Response] Received ({duration:.2f}s)")

            # Update activity tracker on success
            await activity_tracker.update("✓ AI response received")

            # Emit LLM response event (if in interactive mode)
            from agent.display import LLMResponseEvent, get_event_emitter, is_interactive_mode

            if is_interactive_mode() and llm_event_id:
                response_event = LLMResponseEvent(duration=duration)
                response_event.event_id = llm_event_id
                emitter = get_event_emitter()
                emitter.emit(response_event)

            # Log response at debug level
            if hasattr(context, "response") and context.response:
                response_preview = str(context.response)[:200]  # First 200 chars
                logger.debug(f"[LLM Response Content] {response_preview}...")

        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            logger.error(f"[LLM Error] {str(e)}")
            raise


async def workflow_context_agent_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Agent middleware that injects workflow context before agent execution.

    This middleware intercepts EVERY agent.run() call and automatically adds
    context from recent workflow executions (slash commands) to the messages.
    This enables the agent to reference detailed workflow results when
    answering follow-up questions.

    Args:
        context: Agent run context containing messages, agent, and metadata
        next: Next middleware or the actual agent execution

    Example:
        User executes /vulns partition, then asks "What CVEs did you find?"
        The middleware injects vulns results before agent execution, allowing
        the agent to answer with specific CVE details.
    """
    # Import here to avoid circular dependency
    from agent.workflows import get_result_store

    # Get recent workflow results
    result_store = get_result_store()
    context_summary = await result_store.get_context_summary(limit=3)

    logger.debug(f"[Context Retrieval] Found {len(context_summary)} chars of workflow context")

    if context_summary and hasattr(context, "messages") and context.messages:
        # Enhanced context with explicit instruction to use the data
        enhanced_context = f"""{context_summary}

**IMPORTANT INSTRUCTION:**
When the user asks about recent workflow results (tests, vulns, status, fork),
YOU MUST reference the workflow results shown above. DO NOT call GitHub tools
to fetch information that is already available in these results.

For example:
- "what was the grade?" → Reference the Grade from Test Results above
- "what CVEs did you find?" → Reference the Vulnerabilities from vulnerability scan results above
- "how many tests passed?" → Reference the Test Results above

Always check this context FIRST before calling any tools."""

        # Create a user message with the workflow context
        # Insert it right before the current user query
        from agent_framework import ChatMessage, Role

        context_message = ChatMessage(role=Role.SYSTEM, text=enhanced_context)

        # Insert before the last message (current user query)
        context.messages.insert(-1, context_message)

        logger.info(f"[Context Injection] Injected workflow context ({len(context_summary)} chars)")
    else:
        logger.debug(
            f"[Context Injection] No workflow results to inject "
            f"(has {len(context.messages) if hasattr(context, 'messages') else 0} messages)"
        )

    # Continue to next middleware or agent execution
    await next(context)
