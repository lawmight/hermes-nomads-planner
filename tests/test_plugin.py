import re
import json
from datetime import date

import pytest

from fixtures import CITY, FAVS, MEETUPS, TRIPS, city_route

SECRET = "s3cr3t-key-value"


def make(pkg, fake_http, routes, secret=SECRET, username="alice"):
    from nomads_planner.client import Credentials, NomadsClient
    from nomads_planner.tools import Handlers
    calls = []

    def get_secret(name):
        calls.append(name)
        return secret

    creds = Credentials(get_config=lambda k, d=None: {"username": username}.get(k, d), get_secret=get_secret)
    http = fake_http(routes)
    return Handlers(NomadsClient(creds, opener=http)), http, calls


ROUTES = {"/api/city/": city_route, "/api/trips": TRIPS, "/api/favorites": FAVS, "/api/meetups": MEETUPS,
          "/api/search": {"total_matching": 1, "returned": 1, "cities": [CITY["lisbon-portugal"]]},
          "/api/top": {"returned": 2, "cities": [CITY["lisbon-portugal"], CITY["tbilisi-georgia"]]},
          "/api/country/": {"slug": "portugal", "name": "Portugal", "cities_count": 16, "top_cities": []}}


# ---- registration / manifest -------------------------------------------------

def test_register_matches_manifest(pkg, fake_ctx):
    import yaml
    from pathlib import Path
    manifest = yaml.safe_load((Path(pkg.__file__).parent / "plugin.yaml").read_text())
    ctx = fake_ctx()
    pkg.register(ctx)
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"])
    assert manifest["provides_hooks"] == []
    assert set(ctx.commands) == {"nomads"}
    assert set(ctx.skills) == {"nomads-trip-planner"} and ctx.skills["nomads-trip-planner"].exists()
    for name, t in ctx.tools.items():
        assert t["schema"]["name"] == name and t["toolset"] == "nomads"
        assert t["schema"]["parameters"]["type"] == "object"


def test_no_os_environ_or_file_reads_in_plugin_code(pkg):
    from pathlib import Path
    root = Path(pkg.__file__).parent
    for f in root.glob("*.py"):
        src = f.read_text()
        assert "os.environ" not in src and "getenv" not in src, f
        assert ".env" not in src, f
        assert re.search(r"(?<![\w.])open\(", src) is None, f  # no builtin file open()


def test_no_write_methods(pkg):
    from pathlib import Path
    src = (Path(pkg.__file__).parent / "client.py").read_text()
    for verb in ('"POST"', '"PATCH"', '"DELETE"', '"PUT"'):
        assert verb not in src


# ---- credentials / request shaping -------------------------------------------

def test_member_call_uses_secret_scope_and_bearer_header(pkg, fake_http):
    h, http, calls = make(pkg, fake_http, ROUTES)
    out = json.loads(h.get_trips({"limit": 2}))
    assert out["ok"] and out["returned"] == 5 and out["trips"][0]["nights"] == 21
    assert calls == ["NOMADS_API_KEY"]
    req = http.requests[0]
    assert req.get_method() == "GET"
    assert req.get_header("Authorization") == f"Bearer alice:{SECRET}"
    assert SECRET not in req.full_url and "key=" not in req.full_url
    assert "limit=2" in req.full_url
    assert "Mozilla" in req.get_header("User-agent")
    assert SECRET not in json.dumps(out)


def test_secret_in_username_colon_key_form(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES, secret="bob:" + SECRET, username="")
    json.loads(h.get_favorites({}))
    assert http.requests[0].get_header("Authorization") == f"Bearer bob:{SECRET}"


def test_missing_key_is_clean_error_and_public_tools_still_work(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES, secret=None)
    err = json.loads(h.get_trips({}))
    assert err == {"ok": False, "error": "missing_key", "detail": err["detail"], "hint": err["hint"]}
    assert "nomads.com/settings" in err["hint"]
    assert http.requests == []  # no network call without a key
    city = json.loads(h.get_city({"slug": "lisbon-portugal"}))
    assert city["ok"] and city["city"]["name"] == "Lisbon"
    assert "Authorization" not in dict(http.requests[0].header_items())
    assert "sponsor" not in city


def test_missing_username(pkg, fake_http):
    h, _, _ = make(pkg, fake_http, ROUTES, username="")
    assert json.loads(h.get_trips({}))["error"] == "missing_username"


def test_secret_scope_error_is_wrapped(pkg, fake_http):
    from nomads_planner.client import Credentials, NomadsClient
    from nomads_planner.tools import Handlers

    def boom(name):
        raise RuntimeError("unscoped")
    h = Handlers(NomadsClient(Credentials(lambda k, d=None: "alice", boom), opener=fake_http(ROUTES)))
    assert json.loads(h.get_favorites({}))["error"] == "secret_unavailable"


def test_invalid_key_and_rate_limit_and_city_not_found(pkg, fake_http):
    routes = dict(ROUTES)
    routes["/api/trips"] = {"error": "invalid_username_or_key", "detail": "Get your key at https://nomads.com/settings"}
    routes["/api/search"] = ({"error": "too_many"}, 429)
    h, _, _ = make(pkg, fake_http, routes)
    assert json.loads(h.get_trips({}))["error"] == "invalid_username_or_key"
    rl = json.loads(h.search_cities({"country": "Portugal"}))
    assert rl["error"] == "rate_limited" and rl["http_status"] == 429
    assert json.loads(h.get_city({"slug": "nowhere-zz"}))["error"] == "city_not_found"


def test_input_validation(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES)
    assert json.loads(h.get_city({"slug": "../etc/passwd"}))["error"] == "invalid_slug"
    assert json.loads(h.get_trips({"from_date": "yesterday"}))["error"] == "invalid_date"
    assert json.loads(h.get_city("not a dict"))["error"] == "invalid_slug"
    assert http.requests == []


def test_search_filters_vs_top_and_cache(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES)
    out = json.loads(h.search_cities({"country": "Portugal", "max_cost_usd": 3000, "limit": 5}))
    assert out["returned"] == 1
    assert "country=Portugal" in http.requests[0].full_url and "max_cost_usd=3000" in http.requests[0].full_url
    json.loads(h.search_cities({}))
    assert http.requests[1].full_url.endswith("/api/top")
    json.loads(h.get_city({"slug": "lisbon-portugal"}))
    json.loads(h.get_city({"slug": "lisbon-portugal"}))
    assert sum("/api/city/" in r.full_url for r in http.requests) == 1  # cached


def test_member_data_never_cached(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES)
    h.get_trips({}); h.get_trips({})
    assert sum("/api/trips" in r.full_url for r in http.requests) == 2


def test_network_error(pkg, fake_http):
    import urllib.error
    h, _, _ = make(pkg, fake_http, {"/api/city/": urllib.error.URLError("down")})
    assert json.loads(h.get_city({"slug": "lisbon-portugal"}))["error"] == "network_error"


# ---- composed brief ------------------------------------------------------------

def test_next_stay_brief_composes(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES)
    b = json.loads(h.next_stay_brief({"today": "2026-11-10", "days_ahead": 60, "max_cities": 4}))
    assert b["ok"]
    tl = b["timeline"]
    assert [c["city"] for c in tl["current"]] == ["Tbilisi"]
    assert [u["city"] for u in tl["upcoming"]] == ["Lisbon", "Somewhere", "Chiang Mai"]
    # Tbilisi to 11-15, Lisbon 11-20..12-05, Somewhere 12-06..12-08, Chiang Mai 12-20..
    assert tl["unplanned_gaps"] == [{"from": "2026-11-16", "to": "2026-11-19", "days": 4},
                                    {"from": "2026-12-09", "to": "2026-12-19", "days": 11}]
    slugs = [(c["slug"], c["why"]) for c in b["cities"]]
    assert slugs == [("tbilisi-georgia", "current_stay"), ("lisbon-portugal", "upcoming_trip"),
                     ("chiang-mai-thailand", "upcoming_trip"), ("bali-indonesia", "favorite")]
    lis = b["cities"][1]
    assert lis["stay"] == {"from": "2026-11-20", "to": "2026-12-05", "nights": 15}
    assert [m["name"] for m in lis["meetups"]] == ["Cowork day"]  # 11-12 meetup is outside the stay
    assert lis["your_history"] == {"past_stays": 1, "past_nights": 30, "last_left": "2026-03-31"}
    assert lis["facts"]["cost_for_nomad_usd_per_month"] == 4740 and "neighborhoods" not in lis["facts"]
    assert [m["name"] for m in b["cities"][0]["meetups"]] == ["Coffee"]
    assert b["cities"][3]["facts"] is None and any("bali-indonesia" in w for w in b["warnings"])
    assert any("Somewhere" in w for w in b["warnings"])
    cmp = {c["metric"]: (c["city"], c["value"]) for c in b["comparisons"]}
    assert cmp["cost_for_nomad_usd_per_month"] == ("chiang-mai-thailand", 1300)
    assert cmp["internet_mbps"] == ("lisbon-portugal", 95)
    assert cmp["safety_score_0_to_5"] == ("tbilisi-georgia", 4.5)
    assert "| Lisbon | upcoming trip | 4740 |" in b["summary_markdown"]
    assert sum("/api/meetups" in r.full_url for r in http.requests) == 1
    assert SECRET not in json.dumps(b)


def test_brief_is_deterministic(pkg, fake_http):
    h1, _, _ = make(pkg, fake_http, ROUTES)
    h2, _, _ = make(pkg, fake_http, ROUTES)
    a = {"today": "2026-11-10"}
    assert h1.next_stay_brief(a) == h2.next_stay_brief(a)


def test_brief_public_only_without_key(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES, secret=None)
    b = json.loads(h.next_stay_brief({"today": "2026-11-10", "cities": ["lisbon-portugal", "chiang-mai-thailand"]}))
    assert b["ok"] and [c["why"] for c in b["cities"]] == ["requested", "requested"]
    assert not any("/api/trips" in r.full_url for r in http.requests)
    assert any("public city data only" in w for w in b["warnings"])
    err = json.loads(h.next_stay_brief({}))
    assert err["error"] == "nothing_to_plan"


def test_brief_rate_limit_stops_city_lookups(pkg, fake_http):
    routes = dict(ROUTES)
    routes["/api/city/"] = ({"error": "x"}, 429)
    h, http, _ = make(pkg, fake_http, routes)
    b = json.loads(h.next_stay_brief({"today": "2026-11-10"}))
    assert b["ok"] and len(b["cities"]) == 1
    assert sum("/api/city/" in r.full_url for r in http.requests) == 1


def test_brief_caps_max_cities(pkg, fake_http):
    h, http, _ = make(pkg, fake_http, ROUTES)
    b = json.loads(h.next_stay_brief({"today": "2026-11-10", "max_cities": 2}))
    assert len(b["cities"]) == 2


# ---- slash command --------------------------------------------------------------

def test_slash_command(pkg, fake_http, fake_ctx, monkeypatch):
    from nomads_planner import _make_command
    h, _, _ = make(pkg, fake_http, ROUTES)
    cmd = _make_command(h)
    assert "Lisbon, Portugal" in cmd("city lisbon-portugal")
    assert "Latest 5 of 5" in cmd("trips")
    assert "Usage" in cmd("bogus")
    assert "Cowork day" in cmd("meetups lisbon-portugal")
    h2, _, _ = make(pkg, fake_http, ROUTES, secret=None)
    assert "missing_key" in _make_command(h2)("trips")


# ---- real Hermes secret scope (runs when Hermes is importable) ---------------

def test_default_credentials_read_hermes_secret_scope(pkg, fake_http, monkeypatch):
    secret_scope = pytest.importorskip("agent.secret_scope")
    from nomads_planner.client import Credentials, NomadsClient
    from nomads_planner.tools import Handlers
    monkeypatch.delenv("NOMADS_API_KEY", raising=False)
    http = fake_http(ROUTES)
    h = Handlers(NomadsClient(Credentials(get_config=lambda k, d=None: {"username": "alice"}.get(k, d)), opener=http))
    assert json.loads(h.get_trips({}))["error"] == "missing_key"
    token = secret_scope.set_secret_scope({"NOMADS_API_KEY": "scoped-key"})
    try:
        assert json.loads(h.get_trips({}))["ok"]
    finally:
        secret_scope.reset_secret_scope(token)
    assert http.requests[-1].get_header("Authorization") == "Bearer alice:scoped-key"


def test_multiplex_without_scope_fails_closed(pkg, fake_http, monkeypatch):
    secret_scope = pytest.importorskip("agent.secret_scope")
    from nomads_planner.client import Credentials, NomadsClient
    from nomads_planner.tools import Handlers
    monkeypatch.setenv("NOMADS_API_KEY", "other-profile-key")
    h = Handlers(NomadsClient(Credentials(get_config=lambda k, d=None: "alice"), opener=fake_http(ROUTES)))
    token = secret_scope.set_multiplex_context(True)
    try:
        out = json.loads(h.get_trips({}))
    finally:
        secret_scope.reset_multiplex_context(token)
    assert out["error"] == "secret_unavailable"
