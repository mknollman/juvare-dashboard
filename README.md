# Juvare EMResource ED Status Dashboard

Track hospital Emergency Department (ED) status from Juvare EMResource's
daily **status-change emails** instead of scraping.

> Why not scrape? Juvare's team dashboard sits behind an Okta login with an
> hCaptcha challenge, so headless scraping is fragile and the EMResource API
> license is expensive. But Juvare **emails you on every status change**, and
> each email actually contains the **entire regional status snapshot**. This
> project just parses those emails and shows the hospitals you care about,
> color-coded by status.

Live example: `https://hospitals.knollman.net`

---

## In two lines

- An Outlook rule forwards each `no-reply@appmail.juvare.com` email to
  `juvare@yourdomain`.
- Cloudflare Email Routing hands it to a Worker, which POSTs the raw email to
  a small Python service on your VPS. That service parses the email, merges a
  running regional snapshot, writes `snapshot.json` + `history.json`, and
  serves the dashboard.

## Repository layout

```
app/
  main.py          entrypoint: starts the HTTP server
  server.py        stdlib HTTP server: /api/ingest, /api/snapshot, /api/history, static site
  emailparser.py   parses Juvare emails into events + regional snapshots
  config.py        config from environment (with a tiny .env loader)
web/
  index.html       dashboard page
  app.js           fetches the API, renders status cards + timeline
  style.css        dark theme, status colours
scripts/
  worker.js        Cloudflare Email Worker (forward email -> webhook)
docs/
  ARCHITECTURE.md      end-to-end data flow
  DEPLOYMENT.md        Portainer + Cloudflare + Outlook setup
  DEVELOPMENT.md       local dev, testing the ingest API
  TROUBLESHOOTING.md   common problems and fixes
  EMAIL_FORMAT.md      anatomy of a Juvare email and the parser rules
```

## Quick start (local, no Docker)

```bash
cp .env.example .env        # set INGEST_TOKEN + HOSPITALS
python app/main.py          # serves http://127.0.0.1:8080
```

Then feed it a real (or sample) email body:

```bash
curl -X POST http://127.0.0.1:8080/api/ingest \
     -H "X-Ingest-Token: <your_token>" \
     -H "Content-Type: text/plain" \
     -d @sample-email.txt
```

Open `http://127.0.0.1:8080` → the dashboard populates.

## Key configuration

| Variable       | Meaning                                                            |
| -------------- | ------------------------------------------------------------------ |
| `INGEST_TOKEN` | Shared secret; must match the Cloudflare Worker.                   |
| `HOSPITALS`    | Hospital name substrings to show, separated by `;` (hospital names contain commas, so commas are literal). |
| `DATA_DIR`     | Where `snapshot.json` / `history.json` live (default `/data`).     |
| `WEB_DIR`      | Static dashboard directory (default `/app/web`).                   |
| `WEB_HOST`     | Bind address (default `0.0.0.0`).                                   |
| `WEB_PORT`     | Listen port (default `8080`).                                       |

Everything is driven by environment variables, so the same image runs locally,
in Docker, and in Portainer.

## Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the full pipeline and data model.
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Portainer stack, Cloudflare Tunnel,
  Email Worker, Email Routing, and the Outlook rule, step by step.
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** — running and testing the API.
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** — what to check when
  something breaks.
- **[EMAIL_FORMAT.md](docs/EMAIL_FORMAT.md)** — the Juvare email format and how
  the parser handles it.