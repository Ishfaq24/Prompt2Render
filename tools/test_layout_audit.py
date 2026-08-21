"""The layout critic's own test suite.

    python tools/test_layout_audit.py            # pass/fail summary
    python tools/test_layout_audit.py --write DIR  # also dump the frames as PNG

Two kinds of case, and the second kind is the one that matters.

BAD frames must be caught. That is the easy half: make the critic paranoid
enough and it catches everything.

GOOD frames must not be. A critic that fails a clean frame is worse than no
critic at all, because `prompt2render scenes` hands its complaint back to the model as
the thing to fix — so a false positive does not merely annoy, it spends API
calls teaching the model to avoid a layout that was fine, and can burn every
retry a section has before giving up on a frame that would have shipped.

The GOOD cases are therefore deliberately awkward: elements packed close,
arrows crossing what they point at, a register with a note beside it. If a
change to the audit trips one of these, the change is wrong.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt2render import scenekit as k        # noqa: E402


# ------------------------------------------------------------------ bad ----

def bad_dial_over_array(ax):
    k.title(ax, "dial drawn through an array")
    k.array(ax, [2, 5, 8, 12, 16, 23, 38, 45], y=4.5)
    k.dial(ax, 4, 8.0, 4.5, 2.6)


def bad_code_over_bits(ax):
    k.title(ax, "code panel over a bit row")
    k.bits(ax, "10011011", 8.0, 5.2, size=40)
    k.code(ax, ["x = 1", "y = 2"], x=8.0, y=5.6)


def bad_numberline_through_array(ax):
    k.title(ax, "number line ruled through an array")
    k.array(ax, [2, 5, 8, 12], y=5.0, idx=False)
    k.number_line(ax, -8, 7, 5.0)


def bad_table_in_curves(ax):
    k.title(ax, "table dropped inside the curves box")
    k.curves(ax, y=4.6, w=9.0, h=4.2)
    k.table(ax, [("1,000", "10")], headers=("size", "steps"), x=8.0, y=4.6)


def bad_register_over_caption(ax):
    k.title(ax, "register outline over a caption")
    k.register(ax, "10011011", 8.0, 2.0)
    k.caption(ax, "this caption is inside the register outline", y=2.0)


def bad_two_bit_rows_same_band(ax):
    """Two rows of boxes sharing a band. Note the digits do *not* collide —
    they interleave in each other's gaps — so the old glyph-only check saw
    nothing wrong here."""
    k.title(ax, "two bit rows in one horizontal band")
    k.bits(ax, "10011011", 7.0, 4.6, size=40)
    k.bits(ax, "01100100", 9.6, 4.6, size=40)


def bad_dial_into_title(ax):
    """r=2.6 needs a 7.4x7.4 box, and signed labels push it further still —
    at this centre the outer labels climb into the title band."""
    k.title(ax, "a dial whose labels reach the title")
    k.dial(ax, 4, 8.0, 4.3, 2.6, pointer=3, label_mode="signed")


def bad_addition_into_table(ax):
    k.title(ax, "a column sum landing on a table")
    k.addition(ax, "01101101", "00101011", "10011000", 5.0, 4.4)
    k.table(ax, [("a", "b"), ("c", "d")], headers=("x", "y"), x=5.5, y=4.4)


def bad_predicate_under_code(ax):
    k.title(ax, "predicate strip under a code block")
    k.predicate_strip(ax, [0, 0, 0, 1, 1, 1], y=4.6)
    k.code(ax, ["if pred(mid):", "    hi = mid"], x=8.0, y=4.6)


def bad_offframe_label(ax):
    k.title(ax, "a label pushed off the right edge")
    k.label(ax, 15.4, 4.5, "this label runs clean off the frame edge", size=30)


def bad_dial_offframe(ax):
    k.title(ax, "a dial that does not fit")
    k.dial(ax, 4, 13.6, 4.5, 3.4)


# ----------------------------------------------------------------- good ----

def good_array_annotated(ax):
    k.title(ax, "an ordinary annotated array")
    k.array(ax, [2, 5, 8, 12, 16, 23, 38, 45], y=4.6, lo=0, hi=7, mid=3,
            bracket="target is > 45")
    k.caption(ax, "eight sorted values")


def good_stacked_bands(ax):
    k.title(ax, "three elements in three bands")
    k.bits(ax, "10011011", 8.0, 6.4, size=34)
    k.array(ax, [2, 5, 8, 12, 16, 23], y=4.2)
    k.caption(ax, "each in its own horizontal band")


def good_arrow_touching_target(ax):
    """An arrow is meant to reach the thing it points at."""
    k.title(ax, "an arrow pointing into an array")
    px = k.array(ax, [2, 5, 8, 12, 16, 23], y=5.4)
    k.arrow(ax, px(2), 3.2, px(2), 4.6)
    k.caption(ax, "the arrow head lands on the box, by design")


def good_strike_through_bits(ax):
    k.title(ax, "a strike through a bit row")
    k.bits(ax, "10011011", 8.0, 4.6, size=40)
    k.strike(ax, 5.0, 11.0, 4.6)


def good_brace_under_bits(ax):
    k.title(ax, "a brace hanging off a bit row")
    c = k.bits(ax, "10011011", 8.0, 5.0, size=40)
    k.bit_brace(ax, c[0], c[3], 4.35, "the high nibble")


def good_register_with_note(ax):
    k.title(ax, "a register with its note beside it")
    k.register(ax, "10011011", 6.4, 4.6, note="one byte")


def good_addition_alone(ax):
    k.title(ax, "a column sum on its own")
    k.addition(ax, "01101101", "00101011", "10011000", 8.0, 4.4,
               carry="11011000", ok=True)


def good_curves_alone(ax):
    k.title(ax, "the curves box, filling its own space")
    k.curves(ax, y=4.4, w=9.0, h=4.2)


def good_dial_alone(ax):
    k.title(ax, "a dial with the room it asks for")
    k.dial(ax, 4, 8.0, 4.1, 2.5, pointer=3)


def good_code_and_caption(ax):
    k.title(ax, "code above, caption below")
    k.code(ax, ["while lo <= hi:", "    mid = (lo + hi) // 2",
                "    if a[mid] == t:", "        return mid"], y=4.8)
    k.caption(ax, "the loop, in four lines")


def good_table_and_caption(ax):
    k.title(ax, "a table with a caption under it")
    k.table(ax, [("1,000", "10"), ("1,000,000", "20")],
            headers=("size", "steps"), y=5.0, col_w=[5.0, 3.0])
    k.caption(ax, "doubling the input costs one more step")


def good_number_line_alone(ax):
    k.title(ax, "a signed number line")
    k.number_line(ax, -8, 7, 4.6, marks={-8: ("min", k.BAD),
                                         7: ("max", k.GOOD)})


def good_predicate_alone(ax):
    k.title(ax, "the predicate strip")
    k.predicate_strip(ax, [0, 0, 0, 1, 1, 1], y=4.6, note="the boundary is the answer")


CASES = [(n, fn) for n, fn in sorted(globals().items())
         if n.startswith(("bad_", "good_")) and callable(fn)]


def run(write: Path | None = None) -> int:
    failures = []
    for name, fn in CASES:
        fig, ax = k.canvas()
        fn(ax)
        fails = [p for p in k.audit(fig, ax, name) if p.level == "fail"]
        want_fail = name.startswith("bad_")
        ok = bool(fails) == want_fail
        if write:
            write.mkdir(parents=True, exist_ok=True)
            k.save(fig, write / f"{'PASS' if ok else 'WRONG'}_{name}.png")
        else:
            k.close(fig)
        mark = "ok  " if ok else "WRONG"
        detail = ""
        if not ok:
            detail = ("  <- should have been caught" if want_fail
                      else f"  <- false positive: {fails[0].message[:100]}")
            failures.append(name)
        print(f"  [{mark}] {name}{detail}")

    bad = sum(1 for n, _ in CASES if n.startswith("bad_"))
    good = len(CASES) - bad
    print(f"\n{len(CASES)} cases: {bad} that must be caught, "
          f"{good} that must not be.")
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("all correct.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", type=Path, default=None,
                    help="also write each frame as a PNG here, for eyeballing")
    sys.exit(run(ap.parse_args().write))
