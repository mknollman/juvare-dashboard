# Troubleshooting

## The site shows a Cloudflare "Bad Gateway" (502)

The tunnel is up but can't reach the backend service.

1. **Confirm the app is listening.** In Portainer, the container should be
   *Running/Healthy* and logs show `[web] serving /app/web on http://0.0.0.0:8080`.
2. **Confirm the port binding.** The stack must publish `"8082:8080"` (no
   `127.0.0.1:` prefix), or the cloudflared container won't reach it. If it is
   `127.0.0.1:8082:8080`, the service is invisible to containers.
3. **Confirm the tunnel URL.** Inside a cloudflared **container**, `127.0.0.1`
   is the container itself. Use the Docker bridge gateway IP of a bridge the
   container is connected to — typically `172.19.0.1` — plus the published
   port: `http://172.19.0.1:8082`.
   - If the cloudflared instance runs as a **system service** (not a
     container), `http://127.0.0.1:8082` is correct.
4. **Trailing whitespace.** The dashboard URL field rejects trailing spaces
   with `invalid port ":8082 " after host` — clear the field and retype.

## Docker says "port is already allocated"

Something else on the VPS owns that port (8080 is commonly taken). Pick a
different published port (8082, 8083, …) and use it in the tunnel URL too.

## Container shows "starting" forever / unhealthy (before first email)

The healthcheck checks `GET /` (the dashboard page), **not** `/api/snapshot`,
because the snapshot correctly returns 503 until the first email arrives.
After the (up to 60 s) interval it should flip to healthy. If it never does,
open the Logs tab and look for tracebacks.

## `{"error": "no data yet"}` on the public site

Nothing has been ingested yet. Either no email has been forwarded, or the
Worker/Email Routing hop is broken. Test each stage:

1. **App works:** `POST /api/ingest` manually with a sample body and a correct
   `X-Ingest-Token` → 200 summary JSON.
2. **Worker works:** in the Worker editor, add temporary debug logging
   (`console.log`) or check **Metrics/Logs** for the `email` invocations. Make
   sure `INGEST_TOKEN` and `WEBHOOK_URL` env vars are set on the Worker.
3. **Email Routing works:** the custom address should show status **Active**.
   Mail to `juvare@yourdomain` should appear in the Worker metrics.

Remember: forward an **old** email to test — its data is stale, but it proves
the pipeline and (optionally) backfills history.

## Dashboard shows hospitals, but some have grey "Unknown"

- The hospital is not in this email's snapshot rows (snapshot only holds
  hospitals that reported a status), and no event has covered it yet.
- Or the `HOSPITALS` substring doesn't match the full name used in the email
  snapshot (e.g. `Atrium` matches the snapshot row `Premier Health Atrium
  Medical Center` but not a short-name subject line).
- A hospital never covered by any email stays grey until it appears.

## A hospital is missing entirely

Check `HOSPITALS` values against the exact snapshot names (`GET
/api/config` lists the configured substrings; the raw ingests print the full
names). Remember entries are semicolon-separated and commas are literal.

## Statuses look wrong/stale

Statuses are exactly what Juvare emailed; the dashboard makes no extrapolation.
The snapshot shows the **most recent value reported**, with `seen_at`. If you
forward an old email, it clobbers newer state for hospitals in that email.
When you test with old mail, re-send the most recent real email afterwards.

## The Worker URL shows "No fetch handler!"

Expected. The worker only implements `email()`, not a web request handler, so
opening its URL in a browser shows that error page. It does not affect email
delivery.

## Portainer Web editor/console quirks

- "Deploy" greyed out, "Missing stack frames", or a `loader.js` error = the
  **Cloudflare/Portainer dashboard UI** chunk failed to load. Hard refresh
  (`Ctrl+Shift+R`), or retry in a private window / another browser. Not caused
  by your code.
- The container console often won't accept typing. Don't debug through it;
  test connectivity from outside instead (curl through the tunnel or a manual
  `POST /api/ingest`).

## Data directory / volume

`snapshot.json` and `history.json` live in the `juvare-data` volume
(`/data` in the container). To reset everything, delete the volume and
redeploy (Portainer → Volumes → remove `juvare-dashboard_juvare-data`). You
will need to forward an email again to rebuild state.