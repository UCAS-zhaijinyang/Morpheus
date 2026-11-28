"""Select employee activity records or complete employee-to-Agent traces."""

from __future__ import annotations

from typing import Any, Mapping


RECORDING_LEVELS = ("employee", "full")

def project_trace(trace: Mapping[str, Any], recording: str = "full") -> dict[str, Any]:
    """Format a completed activity for serialization without modifying it."""
    if recording == "full":
        return {**trace, "recording": "full"}
    if recording != "employee":
        raise ValueError(f"recording must be one of {RECORDING_LEVELS}")

    return {
        "schema_version": "morpheus.employee_trace.v1",
        "recording": "employee",
        "trace_id": trace["trace_id"],
        "employee": trace["employee"],
    }
