import email
import json
import mimetypes
import os
import time
from email import policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import emailparser


def _read_email_body(raw, subject_hint=""):
    """Extract (subject, text_body) from an RFC822 message."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    subject = msg.get("Subject", "") or subject_hint
    text = ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain":
            try:
                text += part.get_content()
            except Exception:
                pass
        elif ctype == "multipart/alternative":
            pass
    if not text:
        text = msg.get_body(preferencelist=("plain", "html"))
        if text:
            text = text.get_content()
    return subject or subject_hint or "", text or ""


def make_handler(cfg):
    web_dir = os.path.abspath(cfg.WEB_DIR)

    class Handler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def log_message(self, fmt, *args):  # keep logs quiet
            print("[web]", fmt % args, flush=True)

        def _send_json(self, obj, status=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _filter_hospitals(self, data):
            names = data.get("hospitals", {})
            if not cfg.HOSPITALS:
                return data
            wanted = {}
            shown = set()
            for name in cfg.HOSPITALS:
                for key, val in names.items():
                    if key not in shown and name.lower() in key.lower():
                        wanted[key] = val
                        shown.add(key)
            data["hospitals"] = wanted
            return data

        def do_GET(self):
            path = self.path.rstrip("/")
            if path == "/api/snapshot":
                snap = _read_json(cfg.snapshot_path)
                if snap is None:
                    self._send_json({"error": "no data yet"}, status=503)
                else:
                    self._send_json(self._filter_hospitals(snap))
                return
            if path == "/api/history":
                hist = _read_json(cfg.history_path) or []
                if cfg.HOSPITALS:
                    hist = [e for e in hist
                            if any(h.lower() in e.get("hospital", "").lower()
                                   for h in cfg.HOSPITALS)]
                self._send_json(hist[-200:])
                return
            if path == "/api/config":
                self._send_json({
                    "hospitals": cfg.HOSPITALS,
                    "interval_min": cfg.SCRAPE_INTERVAL_MIN,
                })
                return
            self._serve_static()

        def do_POST(self):
            if self.path.rstrip("/") != "/api/ingest":
                self.send_response(404)
                self.end_headers()
                return
            token = self.headers.get("X-Ingest-Token", "")
            if token != cfg.INGEST_TOKEN:
                self._send_json({"error": "unauthorized"}, status=401)
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "").lower()
            if "json" in ctype:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send_json({"error": "bad json"}, status=400)
                    return
                subject = payload.get("subject", "")
                body = payload.get("body", "")
            else:
                subject_hint = self.headers.get("X-Mail-Subject", "")
                subject, body = _read_email_body(raw, subject_hint)
            try:
                summary = emailparser.ingest(cfg, subject, body)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
                return
            print(f"[ingest] {summary['hospitals_in_email']} hospitals, "
                  f"event={bool(summary['event'])} {subject}", flush=True)
            self._send_json(summary)

        # SimpleHTTPRequestHandler needs translate_path/send_head for static files
        def _serve_static(self):
            import urllib.parse
            from http.server import SimpleHTTPRequestHandler
            parsed = urllib.parse.urlparse(self.path)
            rel = urllib.parse.unquote(parsed.path)
            if rel == "/":
                rel = "/index.html"
            full = os.path.normpath(os.path.join(web_dir, rel.lstrip("/")))
            if not full.startswith(web_dir) or not os.path.isfile(full):
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def start_server(cfg):
    handler = make_handler(cfg)
    httpd = ThreadingHTTPServer((cfg.HOST, cfg.PORT), handler)
    print(f"[web] serving {cfg.WEB_DIR} on http://{cfg.HOST}:{cfg.PORT}", flush=True)
    httpd.serve_forever()