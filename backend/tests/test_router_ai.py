import json
import time
import httpx
import pytest
from app import router_ai as ai
from app.media import write_json


def transport(monkeypatch, handler):
    calls = []

    def handle(request):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(
        ai, "client", lambda config, timeout=15: httpx.Client(transport=httpx.MockTransport(handle))
    )
    return calls


def test_configuration_changes_without_restart_and_empty_never_reuses_key():
    old = ai.configuration()
    ai.ENV_PATH.write_text("9router_base_url=http://localhost:20128/v1\n9router_key=replacement\n")
    assert ai.configuration().key == "replacement"
    assert ai.configuration().identity != old.identity
    ai.ENV_PATH.write_text("9router_base_url=http://localhost:20128/v1\n9router_key=\n")
    with pytest.raises(ai.ConfigError):
        ai.configuration()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/key",
        "http://secret:pw@localhost/v1",
        "http://localhost",
        "https://localhost/v1?key=x",
    ],
)
def test_invalid_router_url_is_rejected(url):
    ai.ENV_PATH.write_text("9router_base_url=" + url + "\n9router_key=test\n")
    with pytest.raises(ai.ConfigError):
        ai.configuration()


def test_metadata_refresh_uses_only_get_and_deduplicates_combos(monkeypatch):
    calls = transport(
        monkeypatch,
        lambda r: httpx.Response(
            200,
            json={
                "data": [
                    {"id": "All", "owned_by": "combo"},
                    {"id": "All", "owned_by": "combo"},
                    {"id": "gemini/model", "owned_by": "gemini"},
                ]
            },
        ),
    )
    ai._refresh(ai.configuration())
    assert len(calls) == 1 and calls[0].method == "GET" and calls[0].url.path == "/v1/models"
    assert [m["id"] for m in ai.snapshot(update=False)["models"]] == ["All"]


def test_failed_refresh_preserves_complete_catalog(monkeypatch):
    calls = transport(monkeypatch, lambda r: httpx.Response(503))
    ai._refresh(ai.configuration())
    result = ai.snapshot(update=False)
    assert result["models"][0]["id"] == "All-Combos"
    assert result["connections"][0]["error"]
    assert len(calls) == 1


def test_generation_sends_real_work_once_and_keeps_selected_combo(monkeypatch):
    calls = transport(
        monkeypatch,
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": '{"clips":[]}'}}]}),
    )
    result = ai.generate(
        "All-Combos",
        "Transkrip sebenarnya",
        {"response_schema": {"type": "object"}},
        validate=json.loads,
    )
    assert json.loads(result.text) == {"clips": []}
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert (
        payload["model"] == "All-Combos"
        and "Transkrip sebenarnya" in payload["messages"][0]["content"]
    )
    assert "test-only" not in payload["messages"][0]["content"]


@pytest.mark.parametrize("status,kind", [(429, "waiting_quota"), (503, "waiting_service")])
def test_provider_wait_does_not_try_models_or_keys(monkeypatch, status, kind):
    calls = transport(monkeypatch, lambda r: httpx.Response(status, headers={"retry-after": "120"}))
    with pytest.raises(ai.ProviderWait) as error:
        ai.generate("All-Combos", "work", {})
    assert len(calls) == 1 and error.value.kind == kind and error.value.retry_after == 120
    assert "harian" not in error.value.reason


def test_bad_json_is_stage_failure_without_extra_generation(monkeypatch):
    calls = transport(
        monkeypatch,
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "invalid"}}]}),
    )
    with pytest.raises(RuntimeError, match="skema JSON"):
        ai.generate("All-Combos", "work", {})
    assert len(calls) == 1


def test_old_gemini_job_requires_explicit_combo(monkeypatch):
    calls = transport(monkeypatch, lambda r: httpx.Response(500))
    with pytest.raises(ai.ConfigError, match="Pekerjaan lama"):
        ai.generate("gemini-old", "work", {})
    assert not calls


def test_catalog_and_validation_never_send_generation(monkeypatch):
    calls = transport(monkeypatch, lambda r: httpx.Response(500))
    ai.validate_model("All-Combos")
    assert ai.snapshot()["models"]
    assert not calls


def test_configured_credentials_do_not_imply_connection():
    config = ai.configuration()
    write_json(ai.cache_path(config), {"version": 1, "error": "Unreachable", "models": []})
    status = ai.connection_status(ai.snapshot(update=False))
    assert status["configured"] is True and status["connected"] is False
    assert status["connection_status"] == "unavailable"


def test_successful_empty_catalog_is_still_connected():
    config = ai.configuration()
    write_json(ai.cache_path(config), {"version": 1, "fetched_at": time.time(), "models": []})
    status = ai.connection_status(ai.snapshot(update=False))
    assert status["connected"] is True and status["connection_status"] == "connected"


def test_failed_refresh_does_not_report_old_cache_as_connected(monkeypatch):
    transport(monkeypatch, lambda r: httpx.Response(503))
    ai._refresh(ai.configuration())
    catalog = ai.snapshot(update=False)
    status = ai.connection_status(catalog)
    assert catalog["models"] and status["connected"] is False
    assert status["connection_status"] == "unavailable"


def test_wsl_loopback_connection_error_explains_windows_host(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(ai.platform, "release", lambda: "6.6-microsoft-standard-WSL2")
    config = replace(ai.configuration(), url="http://localhost:20128/v1")
    message = ai.connection_error(config)
    assert "WSL" in message and "localhost mengarah ke Ubuntu" in message
    assert config.key not in message
    other = replace(config, url="http://172.20.240.1:20128/v1")
    assert "localhost" not in ai.connection_error(other)
