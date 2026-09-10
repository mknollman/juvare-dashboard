# Juvare ED status dashboard — from your email instead of scraping
#
# Juvare's team dashboard is behind an Okta login with hCaptcha, so scraping
# is fragile. But Juvare *emails* you on every status change, and each email
# actually contains the ENTIRE regional status snapshot. This project parses
# those emails and shows the hospitals you care about, colored by status.

## How it works

    Outlook rule: forward EMResource emails to juvare@your.domain
        ⬇
    Cloudflare Email Routing (free) routes juvare@your.domain to a Worker
        ⬇
    Worker POSTs the raw email to https://your-tunnel/api/ingest
    (+ X-Ingest-Token secret)
        ⬇
    This app (VPS via Portainer):
      • parses hospital/status/time from each email
      • merges a running regional snapshot
      • appends change events to history
      • serves the web dashboard

The app keeps running; data lives in the `juvare-data` volume
(snapshot.json + history.json).

## One-time Cloudflare + Outlook setup

1. Cloudflare Email Routing (Dashboard > your domain > Email):
   - First add+verify a destination address (any working email).
   - Create custom address   juvare@yourdomain
     - send to: Worker  →  "Send to a Worker"  →  create Worker.
   - Cloudflare adds the MX/SPF records automatically (no DNS work for you).

2. Cloudflare Worker (zero-dependency):
   - Create Worker > paste scripts/worker.js.
   - Environment variables:
       INGEST_TOKEN = <the same secret as below>
       WEBHOOK_URL  = https://dashboard.<yourdomain>/api/ingest
       (point this at your Cloudflare Tunnel hostname)
   - Deploy, then wire the custom address route to it.

3. Outlook rule:
   - New rule: from EMResource <no-reply@appmail.juvare.com>
     → forward to juvare@yourdomain

## Local run (no Docker)

    cp .env.example .env   # fill in INGEST_TOKEN + HOSPITALS
    python app/main.py     # serves http://127.0.0.1:8080

Test the pipeline by POSTing an email body manually:

    curl -X POST http://127.0.0.1:8080/api/ingest \
         -H "X-Ingest-Token: $INGEST_TOKEN" \
         -H "Content-Type: text/plain" \
         -d @sample-email.txt

Or with a subject:

    curl -X POST ...?subject="EMResource - UC Health West Chester"

The ingest endpoint also accepts JSON: {"subject": ..., "body": ...}.

## Deploy to VPS (Portainer)

- Stack from this repo (build). Set environment:
    INGEST_TOKEN  (random secret; must match the Worker)
    HOSPITALS    = Christ, Kettering, Mercy, Premier, TriHealth, UC Health
- Add a Cloudflare Tunnel (public hostname) from dashboard.<yourdomain>
  → http://juvare-dashboard:8080 (or the container IP:8080).
- curl a test email through the tunnel to confirm end to end.

## Backfill existing history

Your inbox still holds past Juvare status emails. Two options:
- Forward a handful of old ones manually (each one fills ~190 hospital rows),
  or set the rule to also forward an older folder once.
- A future optional IMAP sync can pull the whole thread automatically.

## Statuses and colours

Colour mapping lives in web/app.js: divert → red, limited → amber,
Normal → green, anything else → grey. Only hospitals in HOSPITALS are shown.