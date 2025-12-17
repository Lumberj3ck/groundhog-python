from __future__ import annotations

import json
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from langchain_core.tools import StructuredTool

from .calendar import CalendarClient, CalendarError
from .notes import recent_notes


class ToolError(Exception):
    pass


class Tool:
    name: str
    description: str

    def parameters(self) -> Dict[str, Any]:
        raise NotImplementedError

    def call(self, input_data: str) -> str:
        raise NotImplementedError

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate a simple math expression. Supports +, -, *, /, %, and power (^)."

    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression, e.g., 2+2*5",
                }
            },
            "required": ["expression"],
        }

    def call(self, input_data: str) -> str:
        try:
            args = json.loads(input_data) if input_data else {}
            expr = args.get("expression") or input_data
        except json.JSONDecodeError:
            expr = input_data
        expr = str(expr).replace("^", "**")
        try:
            result = eval(expr, {"__builtins__": {}}, math.__dict__ | operator.__dict__)
        except Exception as exc:  # pylint: disable=broad-except
            raise ToolError(f"Could not evaluate expression: {exc}") from exc
        return str(result)


@dataclass
class NotesTool(Tool):
    notes_dir: str
    default_limit: int = 5

    @property
    def name(self) -> str:  # type: ignore[override]
        return "notes"

    @property
    def description(self) -> str:  # type: ignore[override]
        return (
            "Fetch the most recent dated notes from the notes directory. "
            "Pass `count` to control how many to return."
        )

    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "How many notes to fetch"},
            },
        }

    def call(self, input_data: str) -> str:
        count = self.default_limit
        if input_data:
            try:
                parsed = json.loads(input_data)
                maybe_count = parsed.get("count")
                if isinstance(maybe_count, int) and maybe_count > 0:
                    count = maybe_count
            except json.JSONDecodeError:
                try:
                    maybe_count = int(input_data.strip())
                    if maybe_count > 0:
                        count = maybe_count
                except ValueError:
                    pass
        return recent_notes(self.notes_dir, count)


@dataclass
class CalendarListTool(Tool):
    client_factory: Callable[[], Optional[CalendarClient]]

    @property
    def name(self) -> str:  # type: ignore[override]
        return "calendar"

    @property
    def description(self) -> str:  # type: ignore[override]
        return "List the user's upcoming Google Calendar events for the next 72 hours, including each event's id."

    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def call(self, input_data: str) -> str:
        client = self.client_factory()
        if not client:
            raise ToolError("Calendar is not configured")
        try:
            return client.list_upcoming()
        except CalendarError as exc:
            raise ToolError(str(exc)) from exc


@dataclass
class CalendarAddTool(Tool):
    client_factory: Callable[[], Optional[CalendarClient]]

    @property
    def name(self) -> str:  # type: ignore[override]
        return "calendar_add_event"

    @property
    def description(self) -> str:  # type: ignore[override]
        return (
            "Add a new event to Google Calendar. Provide JSON with summary, start_time,"
            " optional end_time or duration_minutes, description, location, and time_zone."
        )

    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "time_zone": {"type": "string"},
            },
            "required": ["summary", "start_time"],
        }

    def call(self, input_data: str) -> str:
        client = self.client_factory()
        if not client:
            raise ToolError("Calendar is not configured")
        try:
            return client.add_event(input_data)
        except CalendarError as exc:
            raise ToolError(str(exc)) from exc


@dataclass
class CalendarEditTool(Tool):
    client_factory: Callable[[], Optional[CalendarClient]]

    @property
    def name(self) -> str:  # type: ignore[override]
        return "calendar_edit_event"

    @property
    def description(self) -> str:  # type: ignore[override]
        return (
            "Edit an existing Google Calendar event. Provide event_id and any fields to update "
            "(summary, description, start_time, end_time, duration_minutes, time_zone, location)."
        )

    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "time_zone": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["event_id"],
        }

    def call(self, input_data: str) -> str:
        client = self.client_factory()
        if not client:
            raise ToolError("Calendar is not configured")
        try:
            return client.edit_event(input_data)
        except CalendarError as exc:
            raise ToolError(str(exc)) from exc


# ---- LangChain adapters ---------------------------------------------------- #


def _wrap_calculator(tool: CalculatorTool) -> StructuredTool:
    def _fn(expression: str) -> str:
        payload = json.dumps({"expression": expression})
        return tool.call(payload)

    return StructuredTool.from_function(
        _fn,
        name=tool.name,
        description=tool.description,
    )


def _wrap_notes(tool: NotesTool) -> StructuredTool:
    def _fn(count: Optional[int] = None) -> str:
        payload = json.dumps({"count": count}) if count else ""
        return tool.call(payload)

    return StructuredTool.from_function(
        _fn,
        name=tool.name,
        description=tool.description,
    )


def _wrap_calendar_list(tool: CalendarListTool) -> StructuredTool:
    def _fn() -> str:
        return tool.call("")

    return StructuredTool.from_function(
        _fn,
        name=tool.name,
        description=tool.description,
    )


def _wrap_calendar_add(tool: CalendarAddTool) -> StructuredTool:
    def _fn(
        summary: str,
        start_time: str,
        end_time: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        time_zone: Optional[str] = None,
    ) -> str:
        payload = json.dumps(
            {
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration_minutes,
                "description": description,
                "location": location,
                "time_zone": time_zone,
            }
        )
        return tool.call(payload)

    return StructuredTool.from_function(
        _fn,
        name=tool.name,
        description=tool.description,
    )


def _wrap_calendar_edit(tool: CalendarEditTool) -> StructuredTool:
    def _fn(
        event_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        time_zone: Optional[str] = None,
        location: Optional[str] = None,
    ) -> str:
        payload = json.dumps(
            {
                "event_id": event_id,
                "summary": summary,
                "description": description,
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration_minutes,
                "time_zone": time_zone,
                "location": location,
            }
        )
        return tool.call(payload)

    return StructuredTool.from_function(
        _fn,
        name=tool.name,
        description=tool.description,
    )


def as_langchain_tools(tools: list[Tool]) -> list[StructuredTool]:
    wrapped: list[StructuredTool] = []
    for tool in tools:
        if isinstance(tool, CalculatorTool):
            wrapped.append(_wrap_calculator(tool))
        elif isinstance(tool, NotesTool):
            wrapped.append(_wrap_notes(tool))
        elif isinstance(tool, CalendarListTool):
            wrapped.append(_wrap_calendar_list(tool))
        elif isinstance(tool, CalendarAddTool):
            wrapped.append(_wrap_calendar_add(tool))
        elif isinstance(tool, CalendarEditTool):
            wrapped.append(_wrap_calendar_edit(tool))
    return wrapped


