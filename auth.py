"""
Clerk-based authentication for the Unbound desktop app.

Flow:
  1. sign_in() starts a local HTTP server on a random port.
  2. Opens the system browser to the Unbound API device-auth page.
  3. User signs in via Clerk in the browser.
  4. Browser redirects to http://localhost:{port}/callback?key=...&state=...
  5. Local server captures the API key and stores it in the OS keyring.
  6. All subsequent API calls use the key via get_api_key().
"""

import http.server
import threading
import webbrowser
import secrets
import socket
from urllib.parse import urlparse, parse_qs

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

API_BASE         = "https://unbound-api-amber.vercel.app"
_KEYRING_SERVICE = "unbound-app"
_KEY_ACCOUNT     = "api_key"
_EMAIL_ACCOUNT   = "user_email"

# Fallback in-memory store when keyring is unavailable
_mem_store: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Key storage (keyring → in-memory fallback)
# ---------------------------------------------------------------------------

def get_api_key() -> str | None:
    if _KEYRING_AVAILABLE:
        return keyring.get_password(_KEYRING_SERVICE, _KEY_ACCOUNT)
    return _mem_store.get(_KEY_ACCOUNT)


def get_user_email() -> str | None:
    if _KEYRING_AVAILABLE:
        return keyring.get_password(_KEYRING_SERVICE, _EMAIL_ACCOUNT)
    return _mem_store.get(_EMAIL_ACCOUNT)


def is_signed_in() -> bool:
    return bool(get_api_key())


def _store(api_key: str, email: str | None) -> None:
    if _KEYRING_AVAILABLE:
        keyring.set_password(_KEYRING_SERVICE, _KEY_ACCOUNT, api_key)
        if email:
            keyring.set_password(_KEYRING_SERVICE, _EMAIL_ACCOUNT, email)
    else:
        _mem_store[_KEY_ACCOUNT] = api_key
        if email:
            _mem_store[_EMAIL_ACCOUNT] = email


def _clear() -> None:
    if _KEYRING_AVAILABLE:
        for acct in (_KEY_ACCOUNT, _EMAIL_ACCOUNT):
            try:
                keyring.delete_password(_KEYRING_SERVICE, acct)
            except Exception:
                pass
    else:
        _mem_store.clear()


# ---------------------------------------------------------------------------
# Sign-in (browser OAuth via local callback server)
# ---------------------------------------------------------------------------

def sign_in(timeout: int = 120) -> bool:
    """
    Opens the browser for Clerk sign-in and waits for the local callback.
    Returns True if sign-in succeeded within `timeout` seconds, False otherwise.
    """
    port  = _free_port()
    state = secrets.token_urlsafe(16)
    result: dict = {"key": None, "done": threading.Event()}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = parse_qs(urlparse(self.path).query)
            received_state = params.get("state", [None])[0]
            received_key   = params.get("key",   [None])[0]

            if received_state == state and received_key:
                result["key"] = received_key
                body = b"<html><body style='font-family:monospace;color:#ccc;background:#111;padding:2rem'>" \
                       b"<h2>Signed in to Unbound.</h2><p>You can close this tab.</p></body></html>"
            else:
                body = b"<html><body>Invalid request.</body></html>"

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            threading.Thread(target=server.shutdown, daemon=True).start()
            result["done"].set()

        def log_message(self, *_):
            pass  # suppress request logs

    server = http.server.HTTPServer(("localhost", port), _Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"{API_BASE}/auth/device?port={port}&state={state}"
    webbrowser.open(url)

    result["done"].wait(timeout=timeout)

    if result["key"]:
        email = _fetch_email(result["key"])
        _store(result["key"], email)
        return True

    server.shutdown()
    return False


def sign_out() -> None:
    """Revokes the API key on the server and clears local storage."""
    key = get_api_key()
    if key and _REQUESTS_AVAILABLE:
        try:
            _requests.post(
                f"{API_BASE}/api/auth/logout",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
        except Exception:
            pass
    _clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_email(api_key: str) -> str | None:
    if not _REQUESTS_AVAILABLE:
        return None
    try:
        r = _requests.get(
            f"{API_BASE}/api/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        if r.ok:
            return r.json().get("email")
    except Exception:
        pass
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]
