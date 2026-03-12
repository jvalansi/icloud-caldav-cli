# icloud-caldav-cli

A minimal Python CLI for reading and writing iCloud Calendar events via CalDAV.

Works with any CalDAV server, but defaults to iCloud.

## Installation

```bash
pip install caldav icalendar
```

## Configuration

Set environment variables (or add to `.env`):

```bash
export APPLE_ID=you@icloud.com
export APPLE_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # app-specific password from appleid.apple.com
export CALDAV_TIMEZONE=America/New_York          # optional, defaults to system timezone
export CALDAV_URL=https://caldav.icloud.com      # optional, defaults to iCloud
```

> **App-specific password:** Go to [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords → Generate.

## Usage

**List all calendars:**
```bash
python calendar_tool.py list-calendars
```

**Get upcoming events:**
```bash
python calendar_tool.py get-events
python calendar_tool.py get-events --days 14
python calendar_tool.py get-events --calendar "Work"
```

**Create an event:**
```bash
python calendar_tool.py create-event \
  --title "Team standup" \
  --start 2026-03-15T09:00 \
  --end 2026-03-15T09:30 \
  --calendar "Work" \
  --location "Zoom"
```

**Delete an event:**
```bash
python calendar_tool.py delete-event --event-id <UID>
```

Event UIDs are returned by `get-events` and `create-event`.

## Reminders

**List reminders (open only by default):**
```bash
python calendar_tool.py get-reminders
python calendar_tool.py get-reminders --list "Shopping"
python calendar_tool.py get-reminders --include-completed
```

**Create a reminder:**
```bash
python calendar_tool.py create-reminder --title "Buy milk"
python calendar_tool.py create-reminder --title "Call dentist" --due 2026-03-20 --priority high
python calendar_tool.py create-reminder --title "Review PR" --due 2026-03-15T10:00 --list "Work"
```

**Complete a reminder:**
```bash
python calendar_tool.py complete-reminder --reminder-id <UID>
```

**Delete a reminder:**
```bash
python calendar_tool.py delete-reminder --reminder-id <UID>
```

Reminder UIDs are returned by `get-reminders` and `create-reminder`.

> **Note:** Basic CRUD works reliably. Location-based reminders, subtasks, and attachments are not supported via CalDAV.

## Output

All commands output JSON, making it easy to pipe into other tools or use from AI agents.

```json
[
  {
    "uid": "662F88CB-ED52-47BB-935F-570EBB921C88",
    "title": "Team standup",
    "start": "2026-03-15T09:00:00+02:00",
    "end": "2026-03-15T09:30:00+02:00",
    "description": null,
    "location": "Zoom",
    "calendar": "Work"
  }
]
```

## Use with AI agents

This tool works well as a Claude (or other LLM) tool — the JSON output is easy to parse and the CLI interface maps cleanly to natural language requests like "what's on my calendar this week?" or "add a meeting Thursday at 3pm".
