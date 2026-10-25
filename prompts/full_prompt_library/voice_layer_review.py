"""Klippo voice-layer prototype for future prompt_engine integration.

Keep concept/storyboard independent from audio selection. This module is not
wired to the production Telegram menu or prompt_engine.build_prompt yet.
"""
VOICE_MODEL = "model_speech"
VOICE_BACKGROUND = "background_narration"
VOICE_NONE = "none"

def available_voice_choices(human_model):
    return (VOICE_MODEL, VOICE_BACKGROUND, VOICE_NONE) if human_model else (VOICE_BACKGROUND, VOICE_NONE)

def render_voice_layer(voice, human_model, dialogue, *, music="soft instrumental background music"):
    if voice not in available_voice_choices(human_model):
        raise ValueError("Voice selection is incompatible with human model")
    if voice == VOICE_NONE:
        return "AUDIO: " + music + ". No speech, dialogue, voice-over or lip movement."
    if not isinstance(dialogue, str) or not dialogue.strip():
        raise ValueError("Selected speech requires complete Malaysian Malay dialogue")
    line = dialogue.strip().replace("\n", " ")
    if voice == VOICE_MODEL:
        return ('AUDIO: The on-camera Universal Malaysian model says in natural Malaysian Malay '
                'with accurate synchronized lip movement: “' + line + '” '
                + music + ' remains low beneath speech.')
    return ('AUDIO: An off-camera narrator says in natural Malaysian Malay: “' + line + '” '
            + ('The on-screen human model stays silent with no lip movement. ' if human_model
               else 'No human appears. ') + music + ' remains low beneath narration.')

def add_voice_to_complete_concept(concept_prompt, voice, human_model, dialogue):
    if not isinstance(concept_prompt, str) or not concept_prompt.strip():
        raise ValueError("A complete product-specific concept prompt is required")
    if "AUDIO:" in concept_prompt:
        raise ValueError("Concept already contains audio; remove its existing audio layer first")
    return concept_prompt.rstrip() + "\n" + render_voice_layer(voice, human_model, dialogue)
