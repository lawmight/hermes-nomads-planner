"""nomads-planner — native Hermes plugin for Nomads.com (read-only).

Registers seven tools, one slash command (/nomads) and one bundled skill.
Network: HTTPS GET to https://nomads.com/api/* only.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schemas
from .client import Credentials, NomadsClient
from .tools import Handlers

TOOLSET = "nomads"
_EMOJI = "🧳"


def _make_command(h: Handlers):
    usage = ("Usage: /nomads brief [days] | /nomads trips | /nomads city <slug> | "
             "/nomads meetups <city-slug> | /nomads top")

    def command(raw_args: str = "", **_kw) -> str:
        parts = (raw_args or "").split()
        sub, rest = (parts[0].lower(), parts[1:]) if parts else ("brief", [])
        if sub == "brief":
            args = {"days_ahead": int(rest[0])} if rest and rest[0].isdigit() else {}
            res = json.loads(h.next_stay_brief(args))
            return res.get("summary_markdown") or _explain(res)
        if sub == "trips":
            res = json.loads(h.get_trips({"limit": 10}))
            if not res.get("ok"):
                return _explain(res)
            rows = [f"- {t['city']}, {t['country']}: {t['date_start'][:10]} → {t['date_end'][:10]} ({t['nights']}n)"
                    for t in res["trips"]]
            return f"Latest {len(rows)} of {res.get('total_trips')} Nomads.com trips:\n" + "\n".join(rows)
        if sub == "city" and rest:
            res = json.loads(h.get_city({"slug": rest[0]}))
            if not res.get("ok"):
                return _explain(res)
            c = res["city"]
            return (f"{c['name']}, {c['country']} — score {c.get('overall_score')}, "
                    f"${c.get('cost_for_nomad_usd_per_month')}/mo nomad cost, {c.get('internet_mbps')} Mbps, "
                    f"{c.get('temperature_c_now')}°C now, safety {c.get('safety_score_0_to_5')}/5 · {c.get('url')}")
        if sub == "meetups" and rest:
            res = json.loads(h.list_meetups({"city": rest[0], "limit": 10}))
            if not res.get("ok"):
                return _explain(res)
            ms = res.get("meetups") or []
            if not ms:
                return f"No upcoming Nomads.com meetups in {rest[0]} in the next {res.get('days_ahead', 90)} days."
            return "\n".join(f"- {m['date']} {m.get('local_time', '')} · {m['name']} @ {m.get('venue', '')} "
                             f"({m.get('people_going')} going)" for m in ms)
        if sub == "top":
            res = json.loads(h.search_cities({"limit": 10}))
            if not res.get("ok"):
                return _explain(res)
            return "\n".join(f"{i}. {c['name']}, {c['country']} ({c.get('overall_score')})"
                             for i, c in enumerate(res["cities"], 1))
        return usage

    return command


def _explain(res: dict) -> str:
    msg = f"Nomads.com: {res.get('error', 'error')}"
    if res.get("detail"):
        msg += f" — {res['detail']}"
    if res.get("hint"):
        msg += f"\n{res['hint']}"
    return msg


def register(ctx) -> None:
    creds = Credentials(get_config=ctx.get_config)
    h = Handlers(NomadsClient(creds))

    for schema, handler in (
        (schemas.SEARCH_CITIES, h.search_cities),
        (schemas.GET_CITY, h.get_city),
        (schemas.GET_COUNTRY, h.get_country),
        (schemas.LIST_MEETUPS, h.list_meetups),
        (schemas.GET_TRIPS, h.get_trips),
        (schemas.GET_FAVORITES, h.get_favorites),
        (schemas.NEXT_STAY_BRIEF, h.next_stay_brief),
    ):
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji=_EMOJI)

    ctx.register_command("nomads", _make_command(h),
                         description="Nomads.com: next-stay brief, trips, city facts, meetups",
                         args_hint="[brief [days] | trips | city <slug> | meetups <slug> | top]")

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            ctx.register_skill(child.name, child / "SKILL.md")
