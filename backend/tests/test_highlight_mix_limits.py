from uuid import uuid4
from copy import deepcopy
import pytest
from fastapi import HTTPException
from app.highlight_limits import MixBudget
from app.review import validate_range, VideoSettings
from app.mix_generation import validate_suggestions, modern_prompt
from app.timeline import EditPlanV2


@pytest.mark.parametrize("length", [300, 36000])
def test_inclusive_highlight_limits(length):
    validate_range(0, length, 2000)


@pytest.mark.parametrize("start,end", [(0, 299), (0, 36001), (-1, 300), (60000, 60300)])
def test_invalid_highlight_ranges(start, end):
    with pytest.raises(HTTPException):
        validate_range(start, end, 1800)


def test_partial_minute_and_cross_boundary_coverage():
    budget = MixBudget(2100)
    assert budget.accept(1770, 1860)
    assert not budget.accept(1920, 2010)
    short = MixBudget(300)
    assert not short.accept(60, 210)
    assert short.accept(60, 150)
    assert not short.accept(180, 270)


def test_automatic_five_and_manual_lower_limit():
    for maximum, count in [(None, 5), (2, 2)]:
        budget = MixBudget(1800, maximum)
        assert sum(budget.accept(60 + i * 180, 150 + i * 180) for i in range(7)) == count


def test_twenty_minute_capacity_is_not_capped_to_one_batch():
    budget = MixBudget(36000)
    assert (
        sum(
            budget.accept(m * 1800 + 60 + i * 180, m * 1800 + 150 + i * 180)
            for m in range(20)
            for i in range(5)
        )
        == 100
    )


def test_new_mix_minimum_and_old_job_compatibility():
    asset = str(uuid4())
    library = [{"id": asset, "frames": 600}]
    plan = EditPlanV2(segments=[{"id": "s", "source_in": 0, "duration": 300}]).model_dump()
    item = {"asset_id": asset, "start": 60, "end": 120, "source_in": 0, "reason": "relevan"}
    assert validate_suggestions(deepcopy(plan), [item], library)["segments"][0]["broll"]
    assert not validate_suggestions(deepcopy(plan), [item], library, 1)["segments"][0]["broll"]
    item["end"] = 150
    assert validate_suggestions(deepcopy(plan), [item], library, 1)["segments"][0]["broll"]


def test_podcast_normalizes_density_and_prompt_consistency():
    assert VideoSettings(visual_mode="podcast", mix_max_per_minute=4).mix_max_per_minute is None
    assert VideoSettings(visual_mode="mix", mix_max_per_minute=3).mix_max_per_minute == 3
    assert "2 sampai 5" not in modern_prompt()


def test_one_insert_crossing_internal_segments_counts_once():
    asset = str(uuid4())
    library = [{"id": asset, "frames": 600}]
    plan = EditPlanV2(
        segments=[
            {"id": "a", "source_in": 0, "duration": 120},
            {"id": "b", "source_in": 120, "duration": 180},
        ]
    ).model_dump()
    item = {"asset_id": asset, "start": 60, "end": 150, "reason": "relevan"}
    result = validate_suggestions(plan, [item], library, 1, 1)
    pieces = [b for s in result["segments"] for b in s["broll"]]
    assert len(pieces) == 2
    assert sum(b["end"] - b["start"] for b in pieces) == 90


def test_new_candidate_bounds_keep_legacy_snapshots():
    from app.search_selection import valid_candidate

    def candidate(end):
        return {
            "start": 0,
            "end": end,
            "title": "Judul",
            "summary": "Ringkasan",
            "reason": "Alasan",
        }

    timing = {"start_frame": 0, "end_frame": 30, "fix_time": True}
    assert valid_candidate(candidate(1), 100, timing, [], 0)
    assert valid_candidate(candidate(1), 100, timing, [], 1) is None
    timing = {"start_frame": 0, "end_frame": 36000, "fix_time": True}
    assert valid_candidate(candidate(1200), 2000, timing, [], 1)
    timing["end_frame"] = 36001
    assert valid_candidate(candidate(36001 / 30), 2000, timing, [], 1) is None
