#!/usr/bin/env python3
"""
iCloud CalDAV CLI — interact with iCloud Calendar and Reminders from the command line.

Usage:
  python calendar_tool.py list-calendars
  python calendar_tool.py get-events [--days N] [--calendar NAME]
  python calendar_tool.py create-event --title TITLE --start DATETIME --end DATETIME [--calendar NAME] [--description TEXT] [--location TEXT]
  python calendar_tool.py delete-event --event-id UID [--calendar NAME]

  python calendar_tool.py get-reminders [--list NAME] [--include-completed]
  python calendar_tool.py create-reminder --title TITLE [--due DATETIME] [--list NAME] [--notes TEXT] [--priority low|medium|high]
  python calendar_tool.py complete-reminder --reminder-id UID [--list NAME]
  python calendar_tool.py delete-reminder --reminder-id UID [--list NAME]

DATETIME format: YYYY-MM-DDTHH:MM  (e.g. 2026-03-15T14:00)

Environment variables:
  APPLE_ID            Your Apple ID (iCloud email)
  APPLE_APP_PASSWORD  App-specific password from appleid.apple.com
  CALDAV_URL          CalDAV server URL (default: https://caldav.icloud.com)
  CALDAV_TIMEZONE     Timezone for naive datetimes (default: system timezone)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import caldav
from caldav.elements import dav
from icalendar import Calendar, Event as ICalEvent, Todo as ICalTodo
import uuid

PRIORITY_MAP = {"high": 1, "medium": 5, "low": 9}

CALDAV_URL = os.environ.get("CALDAV_URL", "https://caldav.icloud.com")
APPLE_ID = os.environ.get("APPLE_ID", "")
APPLE_APP_PASSWORD = os.environ.get("APPLE_APP_PASSWORD", "")


def get_client():
    return caldav.DAVClient(url=CALDAV_URL, username=APPLE_ID, password=APPLE_APP_PASSWORD)


def get_principal():
    client = get_client()
    return client.principal()


def cmd_list_calendars(_args):
    principal = get_principal()
    calendars = principal.calendars()
    result = []
    for cal in calendars:
        props = cal.get_properties([dav.DisplayName()])
        name = props.get("{DAV:}displayname", cal.url.path.rstrip("/").split("/")[-1])
        result.append({"name": name, "url": str(cal.url)})
    print(json.dumps(result, indent=2))


def _local_tz():
    """Return configured timezone, falling back to system timezone, then UTC."""
    tz_name = os.environ.get("CALDAV_TIMEZONE", "")
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    try:
        return ZoneInfo("localtime")
    except Exception:
        return timezone.utc


def _parse_dt(s: str) -> datetime:
    """Parse YYYY-MM-DDTHH:MM into a timezone-aware datetime."""
    tz = _local_tz()
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def _event_to_dict(vevent) -> dict:
    """Extract key fields from a VEVENT component."""
    def _str(val):
        if val is None:
            return None
        if hasattr(val, "dt"):
            v = val.dt
            if isinstance(v, datetime):
                return v.isoformat()
            return str(v)
        return str(val)

    return {
        "uid": _str(vevent.get("uid")),
        "title": _str(vevent.get("summary")),
        "start": _str(vevent.get("dtstart")),
        "end": _str(vevent.get("dtend")),
        "description": _str(vevent.get("description")),
        "location": _str(vevent.get("location")),
    }


def cmd_get_events(args):
    principal = get_principal()
    calendars = principal.calendars()

    # Filter by calendar name if specified
    if args.calendar:
        cname = args.calendar.lower()
        calendars = [
            c for c in calendars
            if args.calendar.lower() in str(
                c.get_properties([dav.DisplayName()]).get("{DAV:}displayname", "")
            ).lower()
        ]
        if not calendars:
            print(json.dumps({"error": f"No calendar matching '{args.calendar}'"}))
            sys.exit(1)

    now = datetime.now(_local_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=args.days)

    results = []
    for cal in calendars:
        props = cal.get_properties([dav.DisplayName()])
        cal_name = props.get("{DAV:}displayname", "?")
        try:
            events = cal.search(start=start, end=end, event=True, expand=True)
        except Exception:
            continue
        for event in events:
            cal_obj = Calendar.from_ical(event.data)
            for component in cal_obj.walk():
                if component.name == "VEVENT":
                    d = _event_to_dict(component)
                    d["calendar"] = cal_name
                    results.append(d)

    # Sort by start time
    results.sort(key=lambda e: e.get("start") or "")
    print(json.dumps(results, indent=2))


def cmd_create_event(args):
    principal = get_principal()
    calendars = principal.calendars()

    # Pick calendar
    target_cal = None
    if args.calendar:
        for cal in calendars:
            props = cal.get_properties([dav.DisplayName()])
            name = props.get("{DAV:}displayname", "")
            if args.calendar.lower() in name.lower():
                target_cal = cal
                break
        if target_cal is None:
            print(json.dumps({"error": f"No calendar matching '{args.calendar}'"}))
            sys.exit(1)
    else:
        # Default to first non-task calendar
        for cal in calendars:
            props = cal.get_properties([dav.DisplayName()])
            name = props.get("{DAV:}displayname", "").lower()
            if "reminder" not in name and "task" not in name:
                target_cal = cal
                break
        if target_cal is None:
            target_cal = calendars[0]

    start_dt = _parse_dt(args.start)
    end_dt = _parse_dt(args.end)

    cal_obj = Calendar()
    cal_obj.add("prodid", "-//icloud-caldav-cli//EN")
    cal_obj.add("version", "2.0")

    event = ICalEvent()
    event_uid = str(uuid.uuid4())
    event.add("uid", event_uid)
    event.add("summary", args.title)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    event.add("dtstamp", datetime.now(timezone.utc))
    if args.description:
        event.add("description", args.description)
    if args.location:
        event.add("location", args.location)

    cal_obj.add_component(event)
    target_cal.save_event(cal_obj.to_ical().decode())

    print(json.dumps({"status": "created", "uid": event_uid, "title": args.title, "start": start_dt.isoformat(), "end": end_dt.isoformat()}))


def cmd_delete_event(args):
    principal = get_principal()
    calendars = principal.calendars()

    if args.calendar:
        calendars = [
            c for c in calendars
            if args.calendar.lower() in str(
                c.get_properties([dav.DisplayName()]).get("{DAV:}displayname", "")
            ).lower()
        ]

    for cal in calendars:
        try:
            events = cal.search(uid=args.event_id)
        except Exception:
            continue
        for event in events:
            event.delete()
            print(json.dumps({"status": "deleted", "uid": args.event_id}))
            return

    print(json.dumps({"error": f"Event with uid '{args.event_id}' not found"}))
    sys.exit(1)


def _get_reminder_lists(principal, name_filter=None):
    """Return CalDAV calendars that contain VTODOs (reminder lists)."""
    lists = []
    for cal in principal.calendars():
        props = cal.get_properties([dav.DisplayName()])
        name = props.get("{DAV:}displayname", cal.url.path.rstrip("/").split("/")[-1])
        if name_filter and name_filter.lower() not in name.lower():
            continue
        lists.append((name, cal))
    return lists


def _todo_to_dict(vtodo, list_name: str) -> dict:
    def _str(val):
        if val is None:
            return None
        if hasattr(val, "dt"):
            v = val.dt
            if isinstance(v, datetime):
                return v.isoformat()
            return str(v)
        return str(val)

    priority_raw = vtodo.get("priority")
    priority = None
    if priority_raw is not None:
        p = int(str(priority_raw))
        if p == 1:
            priority = "high"
        elif p == 5:
            priority = "medium"
        elif p == 9:
            priority = "low"

    return {
        "uid": _str(vtodo.get("uid")),
        "title": _str(vtodo.get("summary")),
        "due": _str(vtodo.get("due")),
        "notes": _str(vtodo.get("description")),
        "status": _str(vtodo.get("status")) or "NEEDS-ACTION",
        "completed": _str(vtodo.get("completed")),
        "priority": priority,
        "list": list_name,
    }


def cmd_get_reminders(args):
    principal = get_principal()
    reminder_lists = _get_reminder_lists(principal, args.list)

    results = []
    for list_name, cal in reminder_lists:
        try:
            todos = cal.search(todo=True)
        except Exception:
            continue
        for todo in todos:
            cal_obj = Calendar.from_ical(todo.data)
            for component in cal_obj.walk():
                if component.name != "VTODO":
                    continue
                d = _todo_to_dict(component, list_name)
                if not args.include_completed and d["status"] == "COMPLETED":
                    continue
                results.append(d)

    results.sort(key=lambda r: r.get("due") or "9999")
    print(json.dumps(results, indent=2))


def cmd_create_reminder(args):
    principal = get_principal()

    target_list = None
    if args.list:
        lists = _get_reminder_lists(principal, args.list)
        if not lists:
            print(json.dumps({"error": f"No reminder list matching '{args.list}'"}))
            sys.exit(1)
        target_list = lists[0][1]
    else:
        # Default to the iCloud Reminders list (named "תזכורות" or "Reminders")
        for name, cal in _get_reminder_lists(principal):
            if name.lower() in ("reminders", "תזכורות"):
                target_list = cal
                break
        if target_list is None:
            all_lists = _get_reminder_lists(principal)
            if not all_lists:
                print(json.dumps({"error": "No reminder lists found"}))
                sys.exit(1)
            target_list = all_lists[0][1]

    cal_obj = Calendar()
    cal_obj.add("prodid", "-//icloud-caldav-cli//EN")
    cal_obj.add("version", "2.0")

    todo = ICalTodo()
    todo_uid = str(uuid.uuid4())
    todo.add("uid", todo_uid)
    todo.add("summary", args.title)
    todo.add("status", "NEEDS-ACTION")
    todo.add("dtstamp", datetime.now(timezone.utc))
    if args.due:
        todo.add("due", _parse_dt(args.due))
    if args.notes:
        todo.add("description", args.notes)
    if args.priority:
        todo.add("priority", PRIORITY_MAP.get(args.priority, 0))

    cal_obj.add_component(todo)
    target_list.save_todo(cal_obj.to_ical().decode())

    print(json.dumps({"status": "created", "uid": todo_uid, "title": args.title}))


def _find_todo(principal, uid, list_filter=None):
    """Search all reminder lists for a VTODO with the given UID."""
    for _name, cal in _get_reminder_lists(principal, list_filter):
        try:
            todos = cal.search(uid=uid, todo=True)
        except Exception:
            continue
        for todo in todos:
            return todo
    return None


def cmd_complete_reminder(args):
    principal = get_principal()
    todo = _find_todo(principal, args.reminder_id, args.list)
    if todo is None:
        print(json.dumps({"error": f"Reminder '{args.reminder_id}' not found"}))
        sys.exit(1)

    cal_obj = Calendar.from_ical(todo.data)
    for component in cal_obj.walk():
        if component.name == "VTODO":
            component["status"] = "COMPLETED"
            component.add("completed", datetime.now(timezone.utc))
            break

    todo.data = cal_obj.to_ical().decode()
    todo.save()
    print(json.dumps({"status": "completed", "uid": args.reminder_id}))


def cmd_delete_reminder(args):
    principal = get_principal()
    todo = _find_todo(principal, args.reminder_id, args.list)
    if todo is None:
        print(json.dumps({"error": f"Reminder '{args.reminder_id}' not found"}))
        sys.exit(1)
    todo.delete()
    print(json.dumps({"status": "deleted", "uid": args.reminder_id}))


def main():
    parser = argparse.ArgumentParser(description="iCloud Calendar CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-calendars", help="List all calendars")

    p_get = sub.add_parser("get-events", help="Get upcoming events")
    p_get.add_argument("--days", type=int, default=7, help="Number of days to look ahead (default 7)")
    p_get.add_argument("--calendar", help="Filter by calendar name")

    p_create = sub.add_parser("create-event", help="Create a new event")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--start", required=True, help="YYYY-MM-DDTHH:MM")
    p_create.add_argument("--end", required=True, help="YYYY-MM-DDTHH:MM")
    p_create.add_argument("--calendar", help="Target calendar name")
    p_create.add_argument("--description", help="Event description")
    p_create.add_argument("--location", help="Event location")

    p_del = sub.add_parser("delete-event", help="Delete an event by UID")
    p_del.add_argument("--event-id", required=True, help="Event UID")
    p_del.add_argument("--calendar", help="Calendar name to search in")

    p_gr = sub.add_parser("get-reminders", help="List reminders")
    p_gr.add_argument("--list", help="Filter by reminder list name")
    p_gr.add_argument("--include-completed", action="store_true", help="Include completed reminders")

    p_cr = sub.add_parser("create-reminder", help="Create a reminder")
    p_cr.add_argument("--title", required=True)
    p_cr.add_argument("--due", help="Due date/time: YYYY-MM-DDTHH:MM or YYYY-MM-DD")
    p_cr.add_argument("--list", help="Target reminder list name")
    p_cr.add_argument("--notes", help="Reminder notes")
    p_cr.add_argument("--priority", choices=["low", "medium", "high"], help="Priority")

    p_done = sub.add_parser("complete-reminder", help="Mark a reminder as completed")
    p_done.add_argument("--reminder-id", required=True, help="Reminder UID")
    p_done.add_argument("--list", help="Reminder list name to search in")

    p_dr = sub.add_parser("delete-reminder", help="Delete a reminder by UID")
    p_dr.add_argument("--reminder-id", required=True, help="Reminder UID")
    p_dr.add_argument("--list", help="Reminder list name to search in")

    args = parser.parse_args()
    {
        "list-calendars": cmd_list_calendars,
        "get-events": cmd_get_events,
        "create-event": cmd_create_event,
        "delete-event": cmd_delete_event,
        "get-reminders": cmd_get_reminders,
        "create-reminder": cmd_create_reminder,
        "complete-reminder": cmd_complete_reminder,
        "delete-reminder": cmd_delete_reminder,
    }[args.command](args)


if __name__ == "__main__":
    if not APPLE_ID or not APPLE_APP_PASSWORD:
        print(json.dumps({"error": "APPLE_ID and APPLE_APP_PASSWORD env vars required"}))
        sys.exit(1)
    main()
