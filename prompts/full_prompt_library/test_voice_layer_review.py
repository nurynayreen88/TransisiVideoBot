"""Isolated review tests for the concept-independent voice layer."""
import importlib.util
from pathlib import Path

path = Path(__file__).with_name("voice_layer_review.py")
spec = importlib.util.spec_from_file_location("klippo_voice_review", path)
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)

def must_fail(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("Expected invalid selection to fail")

def test_voice_layer():
    assert len(voice.available_voice_choices(True)) == 3
    assert len(voice.available_voice_choices(False)) == 2
    assert "model_speech" not in voice.available_voice_choices(False)
    concept = "Vertical 9:16. Product: Periuk. LOCATION: home kitchen. ACTION: realistic cooking demonstration."
    a = voice.add_voice_to_complete_concept(concept, "model_speech", True, "Saya tunjukkan periuk ini.")
    b = voice.add_voice_to_complete_concept(concept, "background_narration", True, "Lihat penggunaan periuk ini.")
    c = voice.add_voice_to_complete_concept(concept, "background_narration", False, "Lihat bentuk periuk ini.")
    d = voice.add_voice_to_complete_concept(concept, "none", False, "")
    assert "synchronized lip movement" in a
    assert "stays silent" in b
    assert "No human appears" in c
    assert "No speech" in d
    assert all(x.count("AUDIO:") == 1 for x in (a, b, c, d))
    must_fail(lambda: voice.add_voice_to_complete_concept(concept, "model_speech", False, "Dialog"))
    must_fail(lambda: voice.add_voice_to_complete_concept(concept, "model_speech", True, ""))
    must_fail(lambda: voice.add_voice_to_complete_concept(a, "none", True, ""))

if __name__ == "__main__":
    test_voice_layer()
    print("Voice-layer review tests passed")
