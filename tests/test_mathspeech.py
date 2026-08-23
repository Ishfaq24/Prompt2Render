from prompt2render.mathspeech import equation_to_speech, speech_text


def test_inline_math_does_not_say_dollar():
    spoken = speech_text("The complexity is $O(n)$.")
    assert "dollar" not in spoken.lower()
    assert "oh n" in spoken.lower() or "o n" in spoken.lower()


def test_common_math_operators_are_spoken():
    spoken = speech_text(r"$x^2 + y^2 = z^2$")
    assert "squared" in spoken
    assert "plus" in spoken
    assert "equals" in spoken


def test_currency_is_not_treated_as_math_delimiter():
    spoken = speech_text("The fee is $5.")
    assert "5" in spoken
    assert "dollar" not in spoken.lower()


def test_fraction_is_spoken_conservatively():
    spoken = equation_to_speech(r"\\frac{a}{b}")
    assert "over" in spoken
    assert "a" in spoken and "b" in spoken

def test_abbreviation_expansion():
    from prompt2render.mathspeech import speech_text
    assert speech_text("The CPU and GPU are fast.") == "The C P U and G P U are fast."
    assert speech_text("e.g. this is an API") == "for example this is an A P I"
    assert speech_text("We use RAM, i.e. memory.") == "We use ram, that is memory."
