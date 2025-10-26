"""Constants for OSDU services."""

# Service definitions for OSDU services
SERVICES = {
    "partition": "Partition Service",
    "entitlements": "Entitlements Service",
    "legal": "Legal Service",
    "schema": "Schema Service",
    "file": "File Service",
    "storage": "Storage Service",
    "indexer": "Indexer Service",
    "indexer-queue": "Indexer Queue Service",
    "search": "Search Service",
    "workflow": "Workflow Service",
}

# Centralized icon definitions for status display
# Used across all trackers for consistent visual language
STATUS_ICONS = {
    "pending": "⏸",
    "running": "▶",
    "querying": "▶",
    "compiling": "▶",
    "testing": "▶",
    "coverage": "▶",
    "assessing": "▶",
    "analyzing": "▶",
    "scanning": "▶",
    "reporting": "▶",
    "waiting": "||",
    "success": "✓",
    "complete": "✓",
    "gathered": "✓",
    "compile_success": "✓",
    "test_success": "✓",
    "error": "✗",
    "compile_failed": "✗",
    "test_failed": "✗",
    "skipped": "⊘",
}
