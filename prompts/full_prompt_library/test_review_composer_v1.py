"""Review-only compatibility tests; run locally before any engine integration."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("review_composer", ROOT / "review_composer_v1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
compose = module.compose_review_prompt
Error = module.PromptChoiceError

def rejected(record, **kwargs):
    try:
        compose(record, product_name="Sample product", **kwargs)
    except Error:
        return
    raise AssertionError("Invalid choice unexpectedly accepted")

def test_pet_choices():
    data = json.loads((ROOT / "review_pet_batch01.json").read_text(encoding="utf-8"))
    assert data["review_only"] and len(data["variations"]) == 20
    ids = [v["variant_id"] for v in data["variations"]]
    assert len(ids) == len(set(ids))
    for v in data["variations"]:
        human = v["model"] != "none"
        opts = dict(human_model=human, age_range="adult" if human else None,
                    voice_type=v["voice_type"], animal=v["animal_required"])
        result = compose(v, product_name="Sample product", **opts)
        assert len(result["prompts"]) == 2
        assert all("{{" not in p for p in result["prompts"])
        assert all(v["animal_required"] in p for p in result["prompts"])
        rejected(v, **{**opts, "animal": None})
        rejected(v, **{**opts, "animal": "fish" if v["animal_required"] != "fish" else "cat"})
        rejected(v, **{**opts, "voice_type": "none"})
        if human:
            rejected(v, **{**opts, "age_range": None})
        else:
            rejected(v, **{**opts, "voice_type": "model_speech"})
            rejected(v, **{**opts, "age_range": "adult"})

def test_v4_choices():
    records = []
    for i in range(1, 6):
        data = json.loads((ROOT / ("review_v4_batch04_part_%02d.json" % i)).read_text(encoding="utf-8"))
        assert data["review_only"] and data["count"] == 20
        records.extend(data["variations"])
    assert len(records) == len({v["variant_id"] for v in records}) == 100
    assert sum(v["duration_seconds"] == 10 for v in records) == 50
    assert sum(v["duration_seconds"] == 20 for v in records) == 50
    for v in records:
        human = v["model"] != "none"
        opts = dict(human_model=human, age_range="adult" if human else None,
                    voice_type=v["voice_type"])
        result = compose(v, product_name="Sample product", **opts)
        assert len(result["prompts"]) == v["duration_seconds"] // 10
        assert all("{{" not in p for p in result["prompts"])
        rejected(v, **{**opts, "human_model": not human})
        if not human:
            rejected(v, **{**opts, "voice_type": "model_speech"})

if __name__ == "__main__":
    test_pet_choices()
    test_v4_choices()
    print("Review composer compatibility checks passed")
