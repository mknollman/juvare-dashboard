"""Parse Juvare EMResource status emails into events + regional snapshots.

Sample email shape:

    Subject: EMResource - UC Health West Chester
    ...
    On 09/09/2026 14:48 EDT UC Health West Chester changed
    ED Status status from Divert/At Capacity to Normal.

    Comments:
    Reasons:
    Region: State of Ohio

    Other Hospital Short Terms in the region report the following
    ED Status status:
    ProMedica Toledo Hospital = Limited Divert/Operations
    Trinity Medical Center West = Limited Divert/Operations
    ...
"""
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

EVENT_RE = re.compile(
    r"On\s+(?P<ts>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+[A-Z]{2,5})\s+"
    r"(?P<hospital>.+?)\s+changed\s+ED\s+Status\s+status\s+from\s+"
    r"(?P<old_status>.*?)\s+to\s+(?P<new_status>.*?)\.\s*$"
)

SNAPSHOT_RE = re.compile(r"report the following ED Status status:")

TZ_ALIASES = {
    "EDT": "America/New_York",
    "EST": "America/New_York",
    "ET": "America/New_York",
    "CDT": "America/Chicago",
    "CST": "America/Chicago",
    "CT": "America/Chicago",
    "MDT": "America/Denver",
    "MST": "America/Denver",
    "MT": "America/Denver",
    "PDT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
}


def parse_ts(text):
    """Parse 'MM/DD/YYYY HH:MM TZ' into an ISO timestamp (or None)."""
    m = re.match(r"\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2})\s+([A-Z]{2,5})", text)
    if not m:
        return None
    when = m.group(1)
    tz_name = TZ_ALIASES.get(m.group(2).upper())
    try:
        dt = datetime.strptime(when, "%m/%d/%Y %H:%M")
        if tz_name:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
            return dt.isoformat()
        return dt.isoformat()
    except ValueError:
        return None


def parse_email(subject="", body=""):
    """Return (event, snapshot) from an EMResource email.

    event:    dict(hospital, old_status, new_status, ts) or None
    snapshot: {hospital_name: status} for every row in the regional list
    """
    event = None
    snapshot = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = EVENT_RE.match(line)
        if m and not event:
            event = {
                "hospital": m.group("hospital").strip(),
                "old_status": m.group("old_status").strip(),
                "new_status": m.group("new_status").strip(),
                "ts": parse_ts(m.group("ts")) or datetime.now().isoformat(),
            }
            continue
        for sep in (" = ", " =", "= "):
            if sep in line:
                name, _, status = line.partition(sep)
                name = name.rstrip().strip()
                status = status.strip()
                if name and status:
                    snapshot[name] = status
                break
    return event, snapshot


def _apply_event_snapshot(snapshot, event):
    """The changed hospital is left out of its own email's regional list;
    fold the event's 'to' status in explicitly."""
    if event:
        snapshot[event["hospital"]] = event["new_status"]


def ingest(cfg, subject, body, received_at=None):
    """Merge one email into snapshot.json + history.json. Returns summary."""
    if received_at is None:
        received_at = datetime.now().isoformat()
    event, snapshot = parse_email(subject, body)
    _apply_event_snapshot(snapshot, event)

    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    current = _read_json(cfg.snapshot_path) or {"last_received": None, "hospitals": {}}
    hospitals = current.get("hospitals", {})
    for name, status in snapshot.items():
        hospitals[name] = {"status": status, "seen_at": received_at}
    if event:
        hospitals[event["hospital"]] = {
            "status": event["new_status"],
            "seen_at": received_at,
        }
    current["last_received"] = received_at
    current["hospitals"] = hospitals
    _write_json(cfg.snapshot_path, current)

    if event:
        history = _read_json(cfg.history_path) or []
        history.append({
            "received_at": received_at,
            "ts": event["ts"],
            "hospital": event["hospital"],
            "old_status": event["old_status"],
            "new_status": event["new_status"],
        })
        history = history[-5000:]
        _write_json(cfg.history_path, history)

    return {
        "received_at": received_at,
        "event": event,
        "hospitals_in_email": len(snapshot),
        "total_hospitals": len(hospitals),
    }


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)