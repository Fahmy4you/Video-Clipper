"""Compatibility URLs now expose the 9Router combo catalog."""

from .router_ai import snapshot, schedule, validate_model


def available_models(refresh=False):
    if refresh:
        schedule(force=True)
    return snapshot()["models"]


def known_models():
    return {m["id"] for m in snapshot(update=False)["models"]}
