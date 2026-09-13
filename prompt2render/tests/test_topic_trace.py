"""Tests for topic detection and algorithm trace injection."""
from prompt2render.topic_trace import detect_and_trace, _extract_array, _extract_target


def test_detects_bubble_sort():
    result = detect_and_trace("Show bubble sort on [5, 3, 1, 4, 2]", "")
    assert result is not None
    assert "PRE-COMPUTED ALGORITHM TRACE" in result
    assert "bubble" in result.lower()


def test_detects_binary_search():
    result = detect_and_trace("Binary search for 23 in sorted array", "")
    assert result is not None
    assert "binary_search" in result.lower()


def test_detects_gcd():
    result = detect_and_trace("Euclidean algorithm for GCD of 252 and 105", "")
    assert result is not None
    assert "gcd" in result.lower() or "euclid" in result.lower()


def test_unrecognised_topic_returns_none():
    result = detect_and_trace("Explain TCP handshake", "")
    assert result is None


def test_extract_array_finds_list():
    arr = _extract_array("Sort the array [8, 3, 5, 1, 9]")
    assert arr == [8, 3, 5, 1, 9]


def test_extract_array_returns_none_on_no_list():
    assert _extract_array("Sort an array of numbers") is None


def test_extract_target_from_brief():
    target = _extract_target("Binary search for 42 in the array")
    assert target == 42


def test_custom_array_used_in_trace():
    result = detect_and_trace("Bubble sort [9, 7, 5, 3, 1]", "")
    assert result is not None
    # The custom array values should appear in the trace
    assert "9" in result


def test_trace_contains_json_steps():
    result = detect_and_trace("bubble sort on an array", "")
    assert result is not None
    # Should contain at least one valid JSON object (a step)
    assert "{" in result and "type" in result
