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
import html as _html
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EVENT_RE = re.compile(
    r"On\s+(?P<ts>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+[A-Z]{2,5})\s+"
    r"(?P<hospital>.+?)\s+changed\s+ED\s+Status\s+status\s+from\s+"
    r"(?P<old_status>.*?)\s+to\s+(?P<new_status>.*?)\.\s*$"
)

# Same event pattern but searchable anywhere in a line/body: Power Automate
# collapses the email to a single line and prepends a prefix such as
# "Status Update for Matt Knollman: " before the "On ..." event sentence,
# so anchoring at line start (^ / match()) misses it.
EVENT_SEARCH_RE = re.compile(
    r"On\s+(?P<ts>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+[A-Z]{2,5})\s+"
    r"(?P<hospital>.+?)\s+changed\s+ED\s+Status\s+status\s+from\s+"
    r"(?P<old_status>.*?)\s+to\s+(?P<new_status>.*?)\."
)

SNAPSHOT_RE = re.compile(r"report the following\s+ED Status status:")

# Statuses observed verbatim in regional snapshots. Used to recover rows when
# Power Automate collapses the whole email to ONE line ("Name = Status Name
# = Status ...") so line-splitting cannot separate rows.
STATUS_VOCAB = (
    "Limited Divert/Operations",
    "Divert/At Capacity",
    "Normal",
    "N/A",
)
SNAPSHOT_ROW_RE = re.compile(
    r"(?P<name>[^=]+?)\s*=\s*(?P<status>"
    + "|".join(re.escape(s) for s in STATUS_VOCAB)
    + r")(?=\s|$)"
)

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


def _normalize_body(body):
    """Return plain text with newlines preserved where possible.

    Power Automate may hand us HTML (Outlook connector 'Body' is HTML by
    default) or plain text with newlines collapsed to spaces. Convert block
    tags to newlines, strip remaining tags, unescape entities.
    """
    text = body or ""
    # Block-level tags -> newline so rows survive HTML stripping.
    text = re.sub(r"(?i)<\s*(br|/p|/div|/tr|/li|/h\d)[^>]*>", "\n", text)
    text = re.sub(r"(?i)<\s*(p|div|tr|li)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _parse_event(body):
    """Find the status-change event anywhere in the body (or None)."""
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = EVENT_RE.match(line)
        if m:
            return {
                "hospital": m.group("hospital").strip(),
                "old_status": m.group("old_status").strip(),
                "new_status": m.group("new_status").strip(),
                "ts": parse_ts(m.group("ts"))
                or datetime.now(timezone.utc).isoformat(),
            }
    # Fallback: single-line/collapsed body, possibly with a prefix before
    # "On ...". Search instead of line-anchored matching.
    flat = " ".join(body.split())
    m = EVENT_SEARCH_RE.search(flat)
    if m:
        return {
            "hospital": m.group("hospital").strip(),
            "old_status": m.group("old_status").strip(),
            "new_status": m.group("new_status").strip(),
            "ts": parse_ts(m.group("ts"))
            or datetime.now(timezone.utc).isoformat(),
        }
    return None


def _parse_snapshot(body):
    """Return {hospital_name: status} for rows after the snapshot marker.

    Only text AFTER 'report the following ED Status status:' is considered,
    so '=' lines elsewhere (forward headers, comments, URLs) never become
    fake hospitals. Handles both multi-line bodies (one row per line) and
    Power Automate single-line bodies (rows space-separated).
    """
    m = SNAPSHOT_RE.search(body)
    if not m:
        return {}
    section = body[m.end():]
    snapshot = {}
    # Fast path: regex over the whole section catches both multi-line rows
    # and collapsed single-line rows, as long as the status is known vocab.
    for rm in SNAPSHOT_ROW_RE.finditer(section):
        name = " ".join(rm.group("name").split())
        # The first name still carries the marker's trailing words when the
        # body has no newline after the marker ("... status: First Hosp").
        # Nothing precedes it except the marker itself, so keep it whole;
        # stray prefixes only occur before the marker, which we cut off.
        status = rm.group("status").strip()
        if name and status:
            snapshot[name] = status
    if snapshot:
        return snapshot
    # Fallback for unknown future statuses: classic line-based parse, still
    # gated behind the marker. Guards length so prose never becomes a row.
    for line in section.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        for sep in (" = ", " =", "= "):
            if sep in line:
                name, _, status = line.partition(sep)
                name = " ".join(name.split())
                status = status.strip()
                if name and status and len(status) <= 60 and "=" not in status:
                    snapshot[name] = status
                break
    return snapshot


def parse_email(subject="", body=""):
    """Return (event, snapshot) from an EMResource email.

    event:    dict(hospital, old_status, new_status, ts) or None
    snapshot: {hospital_name: status} for every row in the regional list
    """
    body = _normalize_body(body)
    event = _parse_event(body)
    snapshot = _parse_snapshot(body)
    return event, snapshot


def _apply_event_snapshot(snapshot, event):
    """The changed hospital is left out of its own email's regional list;
    fold the event's 'to' status in explicitly."""
    if event:
        snapshot[event["hospital"]] = event["new_status"]


def ingest(cfg, subject, body, received_at=None):
    """Merge one email into snapshot.json + history.json. Returns summary."""
    if received_at is None:
        received_at = datetime.now(timezone.utc).isoformat()
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
