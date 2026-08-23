from __future__ import annotations

from prompt2render.textseg import norm_tokens, normalise_token


def test_mixed_algorithm_tokens_do_not_enter_numeric_converter():
    for token in ("n-1", "O(n)", "2D", "1-based", "v2"):
        assert normalise_token(token) != ""
        assert isinstance(normalise_token(token), str)


def test_numeric_tokens_are_still_spelled_for_alignment():
    assert normalise_token("42") == "forty two"
    assert normalise_token("1.5") == "one point five"
    assert "n-1" in norm_tokens("compare n-1 with 2")
