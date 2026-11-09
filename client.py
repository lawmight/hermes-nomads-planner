"""Read-only HTTP client for the public Nomads.com API (https://nomads.com/api).

Network: GET requests to https://nomads.com/api/* only. No writes, no other hosts.
Credentials: the personal key comes from Hermes (agent.secret_scope.get_secret), never
from the raw process environment, files, or browser state. It is sent in the Authorization header, never in
the URL, and never appears in a tool result or log line.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

BASE_URL = "https://nomads.com"
SECRET_NAME = "NOMADS_API_KEY"
SETTINGS_URL = "https://nomads.com/settings"
USER_AGENT = "Mozilla/5.0 (compatible; hermes-nomads-planner/0.1; +https://nomads.com/api)"
TIMEOUT_S = 15
CACHE_TTL_S = 600  # public city data is rate limited per IP (60/h, 200/day); cache politely

# Noise the API adds to every payload; we drop it so tool results stay small.
_DROP_KEYS = ("join", "sponsor")


class NomadsError(Exception):
    def __init__(self, code: str, detail: str = "", hint: str = "", status: int = 0):
        super().__init__(detail or code)
        self.code, self.detail, self.hint, self.status = code, detail, hint, status

    def as_dict(self) -> dict:
        out = {"ok": False, "error": self.code}
        if self.detail:
            out["detail"] = self.detail
        if self.hint:
            out["hint"] = self.hint
        if self.status:
            out["http_status"] = self.status
        return out


def _default_secret(name: str) -> Optional[str]:
    from agent.secret_scope import get_secret  # Hermes' profile-scoped route (catalog rule 11)

    return get_secret(name)


class Credentials:
    """Resolves (username, key) lazily, per call, so profile switches are honoured."""

    def __init__(self, get_config: Callable[[str, Any], Any],
                 get_secret: Callable[[str], Optional[str]] = _default_secret):
        self._get_config = get_config
        self._get_secret = get_secret

    def resolve(self) -> tuple[str, str]:
        try:
            raw = (self._get_secret(SECRET_NAME) or "").strip()
        except Exception as exc:  # e.g. UnscopedSecretError under multiplexing
            raise NomadsError("secret_unavailable", f"Hermes could not resolve {SECRET_NAME}: {type(exc).__name__}") from None
        username = str(self._get_config("username", "") or "").strip()
        key = raw
        if ":" in raw:  # Nomads' own Bearer format: username:key
            u, _, k = raw.partition(":")
            key = k.strip()
            username = username or u.strip()
        if not key:
            raise NomadsError(
                "missing_key",
                "This tool reads your own Nomads.com account and needs your personal key.",
                f"Get it at {SETTINGS_URL}, then run: hermes config set {SECRET_NAME} <key> "
                "(or use the plugin's settings form in Hermes Desktop). "
                "City, country and meetup tools work without it.",
            )
        if not username:
            raise NomadsError(
                "missing_username",
                "Nomads.com needs your username together with the key.",
                "Run: hermes config set plugins.entries.nomads-planner.settings.username <you>, or save the key as username:key.",
            )
        return username, key

    def available(self) -> bool:
        try:
            self.resolve()
            return True
        except NomadsError:
            return False


class NomadsClient:
    def __init__(self, credentials: Credentials,
                 opener: Optional[Callable[[urllib.request.Request, float], Any]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.credentials = credentials
        self._open = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self._clock = clock
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    # -- low level -------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None, member: bool = False,
             cache: bool = False) -> dict:
        clean = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        url = BASE_URL + path + (("?" + urllib.parse.urlencode(clean)) if clean else "")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        cache_key = url
        if member:
            username, key = self.credentials.resolve()
            headers["Authorization"] = f"Bearer {username}:{key}"
            cache = False  # never cache private data
        if cache:
            with self._lock:
                hit = self._cache.get(cache_key)
                if hit and self._clock() - hit[0] < CACHE_TTL_S:
                    return hit[1]
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            resp = self._open(req, TIMEOUT_S)
            body = resp.read()
            status = getattr(resp, "status", 200) or 200
        except urllib.error.HTTPError as exc:
            body, status = exc.read() or b"", exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NomadsError("network_error", f"Could not reach nomads.com: {type(exc).__name__}") from None
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            snippet = body[:120].decode("utf-8", "replace")
            if status in (403, 503) or "cloudflare" in snippet.lower():
                raise NomadsError("blocked", "nomads.com refused the request (edge protection).", status=status) from None
            raise NomadsError("bad_response", f"Non-JSON response from nomads.com (HTTP {status}).", status=status) from None
        if status == 429:
            raise NomadsError("rate_limited", "nomads.com rate limit hit (city data: 60/hour, 200/day per IP).",
                              "Wait and retry; results are cached for 10 minutes.", status=429)
        if isinstance(data, dict) and data.get("error"):
            hint = data.get("hint") or ""
            if data["error"] == "invalid_username_or_key":
                hint = f"Check the username setting and the key from {SETTINGS_URL}."
            raise NomadsError(str(data["error"]), str(data.get("detail") or ""), str(hint), status if status >= 400 else 0)
        if status >= 400:
            raise NomadsError("http_error", f"HTTP {status} from nomads.com", status=status)
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in _DROP_KEYS}
        if cache:
            with self._lock:
                self._cache[cache_key] = (self._clock(), data)
        return data

    # -- public city data -------------------------------------------------
    def search(self, **filters) -> dict:
        return self._get("/api/search", filters, cache=True)

    def top(self) -> dict:
        return self._get("/api/top", cache=True)

    def city(self, slug: str) -> dict:
        return self._get("/api/city/" + urllib.parse.quote(slug, safe="-"), cache=True)

    def country(self, slug: str) -> dict:
        return self._get("/api/country/" + urllib.parse.quote(slug, safe="-"), cache=True)

    def meetups(self, city: str = "", country: str = "", days_ahead: Optional[int] = None,
                limit: Optional[int] = None) -> dict:
        return self._get("/api/meetups", {"city": city, "country": country,
                                          "days_ahead": days_ahead, "limit": limit}, cache=True)

    # -- member data (read-only) ------------------------------------------
    def trips(self, from_date: str = "", to_date: str = "", limit: Optional[int] = None) -> dict:
        return self._get("/api/trips", {"from_date": from_date, "to_date": to_date, "limit": limit}, member=True)

    def favorites(self) -> dict:
        return self._get("/api/favorites", member=True)
