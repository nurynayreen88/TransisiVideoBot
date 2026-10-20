#!/usr/bin/env python3
"""Non-destructive structural and repetition audit for Klippo's variation library."""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

FIELDS = ("hook", "action", "detail", "camera", "lighting", "closing", "audio")
DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / "prompts/subcategory_variation_library.json"


def audit(data):
    errors, flags = [], []
    subs = data.get("subcategories")
    if not isinstance(subs, list) or not subs:
        return {"errors": ["subcategories must be a non-empty list"], "flags": [], "stats": {}}
    sub_ids, variation_ids = set(), set()
    total = 0
    repeat_slots = 0
    for sub in subs:
        sid = str(sub.get("subcategory_id", "")).strip()
        if not sid:
            errors.append("subcategory missing subcategory_id")
        if sid in sub_ids:
            errors.append(f"duplicate subcategory_id: {sid}")
        sub_ids.add(sid)
        variations = sub.get("variations")
        if not isinstance(variations, list) or not variations:
            errors.append(f"{sid}: variations must be a non-empty list")
            continue
        if sub.get("variation_count") is not None and sub["variation_count"] != len(variations):
            errors.append(f"{sid}: declared variation_count differs from actual")
        minimum = data.get("minimum_variations_per_subcategory")
        if isinstance(minimum, int) and len(variations) < minimum:
            errors.append(f"{sid}: only {len(variations)} variations; minimum is {minimum}")
        for field in ("hook", "detail", "audio"):
            values = Counter()
            for index, v in enumerate(variations, 1):
                value = v.get(field)
                if isinstance(value, str) and value.strip():
                    values[re.sub(r"\\s+", " ", value.strip().lower())] += 1
            if values:
                repeat_slots += 1
                top = values.most_common(1)[0]
                if top[1] >= 8:
                    flags.append(f"{sid}: {field} repeats {top[1]}/{len(variations)} times; review whether boilerplate limits variety")
        for index, v in enumerate(variations, 1):
            total += 1
            vid = str(v.get("id", "")).strip()
            if not vid:
                errors.append(f"{sid} variation {index}: missing id")
            elif vid in variation_ids:
                errors.append(f"duplicate variation id: {vid}")
            variation_ids.add(vid)
            for field in FIELDS:
                value = v.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{sid}/{vid or index}: missing or empty {field}")
            audio = v.get("audio", "")
            if isinstance(audio, str) and re.match(r"^AUDIO:\\s*AUDIO:", audio, re.I):
                errors.append(f"{sid}/{vid}: duplicated AUDIO prefix in audio field")
            action = v.get("action", "")
            if isinstance(action, str) and len(action.split()) < 6:
                flags.append(f"{sid}/{vid}: unusually short action; check whether it is actionable")
            detail = v.get("detail", "")
            if isinstance(detail, str) and re.search(r"educational toy pieces\\b", detail, re.I):
                flags.append(f"{sid}/{vid}: possible toy-detail grammar issue")
    return {"errors": errors, "flags": flags, "stats": {
        "subcategories": len(subs), "variations": total,
        "unique_variation_ids": len(variation_ids), "field_slots_checked": total * len(FIELDS),
        "repetition_review_flags": sum("repeats " in f for f in flags),
        "review_flags": len(flags),
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(json.loads(args.library.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Klippo subcategory library audit")
        for key, value in result["stats"].items():
            print(f"- {key.replace('_', ' ').title()}: {value}")
        print(f"- Hard errors: {len(result['errors'])}")
        for item in result["errors"]:
            print(f"ERROR: {item}")
        for item in result["flags"]:
            print(f"REVIEW: {item}")
        print("Review flags are triage hints, not automatic proof of poor quality.")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
