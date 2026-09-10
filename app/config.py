import os


def _load_env_file(path=".env"):
    """Minimal .env loader (no external dependency). CWD-relative, so run from
    the project root."""
    candidates = [path]
    env_hint = os.environ.get("ENV_FILE", "")
    if env_hint and os.path.exists(env_hint):
        candidates.append(env_hint)
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        os.environ.setdefault(key, value)
        except OSError:
            continue


_load_env_file()


def _int(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


class Config:
    """All configuration comes from environment variables (Portainer secrets/env)."""

    DATA_DIR = os.environ.get("DATA_DIR", "/data")

    # Ingest: the Cloudflare Worker POSTs each forwarded email here with this
    # token in the X-Ingest-Token header.
    INGEST_TOKEN = os.environ.get("INGEST_TOKEN", "changeme")

    # Hospital filter: semicolon- or newline-separated substrings (commas are
    # kept literal because they appear inside hospital names); only these show.
    _h = os.environ.get("HOSPITALS", "").replace("\\n", "\n").replace("\n", ";")
    HOSPITALS = [h.strip() for h in _h.split(";") if h.strip()]

    # Background catch-up poll of Juvare status-change emails (optional IMAP
    # backfill - empty disables it).
    IMAP_HOST = os.environ.get("IMAP_HOST", "")
    IMAP_USER = os.environ.get("IMAP_USER", "")
    IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")
    IMAP_MAILBOX = os.environ.get("IMAP_MAILBOX", "INBOX")

    # Behaviour / web ------------------------------------------------------
    SCRAPE_INTERVAL_MIN = _int("SCRAPE_INTERVAL_MIN", 60)
    WEB_DIR = os.environ.get("WEB_DIR", "/app/web")
    HOST = os.environ.get("WEB_HOST", "0.0.0.0")
    PORT = _int("WEB_PORT", 8080)

    @property
    def snapshot_path(self):
        return os.path.join(self.DATA_DIR, "snapshot.json")

    @property
    def history_path(self):
        return os.path.join(self.DATA_DIR, "history.json")