import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    monkeypatch.delenv("WHISPER_PROFILE", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)


def test_standard_is_default_and_explicit_profile_has_priority():
    default = Settings(_env_file=None)
    assert (default.whisper_profile, default.whisper_model) == ("standard", "small")
    chosen = Settings(_env_file=None, whisper_profile="standard", whisper_model="base")
    assert (chosen.whisper_profile, chosen.whisper_model) == ("standard", "small")


@pytest.mark.parametrize(
    "values,expected",
    [
        ({"whisper_profile": "light"}, ("light", "base")),
        ({"whisper_model": "base"}, ("light", "base")),
        ({"whisper_model": "small"}, ("standard", "small")),
    ],
)
def test_legacy_model_and_manual_profiles(values, expected):
    chosen = Settings(_env_file=None, **values)
    assert (chosen.whisper_profile, chosen.whisper_model) == expected


def test_unknown_profile_is_not_silently_downgraded():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, whisper_profile="unknown")


def test_environment_profile_overrides_legacy_key(monkeypatch):
    monkeypatch.setenv("WHISPER_PROFILE", "standard")
    monkeypatch.setenv("WHISPER_MODEL", "base")
    chosen = Settings(_env_file=None)
    assert chosen.whisper_model == "small"
