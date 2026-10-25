"""Explicit review-only lookup for V9 cookware draft prompts.

Not imported by the production bot. Does not alter legacy prompt selection.
"""
import json
from pathlib import Path

_LIBRARY = Path(__file__).resolve().parent / "prompts" / "full_prompt_library"


def preview_cookware_prompt(concept, duration_seconds):
    """Return original draft text for manual QA, never runtime activation."""
    if duration_seconds not in (10, 20):
        raise ValueError("Unsupported duration")
    manifest = json.loads((_LIBRARY / "v9_cookware_shortlist_50_20261025.json").read_text(encoding="utf-8"))
    alias = json.loads((_LIBRARY / "v9_cookware_alias_review_20261025.json").read_text(encoding="utf-8"))
    if alias["status"] != "REVIEW_ONLY" or alias["master_id"] != "home_kitchen":
        raise ValueError("Alias is not in review mode")
    if manifest["status"] != "SHORTLIST_PENDING_PRODUCT_FIT_AND_RENDER_QA":
        raise ValueError("Shortlist is not in review mode")
    matches = [row for row in manifest["selected"] if row["concept"] == concept]
    if len(matches) != 1:
        raise ValueError("Concept not found or ambiguous")
    row = matches[0]
    source_path = _LIBRARY / Path(row["source_file"]).name
    source = json.loads(source_path.read_text(encoding="utf-8"))
    records = {item["id"]: item for item in source["variations"]}
    found = [records[key] for key in row["record_ids"] if records[key]["duration_seconds"] == duration_seconds]
    if len(found) != 1 or found[0]["status"] != "DRAFT_RENDER_QA":
        raise ValueError("Prompt is not a unique draft")
    return {"id": found[0]["id"], "concept": concept, "duration_seconds": duration_seconds,
            "full_prompt": found[0]["full_prompt"], "status": "DRAFT_RENDER_QA",
            "runtime_activated": False}
