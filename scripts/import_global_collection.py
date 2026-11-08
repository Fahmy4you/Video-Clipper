"""Idempotent reviewed Global footage import. No automatic overwrite of existing assets."""

import argparse, json, hashlib, math, os, re, shutil
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from app.db import Session, VideoClip, Hashtag, Clip
from app.config import STORAGE
from app.video_library import Metadata, folder, prepare, info
from app.queue_runtime import add_library, wake
from app.hashtags import normalize_tags


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def source_key(a):
    provider = a.get("provider", "tiktok")
    if provider == "tiktok" and re.fullmatch(r"\d+", a["source_id"]):
        return "https://www.tiktok.com/video/" + a["source_id"]
    if provider == "youtube" and re.fullmatch(r"[A-Za-z0-9_-]{11}", a["source_id"]):
        return "https://www.youtube.com/watch?v=" + a["source_id"]
    raise ValueError("Invalid source provider or ID")


def validate_entry(a):
    source_key(a)
    if not re.fullmatch(r"[a-z0-9][A-Za-z0-9_-]{0,210}\.mp4", a["filename"]):
        raise ValueError("Invalid managed filename")
    if a["sha256"] != digest(a["file"]):
        raise ValueError("Source checksum changed")
    if not a.get("reviewed"):
        raise ValueError("Visual review required")
    if not a["scenes"]:
        raise ValueError("At least one curated scene required")
    body = Metadata(
        title=a["title"],
        hashtags=a["hashtags"],
        explain=a["explain"],
        scenes=a["scenes"],
        scope="global",
        instansi_ids=[],
        revision=1,
    )
    previous = 0
    end = math.floor(a["duration"] * 30)
    for scene in body.scenes:
        if scene.start < previous or scene.end > end:
            raise ValueError("Scene overlaps or exceeds duration")
        if any(
            scene.start < x["end"] and scene.end > x["start"] for x in a.get("excluded_ranges", [])
        ):
            raise ValueError("Scene includes excluded closing")
        previous = scene.end
    return body


def existing_snapshot():
    with Session() as s:
        return {
            "videos": [
                {"data": info(v), "sha256": digest(STORAGE / v.url_path)}
                for v in s.scalars(select(VideoClip))
            ],
            "highlights": [
                {"id": c.id, "revision": c.revision, "plan": c.plan, "legacy_plan": c.legacy_plan}
                for c in s.scalars(select(Clip))
            ],
        }


def perform(manifest_path, commit=False):
    manifest_path = Path(manifest_path)
    entries = json.loads(manifest_path.read_text())
    root = manifest_path.parent
    before_path = root / "before-import.json"
    if commit and not before_path.exists():
        before_path.write_text(json.dumps(existing_snapshot(), ensure_ascii=False, indent=2))
    with Session() as s:
        existing = {digest(STORAGE / v.url_path): v.id for v in s.scalars(select(VideoClip))}
    results = []
    pending = []
    for a in entries:
        body = validate_entry(a)
        aid = str(uuid5(NAMESPACE_URL, source_key(a)))
        result = {"index": a["index"], "source_id": a["source_id"], "url": a["url"], "id": aid}
        if a["sha256"] in existing:
            aid = existing[a["sha256"]]
            result.update(
                id=aid,
                status="existing",
                message="Identical source retained; metadata not overwritten",
            )
            with Session() as s:
                v = s.get(VideoClip, aid)
                if (
                    commit
                    and v.status in ("failed", "queued")
                    and aid == str(uuid5(NAMESPACE_URL, source_key(a)))
                    and v.revision == 1
                    and v.scope == "global"
                ):
                    pending.append(aid)
            results.append(result)
            continue
        with Session() as s:
            v = s.get(VideoClip, aid)
            if v:
                raise ValueError(
                    "Stable source ID already exists with different bytes; review manually"
                )
        if not commit:
            result["status"] = "would_import"
            results.append(result)
            continue
        dest = folder(aid)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / a["filename"]
        canonical = dest / "source.media"
        if target.exists():
            if digest(target) != a["sha256"]:
                raise ValueError("Staged target collision")
        else:
            shutil.copy2(a["file"], target)
        if digest(target) != a["sha256"]:
            raise ValueError("Copy checksum mismatch")
        if canonical.exists():
            if digest(canonical) != a["sha256"]:
                raise ValueError("Canonical source collision")
        else:
            os.link(target, canonical)
        (dest / "import-source.json").write_text(
            json.dumps(
                {
                    k: a[k]
                    for k in (
                        "url",
                        "source_id",
                        "sha256",
                        "filename",
                        "uncertainty_notes",
                        "excluded_ranges",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        with Session() as s:
            tags = {t.name_tag: t for t in s.scalars(select(Hashtag))}
            for name in body.hashtags:
                if name not in tags:
                    tags[name] = Hashtag(name_tag=name)
                    s.add(tags[name])
            s.add(
                VideoClip(
                    id=aid,
                    title=body.title,
                    url_path=str(target.relative_to(STORAGE)),
                    scope="global",
                    instansi_records=[],
                    tag_records=[tags[t] for t in body.hashtags],
                    explain=body.explain,
                    scenes=[x.model_dump() for x in body.scenes],
                    duration=a["duration"],
                    width=a["width"],
                    height=a["height"],
                    status="queued",
                )
            )
            s.flush()
            add_library(s, aid)
            s.commit()
        existing[a["sha256"]] = aid
        pending.append(aid)
        result["status"] = "imported"
        results.append(result)
        (root / "import-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print("IMPORTED", a["index"], body.title, flush=True)
    if commit:
        with Session() as s:
            for aid in set(pending):
                add_library(s, aid)
            s.commit()
        if pending:
            wake()
        with Session() as s:
            for r in results:
                v = s.get(VideoClip, r["id"])
                r["asset_status"] = v.status
                r["error"] = v.error
        (root / "import-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("RESULT", len(results), flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    perform(args.manifest, args.commit)
