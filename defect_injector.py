"""Defect injection module for the Simple Library Manager MCP server.

Reads the INJECT_MCP_DEFECT environment variable and mutates outgoing
JSON-RPC message dictionaries (or replaces them entirely) to simulate
protocol-level failures for resilience testing.
"""

import os


def apply_defect(message: dict) -> dict | str:
    """Apply a defect to an outgoing JSON-RPC message based on an env var.

    Args:
        message: The JSON-RPC message as a plain dictionary.

    Returns:
        The (possibly mutated) dictionary, or a raw string for the
        ``garbage_data`` mode that deliberately breaks JSON parsing.
    """
    defect = os.environ.get("INJECT_MCP_DEFECT", "").strip()

    if not defect:
        return message

    if defect == "missing_id":
        message.pop("id", None)
        return message

    if defect == "invalid_version":
        message["jsonrpc"] = "1.0"
        return message

    if defect == "artificial_error":
        message.pop("result", None)
        message["error"] = {
            "code": -32000,
            "message": "Injected artificial error for testing purposes",
        }
        return message

    if defect == "garbage_data":
        return "{bad_json: true, ]"

    return message
