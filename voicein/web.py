"""Phone web recorder: localhost-only HTTP, session cookie, paste on the laptop."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from openai import OpenAI

from voicein.config import load_config
from voicein.cues import play_recording_cue
from voicein.pipeline import run_pipeline_audio
from voicein.web_auth import (
    cookie_header,
    cookie_valid,
    clear_cookie_header,
    load_auth,
    parse_cookie_header,
    issue_cookie,
    verify_password,
)
from voicein.web_pages import APP_PAGE, LOGIN_PAGE

logger = logging.getLogger(__name__)

_MAX_AUDIO = 20 * 1024 * 1024
_LOGIN_WINDOW = 900
_LOGIN_MAX = 5

_fail_lock = threading.Lock()
_failures: dict[str, list[float]] = defaultdict(list)


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    cf = handler.headers.get("CF-Connecting-IP", "").strip()
    if cf:
        return cf
    forwarded = handler.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return handler.client_address[0]


def _login_blocked(ip: str) -> bool:
    now = time.time()
    with _fail_lock:
        stamps = [t for t in _failures[ip] if now - t < _LOGIN_WINDOW]
        _failures[ip] = stamps
        return len(stamps) >= _LOGIN_MAX


def _login_fail(ip: str) -> None:
    with _fail_lock:
        _failures[ip].append(time.time())


def _login_ok(ip: str) -> None:
    with _fail_lock:
        _failures.pop(ip, None)


def _is_https(handler: BaseHTTPRequestHandler) -> bool:
    proto = handler.headers.get("X-Forwarded-Proto", "").lower()
    if proto == "https":
        return True
    visitor = handler.headers.get("CF-Visitor", "")
    return "https" in visitor.lower()


def _origin_ok(handler: BaseHTTPRequestHandler, public_host: str) -> bool:
    host = (handler.headers.get("Host") or "").split(":")[0].lower()
    allowed = {public_host.lower(), "127.0.0.1", "localhost"}
    if host and host not in allowed:
        return False
    origin = (handler.headers.get("Origin") or "").strip()
    if not origin:
        referer = (handler.headers.get("Referer") or "").strip()
        origin = referer
    if not origin:
        return handler.command == "POST" and handler.path == "/login"
    if origin.startswith("https://"):
        origin_host = origin[len("https://") :].split("/")[0].split(":")[0].lower()
    elif origin.startswith("http://"):
        origin_host = origin[len("http://") :].split("/")[0].split(":")[0].lower()
    else:
        return False
    return origin_host in allowed


def _filename_for(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "mp4" in lowered or "m4a" in lowered:
        return "recording.mp4"
    if "ogg" in lowered:
        return "recording.ogg"
    if "mpeg" in lowered or "mp3" in lowered:
        return "recording.mp3"
    if "wav" in lowered:
        return "recording.wav"
    return "recording.webm"


def make_handler(*, public_host: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("%s - %s", _client_ip(self), fmt % args)

        def _auth(self):
            return load_auth()

        def _authed(self) -> bool:
            auth = self._auth()
            if auth is None:
                return False
            token = parse_cookie_header(self.headers.get("Cookie"))
            return cookie_valid(auth, token)

        def _send(self, code: int, body: bytes, *, content_type: str, extra: list[str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            if extra:
                for line in extra:
                    name, _, value = line.partition(":")
                    self.send_header(name.strip(), value.strip())
            self.end_headers()
            self.wfile.write(body)

        def _html(self, code: int, text: str, extra: list[str] | None = None) -> None:
            self._send(code, text.encode("utf-8"), content_type="text/html; charset=utf-8", extra=extra)

        def _json(self, code: int, payload: dict, extra: list[str] | None = None) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self._send(code, raw, content_type="application/json; charset=utf-8", extra=extra)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
                self._send(404, b"not found", content_type="text/plain")
                return
            auth = self._auth()
            if auth is None:
                self._html(503, "<p>VoiceIn web auth is not set up. Run: python -m voicein web-setup</p>")
                return
            if self._authed():
                self._html(200, APP_PAGE)
                return
            self._html(200, LOGIN_PAGE.replace("%ERROR%", ""))

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if not _origin_ok(self, public_host):
                self._json(403, {"error": "Bad origin"})
                return
            if path == "/login":
                self._login()
                return
            if path == "/logout":
                self._logout()
                return
            if path == "/transcribe":
                self._transcribe()
                return
            self._send(404, b"not found", content_type="text/plain")

        def _login(self) -> None:
            auth = self._auth()
            if auth is None:
                self._html(503, "<p>Auth is not configured.</p>")
                return
            ip = _client_ip(self)
            if _login_blocked(ip):
                logger.warning("Login lockout for %s", ip)
                page = LOGIN_PAGE.replace("%ERROR%", "Too many attempts. Wait 15 minutes.")
                self._html(429, page)
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length > 4096:
                self._html(413, LOGIN_PAGE.replace("%ERROR%", "Invalid request."))
                return
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            password = (parse_qs(raw).get("password") or [""])[0]
            if not verify_password(auth, password):
                _login_fail(ip)
                logger.warning("Failed login from %s", ip)
                self._html(401, LOGIN_PAGE.replace("%ERROR%", "Wrong password."))
                return
            _login_ok(ip)
            token = issue_cookie(auth)
            header = cookie_header(
                token,
                max_age=auth.session_days * 86400,
                secure=_is_https(self),
            )
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", header)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _logout(self) -> None:
            header = clear_cookie_header(secure=_is_https(self))
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", header)
            self.end_headers()

        def _transcribe(self) -> None:
            if not self._authed():
                self._json(401, {"error": "Sign in first."})
                return
            if self.headers.get("X-VoiceIn") != "1":
                self._json(403, {"error": "Missing request token."})
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > _MAX_AUDIO:
                self._json(413, {"error": "Recording too large or empty."})
                return
            data = self.rfile.read(length)
            cfg = load_config()
            if not cfg.openai_api_key:
                self._json(500, {"error": "Missing OpenAI API key on the laptop."})
                return
            filename = _filename_for(self.headers.get("Content-Type") or "")
            play_recording_cue("stop", spec=cfg.cue_sound_stop, block=False)
            client = OpenAI(api_key=cfg.openai_api_key)
            try:
                okay, detail = run_pipeline_audio(
                    client=client,
                    cfg=cfg,
                    data=data,
                    filename=filename,
                    rewrite_level=cfg.llm_rewrite_level,
                )
            except Exception:
                logger.exception("Web transcribe failed")
                self._json(500, {"error": "Transcription failed."})
                return
            if okay:
                play_recording_cue("paste", spec=cfg.cue_sound_paste, block=False)
                logger.info("%s", detail)
                self._json(200, {"ok": True})
                return
            logger.warning("%s", detail)
            self._json(400, {"ok": False, "error": detail})

    return Handler


def serve(*, host: str, port: int, public_host: str) -> None:
    if load_auth() is None:
        raise SystemExit("Run `python -m voicein web-setup` first to create a password.")
    httpd = ThreadingHTTPServer((host, port), make_handler(public_host=public_host))
    logger.info("VoiceIn web listening on http://%s:%s (public host %s)", host, port, public_host)
    httpd.serve_forever()
