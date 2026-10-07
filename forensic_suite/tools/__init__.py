"""External forensic tool wrappers (PhoneInfoga, ALEAPP, ExifTool, ...)."""
from __future__ import annotations

from .base import ForensicTool, ToolResult
from .phoneinfoga import PhoneInfoga
from .aleapp import ALEAPP

TOOL_REGISTRY: dict[str, type[ForensicTool]] = {
    PhoneInfoga.name: PhoneInfoga,
    ALEAPP.name: ALEAPP,
}


def available_tools() -> list[type[ForensicTool]]:
    return list(TOOL_REGISTRY.values())


def get_tool(name: str) -> type[ForensicTool] | None:
    return TOOL_REGISTRY.get(name)


__all__ = ["ForensicTool", "ToolResult", "PhoneInfoga", "ALEAPP",
           "TOOL_REGISTRY", "available_tools", "get_tool"]