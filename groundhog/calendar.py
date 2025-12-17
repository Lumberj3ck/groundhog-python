from __future__ import annotations

import datetime as dt
import json
from typing import Dict, Optional, Tuple

from google.oauth2 import service_account, credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, ValidationError

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarError(Exception):
    """Raised when calendar operations fail."""


def _to_datetime(value: str, tz: Optional[str]) -> Tuple[dt.datetime, bool]:
    """Parse date or datetime; returns (dt, is_all_day)."""
    value = value.strip()
    if not value:
        raise ValueError("time value is empty")

    # Try RFC3339
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")), False
    except ValueError:
        pass

    # Date-only
    try:
        date_val = dt.date.fromisoformat(value)
        return dt.datetime.combine(date_val, dt.time()), True
    except ValueError:
        pass

    # Lenient parse without timezone
    patterns = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
    for pattern in patterns:
        try:
            parsed = dt.datetime.strptime(value, pattern)
            if tz:
                parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(0)))
            return parsed, False
        except ValueError:
            continue
    raise ValueError(
        "Could not parse time; use RFC3339 or YYYY-MM-DD for all-day events."
    )


def _compute_end(
    start: dt.datetime, start_all_day: bool, end: Optional[str], duration_minutes: Optional[int]
) -> Tuple[dt.datetime, bool]:
    if end:
        parsed_end, end_all_day = _to_datetime(end, None)
        if start_all_day != end_all_day:
            raise ValueError("start_time and end_time must both be date-only or both include time")
        return parsed_end, end_all_day

    if start_all_day:
        return start + dt.timedelta(days=1), True
    if duration_minutes and duration_minutes > 0:
        return start + dt.timedelta(minutes=duration_minutes), False
    return start + dt.timedelta(hours=1), False


def _build_service(creds: credentials.Credentials):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def credentials_from_service_account(path: str) -> credentials.Credentials:
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def credentials_from_oauth(token_info: Dict[str, str]) -> credentials.Credentials:
    return credentials.Credentials.from_authorized_user_info(token_info, scopes=SCOPES)


class AddEventPayload(BaseModel):
    summary: str
    start_time: str = Field(..., alias="start_time")
    end_time: Optional[str] = Field(default=None, alias="end_time")
    duration_minutes: Optional[int] = Field(default=None, alias="duration_minutes")
    description: Optional[str] = None
    location: Optional[str] = None
    time_zone: Optional[str] = Field(default=None, alias="time_zone")


class EditEventPayload(BaseModel):
    event_id: str = Field(..., alias="event_id")
    summary: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    time_zone: Optional[str] = None
    location: Optional[str] = None


class CalendarClient:
    def __init__(self, base_credentials: credentials.Credentials):
        self._base_credentials = base_credentials

    @classmethod
    def from_service_account(cls, credentials_file: str) -> "CalendarClient":
        creds = credentials_from_service_account(credentials_file)
        return cls(creds)

    @classmethod
    def from_oauth_token(cls, token_info: Dict[str, str]) -> "CalendarClient":
        creds = credentials_from_oauth(token_info)
        return cls(creds)

    def list_upcoming(self) -> str:
        try:
            service = _build_service(self._base_credentials)
            now = dt.datetime.utcnow().isoformat() + "Z"
            end = (dt.datetime.utcnow() + dt.timedelta(days=3)).isoformat() + "Z"
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=end,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
        except HttpError as exc:
            raise CalendarError(str(exc)) from exc

        if not events:
            return "No upcoming events found."

        lines: list[str] = []
        for event in events:
            start = event.get("start", {})
            when = start.get("dateTime") or start.get("date") or "unknown"
            lines.append(f"{when} – {event.get('summary', 'Untitled')} (id: {event.get('id')})")
        return "\n".join(lines)

    def add_event(self, raw_input: str) -> str:
        try:
            payload = AddEventPayload.model_validate_json(raw_input)
        except ValidationError as exc:
            raise CalendarError(f"Invalid add event payload: {exc}") from exc

        start, start_all_day = _to_datetime(payload.start_time, payload.time_zone)
        end, end_all_day = _compute_end(start, start_all_day, payload.end_time, payload.duration_minutes)
        if end <= start:
            raise CalendarError("end_time must be after start_time")

        start_block: Dict[str, str] = {}
        end_block: Dict[str, str] = {}
        if start_all_day:
            start_block["date"] = start.date().isoformat()
            end_block["date"] = end.date().isoformat()
        else:
            start_block["dateTime"] = start.isoformat()
            end_block["dateTime"] = end.isoformat()
            if payload.time_zone:
                start_block["timeZone"] = payload.time_zone
                end_block["timeZone"] = payload.time_zone

        body = {
            "summary": payload.summary,
            "description": payload.description,
            "location": payload.location,
            "start": start_block,
            "end": end_block,
        }

        try:
            service = _build_service(self._base_credentials)
            created = service.events().insert(calendarId="primary", body=body).execute()
        except HttpError as exc:
            raise CalendarError(f"Unable to create event: {exc}") from exc

        link = created.get("htmlLink")
        start_disp = created.get("start", {}).get("dateTime") or created.get("start", {}).get("date")
        end_disp = created.get("end", {}).get("dateTime") or created.get("end", {}).get("date")
        base_msg = f'Created calendar event "{created.get("summary","")}" ({start_disp} → {end_disp}).'
        if link:
            return f"{base_msg} Link: {link}"
        return base_msg

    def edit_event(self, raw_input: str) -> str:
        try:
            payload = EditEventPayload.model_validate_json(raw_input)
        except ValidationError as exc:
            raise CalendarError(f"Invalid edit payload: {exc}") from exc

        try:
            service = _build_service(self._base_credentials)
            existing = service.events().get(calendarId="primary", eventId=payload.event_id).execute()
        except HttpError as exc:
            raise CalendarError(f"Unable to fetch event: {exc}") from exc

        start_info = existing.get("start", {})
        end_info = existing.get("end", {})
        tz = payload.time_zone or start_info.get("timeZone") or end_info.get("timeZone")

        def resolve_time(block: Dict[str, str]) -> Optional[str]:
            return block.get("dateTime") or block.get("date")

        start_raw = payload.start_time or resolve_time(start_info)
        end_raw = payload.end_time or resolve_time(end_info)

        start_dt, start_all_day = _to_datetime(start_raw, tz) if start_raw else (None, False)  # type: ignore[arg-type]
        if start_dt is None:
            raise CalendarError("Event has no start time; provide start_time")
        end_dt, end_all_day = _compute_end(
            start_dt,
            start_all_day,
            end_raw,
            payload.duration_minutes,
        )
        if start_all_day != end_all_day:
            raise CalendarError("start_time and end_time must both be date-only or both include time")

        if start_all_day:
            start_block = {"date": start_dt.date().isoformat()}
            end_block = {"date": end_dt.date().isoformat()}
        else:
            start_block = {"dateTime": start_dt.isoformat()}
            end_block = {"dateTime": end_dt.isoformat()}
            if tz:
                start_block["timeZone"] = tz
                end_block["timeZone"] = tz

        update_body = {
            "summary": payload.summary or existing.get("summary"),
            "description": payload.description or existing.get("description"),
            "location": payload.location or existing.get("location"),
            "start": start_block,
            "end": end_block,
        }

        try:
            saved = service.events().update(
                calendarId="primary", eventId=payload.event_id, body=update_body
            ).execute()
        except HttpError as exc:
            raise CalendarError(f"Unable to update event: {exc}") from exc

        link = saved.get("htmlLink")
        start_disp = saved.get("start", {}).get("dateTime") or saved.get("start", {}).get("date")
        end_disp = saved.get("end", {}).get("dateTime") or saved.get("end", {}).get("date")
        base_msg = f'Updated calendar event "{saved.get("summary","")}" ({start_disp} → {end_disp}).'
        if link:
            return f"{base_msg} Link: {link}"
        return base_msg


