# Deployment

This project is deployed in three unrelated systems:

1. **VPS** — the Python app, run as a Portainer stack, built from the git repo.
2. **Cloudflare** — Tunnel (public hostname), Email Worker, Email Routing.
3. **Microsoft Outlook** — the forwarding rule that feeds the pipeline.

Order matters: app first, tunnel second, worker/routing third, rule last.

---

## 0. Prerequisites

- A VPS reachable from a Cloudflare Tunnel. The reference deployment uses
  Portainer on the VPS.
- `knollman.net` (any domain works) on Cloudflare DN, with **no MX records**
  yet (Cloudflare Email Routing adds them).
- Docker registry or a git repo the VPS can build from.
  This repo is public at `github.com/mknollman/juvare-dashboard`.

---

## 1. VPS app via Portainer

### 1.1 Push the code somewhere Portainer can build

```bash
git init -b main
git add .
git commit -m "Juvare ED status dashboard"
gh repo create juvare-dashboard --private --source=. --push
# make it public (only if you want Portainer to build without credentials)
gh repo edit OWNER/juvare-dashboard --visibility=public --accept-visibility-change-consequences
```

### 1.2 Portainer stack (Web editor)

**Portainer → Stacks → + Add stack → Web editor**, paste:

```yaml
services:
  juvare-dashboard:
    build:
      context: "https://github.com/OWNER/juvare-dashboard.git#main"
    container_name: juvare-dashboard
    restart: unless-stopped
    ports:
      - "8082:8080"
    volumes:
      - juvare-data:/data
    environment:
      INGEST_TOKEN: "<generate a random token>"
      HOSPITALS: "Christ Hospital, The - Liberty; Kettering Health Hamilton; Atrium; Bethesda North; Bethesda Butler; Cincinnati; West Chester; Mercy Health - Fairfield Hospital"
      DATA_DIR: /data
      WEB_DIR: /app/web

volumes:
  juvare-data:
```

Notes:

- The production stack binds **all interfaces** on port **8082** so the
  cloudflared *container* can reach it (see the tunnel section). The repo's
  `docker-compose.yml` binds loopback:8080 for local use.
- `INGEST_TOKEN` must be the **same value** configured in the Cloudflare Worker
  later.
- If the bind says `port is already allocated`, pick another free port and use
  it consistently in the tunnel.

### 1.3 Verify

In Portainer the container should go **healthy** within ~60 s. Logs show
`[web] serving /app/web on http://0.0.0.0:8080` and `GET / HTTP/1.1 200`.

---

## 2. Cloudflare Tunnel

Your VPS already runs a `cloudflared` **container** for other services (e.g.
Nextcloud). Its webhook URL points at the Docker bridge gateway because inside
that container `127.0.0.1` is the container itself, not the host.

**Zero Trust → Networks → Tunnels → *your tunnel* → Public Hostname tab →
Add a public hostname**

- Subdomain   : `hospitals`
- Domain      : `knollman.net`
- Service type: `HTTP`
- URL         : `http://172.19.0.1:8082`

The gateway IP `172.19.0.1` is the one the existing Nextcloud hostname already
uses on this host — reuse whatever gateway IP your working hostname uses.
(The port is the one from step 1.2.)

Test: `curl -s https://hospitals.knollman.net/api/snapshot` → either JSON or
`{"error": "no data yet"}` (503). A **502** means the tunnel backend URL is
wrong; see TROUBLESHOOTING.

---

## 3. Cloudflare Email Worker

1. **Workers & Pages → Create application → Create Worker** (the current UI
   labels it *"Start with Hello World"*). Name it `juvare-email-ingest`.
2. Replace the boilerplate with `scripts/worker.js` from this repo.
3. **Settings → Variables and Secrets**, add:
   - `INGEST_TOKEN` = same token as step 1.2
   - `WEBHOOK_URL`  = `https://hospitals.knollman.net/api/ingest`
4. Save and deploy.

## 4. Cloudflare Email Routing

1. **Select the domain (knollman.net) → Email → Email Routing → Enable**.
   Cloudflare adds the MX + SPF records automatically; no DNS work.
2. **Routing rules → Custom addresses → Create address**:
   - Address    : `juvare@knollman.net`
   - Destination: **Send to a Worker** → select `juvare-email-ingest`.
3. Status should become **Active**.

The worker appears in the destination list because it has an `email()`
handler; there is no extra "trigger" to configure.

---

## 5. Outlook rule

New rule:

- **From**: `EMResource <no-reply@appmail.juvare.com>`
- **Action**: **forward to** `juvare@knollman.net`

Every future status-change email now drives the dashboard automatically.

---

## 6. End-to-end test

Forward any existing EMResource email to `juvare@knollman.net`, then:

```bash
curl -s https://hospitals.knollman.net/api/snapshot
```

You should see your `HOSPITALS` list with statuses and a `last_received`
timestamp, and the dashboard fills with cards.

---

## Redeploying after code changes

Push to the repo, then **Portainer → Stack → juvare-dashboard → Redeploy**
(it rebuilds the image from the git context). Data survives in the
`juvare-data` volume.