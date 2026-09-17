# Juvare email format & parser rules

## What an EMResource status email looks like

```
From: EMResource <no-reply@appmail.juvare.com>
Subject: EMResource - UC Health West Chester

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
(≈190 rows, one per hospital reporting a status)
```

Key facts the parser relies on:

1. The **subject** names the triggering hospital, but the parser reads the
   event from the **body**, not the subject.
2. **Event line** format:
   `On MM/DD/YYYY HH:MM TZ <Hospital> changed ED Status status from <Old> to <New>.`
3. The event's hospital ("UC Health West Chester" above) is **excluded from
   its own email's snapshot section**, so the parser folds the event's `to`
   status back into the snapshot explicitly.
4. Immediately after the line `Other Hospital Short Terms in the region
   report the following ED Status status:` come `Name = Status` rows.

## Parser implementation (`app/emailparser.py`)

### Event detection — `EVENT_RE`

```python
r"On\s+(?P<ts>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+[A-Z]{2,5})\s+"
r"(?P<hospital>.+?)\s+changed\s+ED\s+Status\s+status\s+from\s+"
r"(?P<old_status>.*?)\s+to\s+(?P<new_status>.*?)\.\s*$"
```

- Matches lines starting with "On …". The `.?` hospital group is lazy, and
  "changed ED Status status from … to … ." anchors the end.
- Old status is captured minimally (so both short and long status strings
  work); new status captures everything up to the trailing period.
- The regex anchors at the region `*$` per stripped line, so a longer sentence
  later in the email doesn't false-match.

### Snapshot rows

Each non-empty line is scanned for the FIRST occurrence of one of these
separators (in order): `" = "`, `" ="`, `"= "`.

```
name, _, status = line.partition(sep)
snapshot[name.strip()] = status.strip()
```

This intentionally tolerates inconsistent spacing (`Name=Status`,
`Name = Status`). Real statuses never contain an `=`, so this is safe.

### Timestamps — `parse_ts` + `TZ_ALIASES`

`MM/DD/YYYY HH:MM TZ` is parsed with `strptime` and given a real timezone via
`zoneinfo`:

| Alias        | Zone                      |
| ------------ | ------------------------- |
| EDT / EST    | `America/New_York`        |
| CDT / CST    | `America/Chicago`         |
| MDT / MST    | `America/Denver`          |
| PDT / PST    | `America/Los_Angeles`     |
| ET / CT / MT / PT | the matching zone above (ET → New_York) |

If no TZ matches or parse fails, the email's receipt time is used instead
(`ts = received_at`).

### Merge — `ingest(cfg, subject, body)`

1. Parse event + snapshot.
2. Fold the event's `new_status` into the snapshot under the event hospital
   (step 3 in the anatomy above).
3. `snapshot.json`: for every (name → status), write
   `hospitals[name] = {"status": status, "seen_at": <now>}`; update
   `last_received`. Merging means hospitals not covered by this email keep
   their previous status.
4. `history.json`: if an event was found, append
   `{received_at, ts, hospital, old_status, new_status}` and trim to the
   newest 5000. Written atomically via `tmp + os.replace` to avoid corruption
   if a write is interrupted.

Both files use `indent=2` for readability; the API reads them on each request
(no in-memory cache), so the dashboard reflects ingests immediately.

## Status vocabulary observed

Examples seen in regional snapshots: `Normal`,
`Limited Divert/Operations`, `Divert/At Capacity`. The parser stores statuses
verbatim — it never normalizes vocabulary. Colour logic in `web/app.js`
classifies by substring (`divert`, `limited`, `normal`, else grey).
## Power Automate cloud flow format (added 2026-09-17)

When the pipeline changed from Outlook forwarding to a **Power Automate cloud
flow**, the body arriving at `/api/ingest` changed shape:

- The whole email arrives as **one single line** (newlines collapsed to
  spaces), with a prefix before the event sentence, e.g.
  `Status Update for Matt Knollman: On 09/17/2026 09:06 EDT UC Health ...`.
- Snapshot rows run together on that line:
  `... status: Ohio State ... Hosp = N/A Mercy Health - ... = Normal ...`.
- A Safelinks tracking URL (`https://...&data=...=...`) may trail the body.

The old parser assumed one row per line and an event line starting with
`On`, so it stored **one giant fake hospital** whose name + status were the
entire email body (visible on the dashboard because the blob contains
tracked substrings like `West Chester`).

Current parser defences (`app/emailparser.py`):

1. Event is searched anywhere in the body (`EVENT_SEARCH_RE`), not just at
   line start.
2. Snapshot rows are only read from text **after** the
   `report the following ED Status status:` marker.
3. Rows are recovered from collapsed single-line bodies via `SNAPSHOT_ROW_RE`
   against the known status vocabulary (`Normal`, `N/A`,
   `Limited Divert/Operations`, `Divert/At Capacity`).
4. HTML bodies are normalized first (block tags → newlines, tags stripped).
5. Trailing URL query fragments (`=` inside Safelinks URLs) never match the
   vocabulary and are ignored.
