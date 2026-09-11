# Local development

The web app is pure Python **standard library** — no virtualenv, no `pip install`
for the app itself. Machine needs Python 3.9+ (uses `zoneinfo`).

## Run

```bash
cp .env.example .env      # edit values
python app/main.py
```

Serves `http://127.0.0.1:8080`. Dashboard auto-refreshes every 60 s.

## Layout of the code

- `app/main.py` — reads `Config`, starts the server.
- `app/config.py` — env config. Also loads a `.env` file from the CWD if you
  run outside Docker (no dotenv dependency). `ENV_FILE` can point at a custom
  path. Uses `setdefault`, so real environment variables win.
- `app/server.py` — `BaseHTTPRequestHandler` server with worker threads.
  Routes:
  - `POST /api/ingest` — the only write path (token-gated).
  - `GET /api/snapshot` — current statuses, filtered to `HOSPITALS`.
  - `GET /api/history` — last 200 events, filtered to `HOSPITALS`.
  - `GET /api/config` — `{ hospitals: [...], interval_min: 60 }`.
  - everything else — static files from `WEB_DIR`.
- `app/emailparser.py` — the parser. See EMAIL_FORMAT.md.

## Testing the ingest API directly

The endpoint accepts three content types:

**1. Formatted email body (plain text).** Optionally include the subject
  header; parser reads the event + snapshot from the body:

```bash
curl -X POST http://127.0.0.1:8080/api/ingest \
     -H "X-Ingest-Token: <token>" \
     -H "Content-Type: text/plain" \
     -H "X-Mail-Subject: EMResource - UC Health West Chester" \
     -d @sample-email.txt
```

**2. Raw RFC822 email** (what the Cloudflare Worker actually sends):

```bash
curl -X POST http://127.0.0.1:8080/api/ingest \
     -H "X-Ingest-Token: <token>" \
     -H "Content-Type: message/rfc822" \
     --data-binary @email.eml
```

**3. JSON**:

```bash
curl -X POST http://127.0.0.1:8080/api/ingest \
     -H "X-Ingest-Token: <token>" \
     -H "Content-Type: application/json" \
     -d '{"subject":"EMResource - Kettering Health Hamilton","body":"On 09/10/2026 08:00 EDT Kettering Health Hamilton changed ED Status status from Normal to Limited Divert/Operations.\n\nOther Hospital Short Terms in the region report the following ED Status status:\nChrist Hospital, The - Liberty Township = Normal\n"}'
```

Response is a summary:

```json
{
  "received_at": "2026-09-10T20:51:24.042236",
  "event": { "hospital": "...", "old_status": "...", "new_status": "...", "ts": "..." },
  "hospitals_in_email": 190,
  "total_hospitals": 198
}
```

Bad or missing token → `401`. Malformed JSON → `400`.

## Sample fixture

The original project used a real sample email during development. Save one of
your own EMResource emails as `sample-email.txt` (or grab it from your Outlook
sent/forwarded copies) to replay tests:

```bash
cp ~/Downloads/sample-email.txt .
curl -X POST http://127.0.0.1:8080/api/ingest -H "X-Ingest-Token: <token>" \
     -H "Content-Type: text/plain" -d @sample-email.txt
```

## HOSPITALS gotchas

- Separator is **`;`** because hospital names contain commas (e.g.
  `Christ Hospital, The - Liberty`). Splitting on `,` would break them.
- Matching is case-insensitive substring: `Cincinnati` also matches
  `UC Health University of Cincinnati MC`. Filter the display set until it
  contains only the hospitals you want.
- Substrings match against the **full names in the email snapshot**, not
  necessarily the short names in the subject line.

## Docker

In Docker the image builds from this repo and runs `python app/main.py` with
defaults suitable for a container (`DATA_DIR=/data`, `WEB_DIR=/app/web`,
port 8080). Update the image by pushing + redeploying (see DEPLOYMENT.md).