"""next_stay_brief: join trips, favorites, city facts and meetups into one planning brief.

Pure and deterministic: every number in the brief is copied from a Nomads.com response or
counted from the member's own trip dates. No invented scores, prices or rankings.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Optional

from .client import NomadsError

# Curated city fields carried into the brief (as returned by GET /api/city/{slug}).
FACT_FIELDS = (
    "name", "country", "region", "url", "overall_score",
    "cost_for_nomad_usd_per_month", "rent_1br_center_usd_per_month", "coworking_usd_per_month",
    "internet_mbps", "temperature_c_now", "humidity_now", "air_quality_now",
    "safety_score_0_to_5", "walkability_score_0_to_5", "healthcare_score_0_to_5",
    "english_speaking_score_0_to_5", "has_remote_work_visa",
)

# "Which candidate is lowest/highest on X" — plain sorts on API numbers.
COMPARE = (
    ("cost_for_nomad_usd_per_month", "lowest", "lowest monthly cost for a nomad (USD)"),
    ("internet_mbps", "highest", "fastest internet (Mbps)"),
    ("safety_score_0_to_5", "highest", "highest safety score (0-5)"),
    ("overall_score", "highest", "highest Nomads.com overall score"),
    ("air_quality_now", "lowest", "best air quality right now (lowest AQI)"),
)

MAX_CITIES = 8


def _d(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _nights(t: dict) -> int:
    a, b = _d(t.get("date_start")), _d(t.get("date_end"))
    return max((b - a).days, 0) if a and b else 0


def classify_trips(trips: list[dict], today: date, days_ahead: int) -> dict:
    horizon = today + timedelta(days=days_ahead)
    current, upcoming, past = [], [], []
    for t in trips:
        a, b = _d(t.get("date_start")), _d(t.get("date_end"))
        if not a or not b:
            continue
        if a <= today <= b:
            current.append(t)
        elif today < a <= horizon:
            upcoming.append(t)
        elif b < today:
            past.append(t)
    upcoming.sort(key=lambda t: t["date_start"])
    past.sort(key=lambda t: t["date_end"], reverse=True)
    return {"current": current, "upcoming": upcoming, "last": past[0] if past else None, "horizon": horizon}


def unplanned_gaps(trips: list[dict], today: date, horizon: date) -> list[dict]:
    """Date ranges in [today, horizon] with no trip on the calendar."""
    spans = sorted((max(_d(t["date_start"]), today), min(_d(t["date_end"]), horizon))
                   for t in trips if _d(t.get("date_start")) and _d(t.get("date_end"))
                   and _d(t["date_end"]) >= today and _d(t["date_start"]) <= horizon)
    gaps, cursor = [], today
    for a, b in spans:
        if a > cursor:
            gaps.append((cursor, a - timedelta(days=1)))
        cursor = max(cursor, b + timedelta(days=1))
    if cursor <= horizon:
        gaps.append((cursor, horizon))
    return [{"from": a.isoformat(), "to": b.isoformat(), "days": (b - a).days + 1} for a, b in gaps]


def history_by_city(trips: list[dict], today: date) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in trips:
        slug = t.get("city_slug")
        b = _d(t.get("date_end"))
        if not slug or not b or b >= today:
            continue
        h = out.setdefault(slug, {"past_stays": 0, "past_nights": 0, "last_left": None})
        h["past_stays"] += 1
        h["past_nights"] += _nights(t)
        if h["last_left"] is None or t["date_end"] > h["last_left"]:
            h["last_left"] = t["date_end"][:10]
    return out


def build_brief(*, today: date, days_ahead: int, max_cities: int,
                trips: Optional[list[dict]], favorites: Optional[list[dict]],
                extra_slugs: list[str], fetch_city: Callable[[str], dict],
                meetups: list[dict], warnings: list[str]) -> dict[str, Any]:
    trips = trips or []
    cls = classify_trips(trips, today, days_ahead)
    history = history_by_city(trips, today)

    # Candidate order: where you are, where you're going, cities you asked about, favorites.
    candidates: list[tuple[str, str, Optional[dict]]] = []
    seen: set[str] = set()

    def add(slug: str, why: str, trip: Optional[dict] = None):
        if slug and slug not in seen and len(candidates) < max_cities:
            seen.add(slug)
            candidates.append((slug, why, trip))

    for t in cls["current"]:
        if t.get("city_slug"):
            add(t["city_slug"], "current_stay", t)
        else:
            warnings.append(f"Current stay in {t.get('city') or 'an unlisted place'} has no Nomads.com city page.")
    for t in cls["upcoming"]:
        if t.get("city_slug"):
            add(t["city_slug"], "upcoming_trip", t)
        else:
            warnings.append(f"Trip to {t.get('city') or 'an unlisted place'} ({t.get('date_start')}) has no Nomads.com city page.")
    for s in extra_slugs:
        add(s, "requested")
    for f in favorites or []:
        add(f.get("slug", ""), "favorite")

    horizon = cls["horizon"]
    by_city: dict[str, list[dict]] = {}
    for m in meetups:
        by_city.setdefault(m.get("city_slug") or "", []).append(m)

    cities = []
    for slug, why, trip in candidates:
        entry: dict[str, Any] = {"slug": slug, "why": why}
        if trip:
            entry["stay"] = {"from": trip.get("date_start", "")[:10], "to": trip.get("date_end", "")[:10],
                             "nights": _nights(trip)}
        try:
            facts = (fetch_city(slug) or {}).get("city") or {}
            entry["facts"] = {k: facts.get(k) for k in FACT_FIELDS if k in facts}
        except NomadsError as exc:
            entry["facts"] = None
            warnings.append(f"City facts for {slug} unavailable: {exc.code}")
            if exc.code == "rate_limited":
                cities.append(entry)
                warnings.append("Stopped city lookups after a rate limit; retry later for the rest.")
                break
        # Meetups: inside the stay window for trips, otherwise anywhere in the horizon.
        lo = _d(entry["stay"]["from"]) if trip else today
        hi = _d(entry["stay"]["to"]) if trip else horizon
        lo, hi = max(lo or today, today), min(hi or horizon, horizon)
        ms = [m for m in by_city.get(slug, []) if (d := _d(m.get("date"))) and lo <= d <= hi]
        entry["meetups"] = [{k: m.get(k) for k in ("name", "date", "local_time", "venue", "people_going", "url")}
                            for m in sorted(ms, key=lambda m: (m.get("date", ""), m.get("local_time", "")))]
        if slug in history:
            entry["your_history"] = history[slug]
        cities.append(entry)

    comparisons = []
    with_facts = [c for c in cities if c.get("facts")]
    if len(with_facts) >= 2:
        for field, direction, label in COMPARE:
            vals = [(c["facts"][field], c["slug"], c["facts"].get("name") or c["slug"]) for c in with_facts
                    if isinstance(c["facts"].get(field), (int, float)) and not isinstance(c["facts"].get(field), bool)]
            if len(vals) < 2:
                continue
            best = min(vals) if direction == "lowest" else max(vals)
            comparisons.append({"metric": field, "label": label, "city": best[1], "name": best[2], "value": best[0],
                                "compared": len(vals)})

    timeline = {
        "today": today.isoformat(), "horizon": horizon.isoformat(),
        "current": [_trip_line(t) for t in cls["current"]],
        "upcoming": [_trip_line(t) for t in cls["upcoming"]],
        "last_trip": _trip_line(cls["last"]) if cls["last"] else None,
        "unplanned_gaps": unplanned_gaps(cls["current"] + cls["upcoming"], today, horizon) if trips else [],
    }
    brief = {"ok": True, "timeline": timeline, "cities": cities, "comparisons": comparisons,
             "warnings": warnings, "source": "Data from Nomads.com — https://nomads.com"}
    brief["summary_markdown"] = render_markdown(brief, member=trips is not None and bool(trips))
    return brief


def _trip_line(t: dict) -> dict:
    return {"city": t.get("city"), "country": t.get("country"), "city_slug": t.get("city_slug") or None,
            "from": str(t.get("date_start", ""))[:10], "to": str(t.get("date_end", ""))[:10], "nights": _nights(t)}


def _fmt(v: Any, unit: str = "") -> str:
    return "n/a" if v is None else f"{v}{unit}"


def render_markdown(brief: dict, member: bool) -> str:
    tl = brief["timeline"]
    lines = [f"# Next-stay brief ({tl['today']} → {tl['horizon']})"]
    if member:
        if tl["current"]:
            c = tl["current"][0]
            lines.append(f"**Now:** {c['city']}, {c['country']} until {c['to']}.")
        elif tl["last_trip"]:
            lt = tl["last_trip"]
            lines.append(f"**Last logged stay:** {lt['city']}, {lt['country']} (left {lt['to']}).")
        if tl["upcoming"]:
            lines.append("**Upcoming:** " + "; ".join(f"{u['city']} {u['from']}→{u['to']} ({u['nights']}n)" for u in tl["upcoming"]))
        else:
            lines.append("**Upcoming:** nothing logged on Nomads.com in this window.")
        for g in tl["unplanned_gaps"]:
            lines.append(f"**Unplanned:** {g['from']} → {g['to']} ({g['days']} days)")
    lines.append("")
    lines.append("| City | Why | Cost/mo (USD) | Internet | Temp now | Safety | Meetups |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in brief["cities"]:
        f = c.get("facts") or {}
        name = f.get("name") or c["slug"]
        lines.append(f"| {name} | {c['why'].replace('_', ' ')} | {_fmt(f.get('cost_for_nomad_usd_per_month'))} | "
                     f"{_fmt(f.get('internet_mbps'), ' Mbps')} | {_fmt(f.get('temperature_c_now'), '°C')} | "
                     f"{_fmt(f.get('safety_score_0_to_5'))} | {len(c.get('meetups') or [])} |")
    for c in brief["cities"]:
        for m in (c.get("meetups") or [])[:3]:
            lines.append(f"- Meetup in {(c.get('facts') or {}).get('name') or c['slug']}: {m['name']} — {m['date']} {m.get('local_time') or ''}, {m.get('venue') or ''} ({m.get('people_going')} going)")
    for cmp in brief["comparisons"]:
        lines.append(f"- {cmp['label'][0].upper() + cmp['label'][1:]}: {cmp['name']} ({cmp['value']})")
    for w in brief["warnings"]:
        lines.append(f"- ⚠ {w}")
    lines.append("\n_Data from Nomads.com — https://nomads.com_")
    return "\n".join(lines)
