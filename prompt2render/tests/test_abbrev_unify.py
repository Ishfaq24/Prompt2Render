"""Regression test: mathspeech (actual TTS input) and textseg (ASR-alignment
comparison form) must agree on how an abbreviation is spoken, since they used
to be two independently-maintained tables that silently drifted apart (e.g.
"JSON" was spelled out for synthesis but not for alignment)."""
from prompt2render import abbrev, mathspeech, textseg


def _spoken_via_synthesis(abbr: str) -> str:
    sentence = f"See {abbr} here."
    spoken = mathspeech.speech_text(sentence)
    return spoken[len("See "):-len(" here.")].lower()


def test_synthesis_and_alignment_agree_for_table_entries():
    for match, _spoken in abbrev.ABBREVIATIONS:
        if " " in match:
            continue  # multi-word entries aren't representable as one alignment token
        token = match.rstrip(".")
        synthesis_form = _spoken_via_synthesis(match)
        alignment_form = textseg.normalise_token(token).lower()
        assert synthesis_form == alignment_form, (
            f"{match!r}: synthesis said {synthesis_form!r}, "
            f"alignment expected {alignment_form!r}"
        )


def test_synthesis_and_alignment_agree_for_generic_fallback_acronyms():
    for acronym in ["NASA", "JSON", "DNA", "SQL", "PDF"]:
        synthesis_form = _spoken_via_synthesis(acronym)
        alignment_form = textseg.normalise_token(acronym).lower()
        assert synthesis_form == alignment_form, (
            f"{acronym!r}: synthesis said {synthesis_form!r}, "
            f"alignment expected {alignment_form!r}"
        )
