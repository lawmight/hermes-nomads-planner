import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    if "nomads_planner" in sys.modules:
        return sys.modules["nomads_planner"]
    spec = importlib.util.spec_from_file_location("nomads_planner", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nomads_planner"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def pkg():
    _load()
    import nomads_planner.client as client  # noqa: F401
    import nomads_planner.tools as tools  # noqa: F401
    import nomads_planner.brief as brief  # noqa: F401
    return sys.modules["nomads_planner"]


class FakeResp:
    def __init__(self, body, status=200):
        self._b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status

    def read(self):
        return self._b


class FakeHTTP:
    """Routes requests by path prefix; records every Request for assertions."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        path = req.full_url.split("nomads.com", 1)[1]
        for prefix, payload in self.routes.items():
            if path.startswith(prefix):
                if isinstance(payload, Exception):
                    raise payload
                if callable(payload):
                    payload = payload(req)
                if isinstance(payload, tuple):
                    body, status = payload
                    if status >= 400:
                        raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(json.dumps(body).encode()))
                    return FakeResp(body, status)
                return FakeResp(payload)
        raise AssertionError(f"unexpected request {path}")


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.tools, self.commands, self.skills = {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **kw}

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler

    def register_skill(self, name, path, **kw):
        self.skills[name] = Path(path)


@pytest.fixture
def fake_http():
    return FakeHTTP


@pytest.fixture
def fake_ctx():
    return FakeCtx
