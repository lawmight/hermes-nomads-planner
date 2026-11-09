"""Tool handlers: dict args in, JSON string out (errors too). Read-only."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from . import brief as brief_mod
from .client import NomadsClient, NomadsError

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _err(code: str, detail: str = "", hint: str = "") -> str:
    return _dump(NomadsError(code, detail, hint).as_dict())


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _slug(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if _SLUG_RE.match(s) else ""


def _nights(t: dict) -> int:
    try:
        return max((date.fromisoformat(t["date_end"][:10]) - date.fromisoformat(t["date_start"][:10])).days, 0)
    except (KeyError, TypeError, ValueError):
        return 0


class Handlers:
    def __init__(self, client: NomadsClient):
        self.c = client

    def _run(self, fn, args: Any) -> str:
        if not isinstance(args, dict):
            args = {}
        try:
            return _dump(fn(args))
        except NomadsError as exc:
            return _dump(exc.as_dict())
        except Exception as exc:  # never raise into the agent loop
            return _err("internal_error", type(exc).__name__)

    # public ---------------------------------------------------------------
    def search_cities(self, args: dict, **_kw) -> str:
        def go(a):
            filters = {k: a.get(k) for k in ("region", "country", "max_cost_usd", "min_internet_mbps",
                                              "min_safety", "min_temperature_c", "max_temperature_c")}
            limit = _int(a.get("limit"), 10, 1, 100)
            data = self.c.search(**filters, limit=limit) if any(v not in (None, "") for v in filters.values()) else self.c.top()
            cities = (data.get("cities") or [])[:limit]
            return {"ok": True, "total_matching": data.get("total_matching", len(cities)), "returned": len(cities),
                    "cities": cities, "source": data.get("attribution", "Data from Nomads.com")}
        return self._run(go, args)

    def get_city(self, args: dict, **_kw) -> str:
        def go(a):
            slug = _slug(a.get("slug"))
            if not slug:
                raise NomadsError("invalid_slug", "Pass a city slug like lisbon-portugal.", "Use nomads_search_cities to find slugs.")
            data = self.c.city(slug)
            return {"ok": True, **data}
        return self._run(go, args)

    def get_country(self, args: dict, **_kw) -> str:
        def go(a):
            slug = _slug(a.get("slug"))
            if not slug:
                raise NomadsError("invalid_slug", "Pass a country slug like portugal or united-kingdom.")
            return {"ok": True, **self.c.country(slug)}
        return self._run(go, args)

    def list_meetups(self, args: dict, **_kw) -> str:
        def go(a):
            city = _slug(a.get("city")) if a.get("city") else ""
            if a.get("city") and not city:
                raise NomadsError("invalid_slug", "city must be a slug like lisbon-portugal.")
            data = self.c.meetups(city=city, country=str(a.get("country") or "").strip(),
                                  days_ahead=_int(a.get("days_ahead"), 90, 1, 365),
                                  limit=_int(a.get("limit"), 20, 1, 100))
            return {"ok": True, **data}
        return self._run(go, args)

    # member -----------------------------------------------------------------
    def get_trips(self, args: dict, **_kw) -> str:
        def go(a):
            for k in ("from_date", "to_date"):
                if a.get(k) and not _DATE_RE.match(str(a[k])):
                    raise NomadsError("invalid_date", f"{k} must be YYYY-MM-DD.")
            data = self.c.trips(from_date=a.get("from_date") or "", to_date=a.get("to_date") or "",
                                limit=_int(a.get("limit"), 50, 1, 1000))
            trips = [{**t, "nights": _nights(t)} for t in data.get("trips") or []]
            return {"ok": True, "username": data.get("username"), "total_trips": data.get("total_trips"),
                    "returned": len(trips), "trips": trips}
        return self._run(go, args)

    def get_favorites(self, args: dict, **_kw) -> str:
        def go(_a):
            data = self.c.favorites()
            return {"ok": True, "cities": data.get("cities") or [], "countries": data.get("countries") or []}
        return self._run(go, args)

    # composed ---------------------------------------------------------------
    def next_stay_brief(self, args: dict, **_kw) -> str:
        def go(a):
            today = date.today()
            if a.get("today"):
                if not _DATE_RE.match(str(a["today"])):
                    raise NomadsError("invalid_date", "today must be YYYY-MM-DD.")
                today = date.fromisoformat(a["today"])
            days_ahead = _int(a.get("days_ahead"), 60, 7, 365)
            max_cities = _int(a.get("max_cities"), 4, 1, brief_mod.MAX_CITIES)
            extra = [s for s in (_slug(x) for x in (a.get("cities") or []) if isinstance(a.get("cities"), list)) if s]
            include_favs = a.get("include_favorites", True) is not False
            warnings: list[str] = []

            trips = favorites = None
            if self.c.credentials.available():
                # Trips overlapping [today - 2y, horizon]; history for "been here before" lines.
                frm = (today - timedelta(days=730)).isoformat()
                to = (today + timedelta(days=days_ahead)).isoformat()
                trips = self.c.trips(from_date=frm, to_date=to, limit=500).get("trips") or []
                if include_favs:
                    try:
                        favorites = self.c.favorites().get("cities") or []
                    except NomadsError as exc:
                        warnings.append(f"Favorites unavailable: {exc.code}")
            elif not extra:
                raise NomadsError("nothing_to_plan",
                                  "No Nomads.com key is set, so there are no trips to plan from.",
                                  "Pass cities=[slug,...] for a public-data brief, or set NOMADS_API_KEY "
                                  "(https://nomads.com/settings) and the username setting.")
            else:
                warnings.append("No Nomads.com key set: brief uses public city data only (no trips, favorites or history).")

            try:  # one meetups call for the whole window, filtered per city locally
                meetups = self.c.meetups(days_ahead=days_ahead, limit=100).get("meetups") or []
            except NomadsError as exc:
                meetups = []
                warnings.append(f"Meetups unavailable: {exc.code}")

            return brief_mod.build_brief(today=today, days_ahead=days_ahead, max_cities=max_cities,
                                         trips=trips, favorites=favorites, extra_slugs=extra,
                                         fetch_city=self.c.city, meetups=meetups, warnings=warnings)
        return self._run(go, args)
