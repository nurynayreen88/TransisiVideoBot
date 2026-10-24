"""Concept-first review smoke tests, separate from the live bot."""
import importlib.util
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
from concept_composer_review import compose_concept

concept = dict(id="kitchen_cookware_01", category="kitchen_cookware",
               setting="real home kitchen", action="an adult demonstrates cooking with the actual pot",
               camera="stable medium view followed by a restrained detail push",
               lighting="soft natural window light", opening="show the complete pot on a stable hob",
               development="show a realistic cooking action with safe hand placement",
               finish="end with the complete pot clearly framed",
               continuation="follow the same cooking motion into a close product detail",
               second_development="show a different genuine angle of the cooking demonstration",
               second_finish="finish on a full-product hero view")

def check():
    a = compose_concept(concept, "Periuk", 10, True, "adult", "model_speech",
                        "Saya tunjukkan penggunaan periuk ini.")
    assert len(a) == 1 and a[0].count("AUDIO:") == 1
    assert "synchronized lip movement" in a[0]
    b = compose_concept(concept, "Periuk", 20, False, None, "background_narration",
                        "Ini paparan periuk.", "Mari lihat sudut seterusnya.")
    assert len(b) == 2 and all(x.count("AUDIO:") == 1 for x in b)
    assert "Continue the exact final frame" in b[1]
    assert "Ini paparan periuk." in b[0] and "Mari lihat sudut seterusnya." in b[1]
    c = compose_concept(concept, "Periuk", 10, False, None, "none")
    assert "No speech" in c[0]
    try:
        compose_concept(concept, "Periuk", 10, False, None, "model_speech", "Dialog")
    except ValueError:
        pass
    else:
        raise AssertionError("Model speech must be rejected without a human model")

if __name__ == "__main__":
    check()
    print("Concept composer review smoke tests passed")
