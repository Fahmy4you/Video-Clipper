import time
import pytest
from app import router_ai
from app.media import write_json


@pytest.fixture(autouse=True)
def private_router(tmp_path, tmp_path_factory, monkeypatch):
    isolated = tmp_path_factory.mktemp("router-fixture")
    env = isolated / ".env"
    env.write_text("9router_base_url=http://127.0.0.1:20128/v1\n9router_key=test-only-not-real\n")
    monkeypatch.setattr(router_ai, "ENV_PATH", env)
    monkeypatch.setattr(router_ai, "STORAGE", isolated)
    config = router_ai.configuration()
    cache = router_ai.cache_path(config)
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        cache,
        {
            "version": 1,
            "fetched_at": time.time(),
            "models": [{"id": "All-Combos", "name": "All-Combos"}],
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must provide a fake 9Router transport")

    monkeypatch.setattr(router_ai, "client", forbidden)
    yield
