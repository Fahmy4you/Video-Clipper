"""Version-two selection: explicit time policy, candidate IDs and partial results."""

import hashlib
import json
import math
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from .db import Session, Project, ProposalSearch, HighlightProposal, HighlightRequest, Job
from .queue_runtime import checkpoint, read_checkpoint
from .router_ai import ContextLimit


class TimeRange(BaseModel):
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    fix_time: bool = True

    @model_validator(mode="after")
    def valid(self):
        if not 300 <= self.end_frame - self.start_frame <= 36000:
            raise ValueError("Durasi highlight harus 10 detik sampai 20 menit.")
        return self


class Selection(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=5)
    unmet_requests: list[str] = Field(default_factory=list, max_length=20)


def valid_candidate(raw, duration, timing, exclusions, rules_version=0):
    from .schemas import Highlight

    h = Highlight.model_validate(raw)
    if not h.title.strip() or not h.summary.strip() or not h.reason.strip():
        return None
    a, b = round(h.start * 30), round(h.end * 30)
    if not 0 <= a < b <= math.floor(duration * 30):
        return None
    if rules_version and not 300 <= b - a <= 36000:
        return None
    if timing:
        x, y = timing["start_frame"], timing["end_frame"]
        if timing["fix_time"]:
            if (a, b) != (x, y):
                return None
        elif abs(a - x) > 1800 or abs(b - y) > 1800 or a >= y or b <= x:
            return None
        if b - a < 30:
            return None
    elif duration < 30:
        if (a, b) != (0, math.floor(duration * 30)):
            return None
    elif not 900 <= b - a <= 2700:
        return None
    if any(a < end and b > start for start, end in exclusions):
        return None
    data = h.model_dump()
    data.update(start=a / 30, end=b / 30)
    data["candidate_id"] = hashlib.sha256(f"{a}:{b}".encode()).hexdigest()[:16]
    return data


def analyze(jid, pid, combo, count, prompt, payload, words, duration, identity, check, update):
    from . import proposal_searches as search
    from .schemas import Highlights

    Session = search.Session
    timing = payload.get("time_range")
    exclusions = payload.get("exclusions", [])
    policy = {
        "version": 2,
        "highlight_rules_version": payload.get("highlight_rules_version", 0),
        "count": count,
        "combo": combo,
        "prompt": prompt,
        "time_range": timing,
        "exclusions": exclusions,
        "transcript": identity,
    }
    signature = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    prefix = "v2:" + signature + ":"
    candidates, unmet = [], []

    def request(key, contents, schema):
        result = read_checkpoint(jid, prefix + key)
        if result is None:
            response = search.generate(
                combo,
                contents,
                {"response_schema": schema},
                check,
                lambda label: update(connection_label=label),
                schema.model_validate_json,
            )
            result = schema.model_validate_json(response.text).model_dump()
            checkpoint(jid, prefix + key, result)
        return result

    instructions = (
        search.PROMPT
        + """
Aturan waktu eksplisit menggantikan target 30–90 detik:
- fix_time=true: gunakan start_frame/30 dan end_frame/30 PERSIS.
- fix_time=false: tiap batas boleh bergeser maksimal 60 detik dan hasil harus
  beririsan dengan rentang acuan. Durasi eksplisit boleh di luar 30–90 detik.
- Sumber di bawah 30 detik tanpa rentang: gunakan seluruh sumber.
Jika topik tidak ditemukan, kembalikan clips kosong dan alasan spesifik.
Jika waktu tetap bertentangan dengan prompt, jangan ubah waktu atau mengarang isi.
"""
    )
    if payload.get("highlight_rules_version"):
        instructions += "\nSemua hasil wajib berdurasi 10 detik sampai 20 menit, termasuk rentang eksplisit dan fleksibel.\n"
    selected_words = words
    if timing:
        pad = 0 if timing["fix_time"] else 60
        lo = max(0, timing["start_frame"] / 30 - pad)
        hi = min(duration, timing["end_frame"] / 30 + pad)
        selected_words = [w for w in words if w["end"] > lo and w["start"] < hi]
    # Valid candidates from the previous attempt are reusable source analysis.
    reuse = payload.get("reuse_job_id")
    if reuse and not timing:
        with Session() as s:
            previous = s.get(Job, reuse)
            if previous and previous.payload.get("transcript_identity") == identity:
                old = previous.checkpoint or {}
                for key, value in old.items():
                    if isinstance(value, dict) and (
                        key.startswith("search:") or (key.startswith("v2:") and ":batch:" in key)
                    ):
                        candidates.extend(value.get("clips", []))
    if not candidates:
        portions = list(search.batches(search.compact_groups(selected_words)))

        def portion_request(portion, depth=0):
            key = "batch:" + hashlib.sha256(json.dumps(portion).encode()).hexdigest()
            contents = (
                instructions
                + "\n"
                + json.dumps(
                    {
                        "count": count,
                        "request": prompt,
                        "source_duration": duration,
                        "time_range": timing,
                        "excluded_ranges_seconds": [[a / 30, b / 30] for a, b in exclusions],
                        "transcript": portion,
                    },
                    ensure_ascii=False,
                )
            )
            try:
                return request(key, contents, Highlights)
            except ContextLimit:
                if depth >= 3 or len(portion) < 4 or (timing and timing["fix_time"]):
                    raise RuntimeError(
                        "Combo tidak dapat memuat rentang transkrip ini. Pilih combo berkapasitas konteks lebih besar."
                    )
                middle = len(portion) // 2
                results = [
                    portion_request(part, depth + 1)
                    for part in (portion[:middle], portion[middle:])
                ]
                return {
                    "clips": [h for r in results for h in r["clips"]],
                    "unmet_requests": [x for r in results for x in r.get("unmet_requests", [])],
                }

        for index, portion in enumerate(portions):
            check()
            update(
                stage="Mencari usulan melalui " + combo,
                progress=75,
                metrics={"analysis_batch": index + 1, "analysis_batches_total": len(portions)},
            )
            result = portion_request(portion)
            candidates.extend(result["clips"])
            unmet.extend(result.get("unmet_requests", []))

    valid = {}
    for raw in candidates:
        candidate = valid_candidate(
            raw, duration, timing, exclusions, payload.get("highlight_rules_version", 0)
        )
        if candidate:
            if (
                prompt.strip()
                and (not timing or not timing["fix_time"])
                and not candidate.get("fulfills_prompt")
            ):
                unmet.append("Kandidat yang ditemukan belum memenuhi arahan topik yang diminta.")
                continue
            valid[candidate["candidate_id"]] = candidate
    pool = list(valid.values())
    chosen = []

    def take(ids):
        for id in ids:
            if id not in valid or id in chosen:
                continue
            h = valid[id]
            if any(h["start"] < valid[x]["end"] and h["end"] > valid[x]["start"] for x in chosen):
                continue
            chosen.append(id)
            if len(chosen) >= count:
                break

    reason = ""

    def save_selected(complete=False):
        check()
        with Session() as s:
            project = s.scalar(select(Project).where(Project.id == pid).with_for_update())
            job = s.get(Job, jid)
            record = s.get(ProposalSearch, payload["search_id"])
            items = list(
                s.scalars(
                    select(HighlightRequest)
                    .where(HighlightRequest.id.in_(payload.get("request_item_ids", [])))
                    .order_by(HighlightRequest.number)
                    .with_for_update()
                )
            )
            if not record.completed:
                occupied = {
                    (p.start, p.end)
                    for item in items
                    if item.proposal_id
                    for p in [s.get(HighlightProposal, item.proposal_id)]
                    if p
                }
                occupied.update(
                    tuple(item.snapshot["deleted_range"])
                    for item in items
                    if item.deleted and item.snapshot.get("deleted_range")
                )
                remaining = iter(
                    [
                        id
                        for id in chosen
                        if (round(valid[id]["start"] * 30), round(valid[id]["end"] * 30))
                        not in occupied
                    ]
                )
                for item in items:
                    if item.deleted or item.proposal_id or item.job_id != jid:
                        continue
                    id = next(remaining, None)
                    if id:
                        h = valid[id]
                        a, b = round(h["start"] * 30), round(h["end"] * 30)
                        p = HighlightProposal(
                            project_id=pid,
                            search_id=record.id,
                            title=h["title"],
                            summary=h["summary"],
                            reason=h["reason"],
                            start=a,
                            end=b,
                            original_start=a,
                            original_end=b,
                            fulfills_prompt=h.get("fulfills_prompt", False),
                        )
                        s.add(p)
                        s.flush()
                        item.proposal_id = p.id
                        item.status = "fulfilled"
                        item.reason = ""
                    elif complete:
                        item.status = "unfulfilled"
                        item.reason = reason[:2000]
                    item.revision += 1
                record.completed = complete
                record.report = {
                    "requested": count,
                    "generated": len(chosen),
                    "unmet_requests": [reason] if reason else [],
                }
            project.analysis_report = record.report
            project.status = "review"
            job.checkpoint = {**job.checkpoint, "proposals_saved": complete, "candidate_pool": pool}
            s.commit()

    if len(pool) <= count:
        take([h["candidate_id"] for h in pool])
    else:

        def select_candidates(key, needed):
            return request(
                key,
                "Pilih ID kandidat terbaik. Jangan ubah rentang. Pilih sebanyak count jika tersedia kandidat tidak beririsan. Jelaskan kekurangan secara spesifik.\n"
                + json.dumps(
                    {
                        "count": needed,
                        "request": prompt,
                        "already_selected": chosen,
                        "candidates": pool,
                    },
                    ensure_ascii=False,
                ),
                Selection,
            )

        result = select_candidates("selection", count)
        take(result["ids"])
        unmet.extend(result["unmet_requests"])
        save_selected()
        if len(chosen) < count and not result["unmet_requests"]:
            # One real-work repair; never an unbounded prompt/test loop.
            result = select_candidates("repair", count - len(chosen))
            take(result["ids"])
            unmet.extend(result["unmet_requests"])

    reason = "; ".join(dict.fromkeys(unmet))
    if len(chosen) < count and not reason:
        reason = (
            "Seleksi AI belum memenuhi jumlah meskipun ada kandidat tersimpan. Coba analisis ulang."
            if len(pool) >= count
            else "Belum ditemukan cukup rentang valid yang memenuhi aturan permintaan."
        )
    save_selected(complete=True)
    with Session() as s:
        report = s.get(ProposalSearch, payload["search_id"]).report
    return {"message": "Usulan siap ditinjau.", **report}
