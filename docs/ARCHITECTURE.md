# Architecture

## The problem

Juvare EMResource only exposes status data through:

- a web dashboard behind **Okta SSO + hCaptcha** (not headless-automatable —
  this project originally tried Playwright and hit the captcha), or
- a paid API license (~$3.5k).

One freely available signal remains: **status-change emails** that Juvare sends
to EMResource users. Each email contains both

1. a single **event** line (`<hospital> changed ED Status status from X to Y`),
   and
2. the **entire regional snapshot** (`<Name> = <Status>` for ~190 hospitals).

## Pipeline

```
Outlook rule: from no-reply@appmail.juvare.com
    └─▶ forward to juvare@yourdomain
           │
Cloudflare Email Routing (free, MX/SPF auto-added)
    └─▶ route juvare@yourdomain → Worker  "juvare-email-ingest"
           │
Cloudflare Worker (scripts/worker.js)
    └─▶ POST body: message.raw  (message/rfc822)
        headers: X-Ingest-Token + X-Mail-Subject
           │
┌──────────▼──────────────────────────────────────────────┐
│ VPS app  (Portainer stack, from github.com/mknollman/    │
│            juvare-dashboard, port 8082)                  │
│                                                          │
│  POST /api/ingest  (token-gated)                         │
│    └─▶ emailparser.ingest()                              │
│          • parse event + snapshot from the email         │
│          • fold the event's "to" status into the snapshot│
│          • merge snapshot.json (per-hospital seen_at)    │
│          • append event to history.json (capped 5000)    │
│                                                          │
│  GET /api/snapshot  filtered to HOSPITALS                │
│  GET /api/history    last 200 events, filtered           │
│  GET /              dashboard static site                │
└──────────────────────────────────────────────────────────┘
           ▲
Cloudflare Tunnel: public hostname → http://172.19.0.1:8082
   https://hospitals.knollman.net
```

## Why each hop exists

| Hop                                  | Job                                                                 |
| ------------------------------------ | ------------------------------------------------------------------- |
| Outlook rule                         | Delivers the right emails to the ingest address.                    |
| Cloudflare Email Routing             | Free inbound email; adds MX/SPF automatically; no extra inbox.      |
| Cloudflare Worker                    | Bridges email → HTTP with zero infrastructure on your side.         |
| `X-Ingest-Token`                     | Only shared secret; scoped to `POST /api/ingest`.                   |
| Cloudflare Tunnel                    | Exposes the VPS service publicly without opening firewall ports.    |
| VPS app (Python stdlib)              | Parses, persists, and serves — dependencies are standard library.   |

## Data model

`snapshot.json` (in the `juvare-data` volume at `/data`):

```json
{
  "last_received": "2026-09-10T20:51:24.042236",
  "hospitals": {
    "UC Health West Chester": {
      "status": "Divert/At Capacity",
      "seen_at": "2026-09-10T20:51:24.042236"
    }
  }
}
```

`history.json`:

```json
[
  {
    "received_at": "2026-09-10T20:51:24.042236",
    "ts": "2026-09-10T14:48:00-04:00",
    "hospital": "UC Health West Chester",
    "old_status": "Divert/At Capacity",
    "new_status": "Normal"
  }
]
```

- `ts` is the event timestamp from the email, normalized to `America/New_York`
  via the TZ aliases in `app/emailparser.py` (`EDT`
  → `America/New_York`, `CDT` → `America/Chicago`, etc.).
- Timeline events are capped at the most recent 5000.

## Status → colour mapping

Defined in `web/app.js`:

| Status text contains…  | Class  | Colour  |
| ---------------------- | ------ | ------- |
| `divert`               | `bad`  | red     |
| `limited`              | `warn` | amber   |
| `normal`               | `ok`   | green   |
| anything else          | `unk`  | grey    |

Only hospitals listed in `HOSPITALS` appear. Filtering is case-insensitive
substring matching, applied **server-side** in `/api/snapshot` and
`/api/history`, so the website payload is small even though each email carries
~190 hospitals.

## Failure characteristics

- If the Worker or Email Routing is down, emails simply don't reach the app —
  nothing breaks in Outlook, and old emails can be re-forwarded later.
- If the VPS is down, the tunnel returns 502; data persists in the volume.
- Emails are processed on arrival; there is no scheduler and no polling.
- `GET /api/snapshot` returns **503** with `{"error": "no data yet"}` until the
  first email has been ingested (this is what the container healthcheck
  deliberately avoids depending on).