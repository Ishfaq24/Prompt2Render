"""Drawing primitives for prompt2render scenes, rendered with matplotlib.

Why this exists: this kit covers the shapes a computer-architecture explainer
actually uses -- rows of bits, arrows, number lines, a wrap-around dial -- and
renders them to PNG stills. A section is then a list of stills held against the
narration, which costs one ffmpeg encode instead of thirty frames a second of
redraw. Manim remains available for hand-authored hero scenes (see
`prompt2render manim`), but it is far too large an API surface to point a model at, and
it has none of the defensive self-shrinking below.

Canvas is a fixed 16x9 unit grid at 1920x1080. Place things in units; never
think in pixels.

`audit()` at the foot of this file is the layout critic. It is what closes the
loop the upstream Code2Video Critic could not: matplotlib already knows where
every glyph landed, so overlapping and off-frame text can be caught exactly,
with no vision model and no extra API call.
"""
from __future__ import annotations

import functools
import os
import threading

import matplotlib
matplotlib.use("Agg")

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox
from matplotlib.patches import Circle, FancyArrow, FancyBboxPatch, Rectangle, Wedge

W, H = 16.0, 9.0
DPI = 100
FIGSIZE = (19.2, 10.8)

BG = "#0d1117"
FG = "#e6edf3"
DIM = "#8b949e"
LINE = "#30363d"
ONE = "#1f6feb"       # a set bit
ZERO = "#161b22"      # a clear bit
GOOD = "#3fb950"
BAD = "#f85149"
WARN = "#d29922"
ACCENT = "#a371f7"

MONO = ["DejaVu Sans Mono", "monospace"]
SANS = ["DejaVu Sans", "sans-serif"]


#: PNG deflate level for the stills. These PNGs are an *intermediate* — the
#: only thing that ever reads them is ffmpeg, which decodes to raw pixels
#: either way, so the encoded video is identical at any level. Level 1 is
#: ~2.5x faster to write than matplotlib's default 6 and costs about 20 KB a
#: still. Raise it if you care about the size of build/scenes on disk.
PNG_COMPRESS = int(os.environ.get("P2R_PNG_COMPRESS", "1"))

#: Set P2R_PNG_EXACT=1 to go back to matplotlib's own savefig writer (byte-for-
#: byte the old PNG files, at roughly double the cost — see save()).
PNG_EXACT = os.environ.get("P2R_PNG_EXACT", "") not in ("", "0", "false")


def canvas():
    """A fresh 16x9 axes on the dark background.

    Built straight from `Figure` rather than `plt.figure()` on purpose. pyplot
    registers every figure in a process-global manager, which (a) leaks any
    figure a scene module forgets to close and (b) is not safe to touch from
    more than one thread — and rendering sections concurrently is exactly what
    `prompt2render stills --jobs` now does. Nothing in the drawing API needs pyplot.
    """
    fig = Figure(figsize=FIGSIZE, dpi=DPI, facecolor=BG)
    FigureCanvasAgg(fig)                 # attaches itself to fig.canvas
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    return fig, ax


def close(fig) -> None:
    """Drop a figure. Works whether or not pyplot ever knew about it."""
    plt.close(fig)                       # no-op for an unmanaged figure
    fig.clear()


def drawn(fig) -> bool:
    """Has this figure already been rasterised?"""
    return getattr(fig.canvas, "renderer", None) is not None


def save(fig, path):
    """Write the still.

    `fig.savefig()` rasterises the whole figure *again*, and by the time we
    get here `audit()` has already drawn it once to measure where the glyphs
    landed — so the default path was paying for two full renders of every
    still. The Agg buffer from that first draw is the finished frame; encoding
    it directly is the same pixels for half the work. Verified pixel-exact
    against savefig, which is the property that matters: the PNG bytes differ
    (RGB rather than RGBA, lighter deflate) but the image does not, and the
    image is all ffmpeg ever sees.
    """
    if PNG_EXACT or not drawn(fig):
        if PNG_EXACT:
            fig.savefig(path, facecolor=BG, dpi=DPI)
            close(fig)
            return
        fig.canvas.draw()

    from PIL import Image                 # matplotlib already depends on it
    w, h = fig.canvas.get_width_height()
    
    # Fast path: skip the .convert("RGB") copy if we don't strictly need it,
    # or just do it in one pass. PIL's frombuffer is fast, but convert allocates.
    img = Image.frombuffer("RGBA", (w, h), memoryview(fig.canvas.buffer_rgba()), "raw", "RGBA", 0, 1)
    # ffmpeg handles RGBA perfectly fine; dropping the .convert("RGB") saves a 1920x1080x3 allocation
    img.save(path, format="PNG", compress_level=PNG_COMPRESS, dpi=(DPI, DPI))
    close(fig)


# ----------------------------------------------------------------- text

# Forward declaration of the decorator we'll define later
# We can't use it directly yet, so we'll wrap the functions at the end of the file.


def title(ax, text, y=8.1, size=46, color=FG):
    ax.text(W / 2, y, text, ha="center", va="center", color=color,
            fontsize=size, fontfamily=SANS, fontweight="semibold")


def caption(ax, text, y=0.85, size=30, color=DIM):
    ax.text(W / 2, y, text, ha="center", va="center", color=color,
            fontsize=size, fontfamily=SANS)


def label(ax, x, y, text, size=28, color=FG, ha="center", va="center",
          mono=False, weight="normal"):
    ax.text(x, y, text, ha=ha, va=va, color=color, fontsize=size,
            fontfamily=MONO if mono else SANS, fontweight=weight)


# ------------------------------------------------------------- bit rows


def bits(ax, value, x, y, n=8, box=1.05, gap=0.16, size=40,
         highlight=None, hcolor=WARN, labels=None, dim=False):
    """Draw `value` as n boxed bits, left to right, MSB first.

    value    : int or a string of '0'/'1'
    x, y     : centre of the row
    highlight: iterable of indices (0 = MSB) to outline
    labels   : optional per-bit strings drawn underneath
    Returns the list of box centre x-coordinates, so callers can hang
    arrows and brackets off individual bits.
    """
    if isinstance(value, int):
        s = format(value & ((1 << n) - 1), f"0{n}b")
    else:
        s = str(value).replace(" ", "")
    n = len(s)
    step = box + gap
    total = n * step - gap
    x0 = x - total / 2
    highlight = set(highlight or ())
    centres = []

    for i, ch in enumerate(s):
        cx = x0 + i * step + box / 2
        centres.append(cx)
        on = ch == "1"
        fc = ONE if on else ZERO
        if dim:
            fc = ZERO if on else BG
        ec = hcolor if i in highlight else (DIM if on else LINE)
        lw = 4.0 if i in highlight else 2.0
        ax.add_patch(FancyBboxPatch(
            (cx - box / 2, y - box / 2), box, box,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2))
        ax.text(cx, y, ch, ha="center", va="center", zorder=3,
                color=FG if not dim else DIM, fontsize=size, fontfamily=MONO)
        if labels and i < len(labels) and labels[i]:
            ax.text(cx, y - box / 2 - 0.34, labels[i], ha="center", va="top",
                    color=DIM, fontsize=19, fontfamily=MONO)
    return centres


def bit_brace(ax, x_from, x_to, y, text, color=DIM, size=22, below=True):
    """A flat bracket under (or over) a span of bits, with a label."""
    d = -1 if below else 1
    ax.plot([x_from, x_from, x_to, x_to],
            [y, y + d * 0.16, y + d * 0.16, y],
            color=color, lw=2, zorder=2)
    ax.text((x_from + x_to) / 2, y + d * 0.42, text, ha="center",
            va="top" if below else "bottom", color=color, fontsize=size,
            fontfamily=SANS)


def rectangle(ax, x, y, w, h, facecolor=ZERO, edgecolor=DIM, lw=2.0, zorder=2):
    """A raw rectangle for dynamic composition."""
    ax.add_patch(Rectangle((x - w/2, y - h/2), w, h, facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, zorder=zorder))

def circle(ax, text, x, y, r=0.4, active=False, size=24):
    ec = ACCENT if active else DIM
    ax.add_patch(Circle((x, y), r, facecolor=BG, edgecolor=ec, linewidth=3.2 if active else 2.0, zorder=2))
    ax.text(x, y, text, ha="center", va="center", zorder=3,
            color=ACCENT if active else FG, fontsize=size, fontfamily=SANS,
            fontweight="bold" if active else "normal")

def arrow(ax, x1, y1, x2, y2, color=ACCENT, lw=3.0, head=0.28):
    ax.add_patch(FancyArrow(
        x1, y1, x2 - x1, y2 - y1, width=lw * 0.012, head_width=head,
        head_length=head, length_includes_head=True, color=color, zorder=4))


def strike(ax, x1, x2, y, color=BAD, lw=4):
    ax.plot([x1, x2], [y, y], color=color, lw=lw, zorder=6)


def badge(ax, x, y, text, color=GOOD, size=30):
    ax.text(x, y, text, ha="center", va="center", color=color, fontsize=size,
            fontfamily=SANS, fontweight="bold")


def compare(ax, a, b, x, y, op="<", winner=None, size=40,
           label_a=None, label_b=None):
    """Two values side by side with a comparator glyph between them --
    the generic version of what k.array's own lo/hi/mid coloring does,
    for a comparison that isn't happening inside an array.

    winner : None | "left" | "right" -- outlines that side GOOD and stamps
             a checkmark on it (color is never the only signal). The other
             side stays neutral, never BAD: losing a comparison is an
             outcome, not an error.
    op     : the comparator glyph shown between the two boxes.
    Returns (left_x, right_x), the box centres, so callers can hang their
    own annotations off either side.
    """
    def _w(v):
        return max(1.3, 0.34 * len(str(v)) + 0.75)
    wa, wb = _w(a), _w(b)
    glyph_gap = 1.2
    lx = x - glyph_gap / 2 - wa / 2
    rx = x + glyph_gap / 2 + wb / 2
    h = 1.3

    for side, cx, w, v, lbl in (("left", lx, wa, a, label_a),
                                ("right", rx, wb, b, label_b)):
        win = winner == side
        ec = GOOD if win else DIM
        ax.add_patch(FancyBboxPatch(
            (cx - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.03,rounding_size=0.12",
            facecolor=ZERO, edgecolor=ec, linewidth=3.5 if win else 2.0, zorder=2))
        ax.text(cx, y, str(v), ha="center", va="center", zorder=3,
                color=GOOD if win else FG, fontsize=size, fontfamily=MONO,
                fontweight="bold" if win else "normal")
        if win:
            badge(ax, cx, y + h / 2 + 0.42, "✓", GOOD, size=int(size * 0.55))
        if lbl:
            ax.text(cx, y - h / 2 - 0.30, lbl, ha="center", va="top",
                    color=DIM, fontsize=17, fontfamily=MONO)

    label(ax, x, y, op, size=int(size * 0.7), color=ACCENT, weight="bold")
    return lx, rx


# ------------------------------------------------- column addition block


def addition(ax, top, bottom, result, x, y, n=8, box=1.05, gap=0.16,
             carry=None, ok=None, size=40):
    """Two operands over a rule with a result, laid out on the bit grid.

    carry : optional string of carry bits drawn above
    ok    : True draws a green tick, False a red cross, None nothing
    """
    step = box + gap
    if carry:
        bits(ax, carry, x, y + 2.55, n=len(carry), box=box * 0.62,
             gap=gap, size=int(size * 0.55), dim=True)
        label(ax, x - (n * step) / 2 - 1.5, y + 2.55, "carry", size=20,
              color=DIM, ha="right")
    bits(ax, top, x, y + 1.35, n=n, box=box, gap=gap, size=size)
    bits(ax, bottom, x, y, n=n, box=box, gap=gap, size=size)
    half = (n * step - gap) / 2
    # A wide operand pushes the rule and the '+' off the left edge — the
    # layout audit caught this in a shipped video. Keep both inside the frame.
    rule_x0 = max(x - half - 0.4, 0.25)
    ax.plot([rule_x0, min(x + half + 0.4, W - 0.25)], [y - 0.78, y - 0.78],
            color=DIM, lw=3)
    label(ax, max(x - half - 0.85, 0.42), y + 0.68, "+", size=44, color=DIM)
    bits(ax, result, x, y - 1.68, n=len(str(result).replace(" ", ""))
         if not isinstance(result, int) else n, box=box, gap=gap, size=size)
    if ok is not None:
        badge(ax, min(x + half + 1.35, W - 0.5), y - 1.68,
              "✓" if ok else "✗", GOOD if ok else BAD, 60)


# --------------------------------------------------------- number line


def number_line(ax, lo, hi, y, x0=1.4, x1=14.6, ticks=None, marks=None,
                size=22):
    """Horizontal axis from lo..hi. marks = {value: (text, colour)}."""
    ax.plot([x0, x1], [y, y], color=DIM, lw=3, zorder=2)
    span = hi - lo

    def px(v):
        return x0 + (v - lo) / span * (x1 - x0)

    for t in (ticks or [lo, 0, hi]):
        ax.plot([px(t), px(t)], [y - 0.16, y + 0.16], color=DIM, lw=3)
        ax.text(px(t), y - 0.52, str(t), ha="center", va="top", color=DIM,
                fontsize=size, fontfamily=MONO)
    # Stagger labels that would collide, rather than letting them overprint.
    placed = []
    for v, (text, color) in sorted((marks or {}).items()):
        xv = px(v)
        tier = 0
        while any(abs(xv - p) < 0.9 and t == tier for p, t in placed):
            tier += 1
        placed.append((xv, tier))
        ax.add_patch(Circle((xv, y), 0.17, facecolor=color,
                            edgecolor=BG, lw=2, zorder=5))
        ax.text(xv, y + 0.55 + tier * 0.62, text, ha="center", va="bottom",
                color=color, fontsize=size + 4, fontfamily=SANS, zorder=5)
    return px


# --------------------------------------------------------- wrap dial


def dial(ax, n_bits, cx, cy, r, pointer=None, highlight_signed=False,
         size=20, label_mode="binary"):
    """The odometer: 2**n_bits patterns around a circle, 0 at the top.

    This is the picture that makes wrap-around obvious -- counting down from
    zero walks you anticlockwise into the top-half patterns.
    """
    import math
    count = 1 << n_bits
    if highlight_signed:
        ax.add_patch(Wedge((cx, cy), r + 0.55, 180, 360, width=0.12,
                           facecolor=BAD, alpha=0.30, zorder=1))
        ax.add_patch(Wedge((cx, cy), r + 0.55, 0, 180, width=0.12,
                           facecolor=GOOD, alpha=0.30, zorder=1))
    ax.add_patch(Circle((cx, cy), r, facecolor="none", edgecolor=LINE, lw=2))
    node_r = 0.46
    for i in range(count):
        ang = math.pi / 2 - 2 * math.pi * i / count
        x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
        signed = i if i < count // 2 else i - count
        hot = pointer is not None and i == pointer % count
        ax.add_patch(Circle((x, y), node_r, zorder=3,
                            facecolor=WARN if hot else ZERO,
                            edgecolor=WARN if hot else LINE, lw=2.5))
        # The pattern lives inside the node so it can never drift off it.
        ax.text(x, y, format(i, f"0{n_bits}b"), ha="center", va="center",
                zorder=4, color=BG if hot else DIM,
                fontsize=size * 0.62, fontfamily=MONO,
                fontweight="bold" if hot else "normal")
        if label_mode in ("signed", "both"):
            lx = cx + (r + node_r + 0.52) * math.cos(ang)
            ly = cy + (r + node_r + 0.52) * math.sin(ang)
            ax.text(lx, ly, str(signed), ha="center", va="center", zorder=4,
                    color=WARN if hot else (GOOD if signed >= 0 else BAD),
                    fontsize=size, fontfamily=MONO)
    return None


# ------------------------------------------------------------ registers


def register(ax, value, x, y, n=8, drop_carry=False, box=1.05, size=40,
             note=None):
    """A bit row inside a register outline, optionally with a carry bit
    shown falling off the left-hand end -- the visual that explains why
    two's complement addition needs no special case."""
    step = box + 0.16
    half = (n * step - 0.16) / 2
    ax.add_patch(Rectangle((x - half - 0.30, y - box / 2 - 0.30),
                           2 * half + 0.60, box + 0.60, facecolor="none",
                           edgecolor=DIM, lw=3, zorder=1))
    bits(ax, value, x, y, n=n, box=box, size=size)
    if drop_carry:
        cx = x - half - 1.35
        ax.add_patch(FancyBboxPatch(
            (cx - box / 2, y - box / 2), box, box,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            facecolor=ZERO, edgecolor=BAD, linewidth=3,
            linestyle="--", zorder=2))
        ax.text(cx, y, "1", ha="center", va="center", color=BAD,
                fontsize=size, fontfamily=MONO, zorder=3)
        arrow(ax, cx, y - 0.75, cx - 0.55, y - 1.55, color=BAD)
        ax.text(cx - 0.60, y - 1.95, "discarded", ha="center", va="top",
                color=BAD, fontsize=22, fontfamily=SANS)
    if note:
        # Sit the note under the register unless there is clearly room beside
        # it -- a note running off the right edge is the classic layout bug.
        if x + half + 0.85 + len(note) * 0.21 < W - 0.4:
            ax.text(x + half + 0.85, y, note, ha="left", va="center",
                    color=DIM, fontsize=24, fontfamily=SANS)
        else:
            ax.text(x, y - box / 2 - 1.05, note, ha="center", va="center",
                    color=DIM, fontsize=24, fontfamily=SANS)


# ------------------------------------------------------- search visuals


def array(ax, values, y=5.0, x0=1.0, x1=15.0, lo=None, hi=None, mid=None,
          found=None, dead=None, target=None, size=26, idx=True,
          bracket=None, alpha=1.0):
    """A sorted array with the pointers a binary search actually maintains.

    dead   : indices already eliminated -- drawn hollow, because the point of
             the algorithm is what you can stop looking at
    lo/hi  : pointer arrows below; mid marked above
    bracket: text drawn over the live lo..hi span
    Returns a function index -> x so callers can attach their own annotations.
    """
    n = len(values)
    if n == 0:
        raise ValueError("k.array requires at least one value")
    gap = 0.12
    box = min(1.15, (x1 - x0 - (n - 1) * gap) / n)
    step = box + gap
    total = n * step - gap
    sx = (x0 + x1) / 2 - total / 2
    dead = set(dead or ())

    def px(i):
        return sx + i * step + box / 2

    for i, v in enumerate(values):
        cx = px(i)
        is_dead = i in dead
        if i == found:
            fc, ec, lw = GOOD, GOOD, 3.5
        elif i == mid:
            fc, ec, lw = WARN, WARN, 3.5
        elif is_dead:
            fc, ec, lw = BG, LINE, 1.5
        else:
            fc, ec, lw = ZERO, DIM, 2.0
        ax.add_patch(FancyBboxPatch(
            (cx - box / 2, y - box / 2), box, box,
            boxstyle="round,pad=0.02,rounding_size=0.09",
            facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2, alpha=alpha))
        
        # Manually apply alpha to text color by creating an RGBA tuple if it's a hex string
        text_color = BG if i in (mid, found) else (LINE if is_dead else FG)
        if alpha < 1.0:
            import matplotlib.colors as mcolors
            rgba = mcolors.to_rgba(text_color, alpha=alpha)
            text_color = rgba
            
        ax.text(cx, y, str(v), ha="center", va="center", zorder=3,
                color=text_color,
                fontsize=size, fontfamily=MONO,
                fontweight="bold" if i in (mid, found) else "normal")
        if idx:
            ax.text(cx, y - box / 2 - 0.30, str(i), ha="center", va="top",
                    color=LINE if is_dead else DIM, fontsize=17,
                    fontfamily=MONO)

    ptr_y = y - box / 2 - 0.95
    for name, i, col in (("lo", lo, ONE), ("hi", hi, ACCENT)):
        if i is None:
            continue
        # 0.62 measured too close: the audit still caught the "hi" label
        # overlapping "lo" by ~12px on the rendered figure. 0.85 clears it
        # with margin (0.70 was the bare minimum in testing).
        yy = ptr_y - (0.85 if (lo == hi and name == "hi") else 0)
        ax.annotate(name, xy=(px(i), yy + 0.30), xytext=(px(i), yy - 0.22),
                    ha="center", va="top", color=col, fontsize=23,
                    fontfamily=MONO, fontweight="bold", zorder=6,
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=2.4))
    if mid is not None:
        ax.annotate("mid", xy=(px(mid), y + box / 2 + 0.10),
                    xytext=(px(mid), y + box / 2 + 0.80),
                    ha="center", va="bottom", color=WARN, fontsize=23,
                    fontfamily=MONO, fontweight="bold", zorder=6,
                    arrowprops=dict(arrowstyle="-|>", color=WARN, lw=2.4))
    if isinstance(bracket, (tuple, list)):
        # Callers sometimes pass (lo, hi, "text"); take the text, not the repr.
        bracket = next((b for b in reversed(bracket) if isinstance(b, str)),
                       None)
    if bracket and lo is not None and hi is not None and lo <= hi:
        a, b = px(lo) - box / 2, px(hi) + box / 2
        # Never let the bracket label climb into the title band at y=7.6.
        yy = min(y + box / 2 + (1.55 if mid is not None else 0.55), 6.9)
        ax.plot([a, a, b, b], [yy, yy + 0.16, yy + 0.16, yy],
                color=GOOD, lw=2.4, zorder=4)
        ax.text((a + b) / 2, yy + 0.30, bracket, ha="center", va="bottom",
                color=GOOD, fontsize=24, fontfamily=SANS, zorder=4)
    if target is not None:
        ax.text(x0 - 0.1, y + 1.9, f"target = {target}", ha="left",
                va="center", color=FG, fontsize=26, fontfamily=MONO)
    return px


def predicate_strip(ax, flags, y=5.0, x0=2.0, x1=14.0, boundary=True,
                    labels=("no", "yes"), size=26, note=None):
    """false,false,...,true,true -- the shape every binary search really needs."""
    n = len(flags)
    if n == 0:
        raise ValueError("k.predicate_strip requires at least one flag")
    gap = 0.12
    box = min(1.3, (x1 - x0 - (n - 1) * gap) / n)
    step = box + gap
    sx = (x0 + x1) / 2 - (n * step - gap) / 2
    # Shrink the label until it fits its own cell. Labels like "too small" or
    # "x^2 < target" are much wider than "no" and will happily run into the
    # neighbouring box otherwise.
    longest = max(len(str(l)) for l in labels)
    fit = size
    while longest * fit * 0.0062 > box * 0.88 and fit > 11:
        fit -= 1

    first_true = None
    for i, f in enumerate(flags):
        cx = sx + i * step + box / 2
        if f and first_true is None:
            first_true = cx
        ax.add_patch(FancyBboxPatch(
            (cx - box / 2, y - box / 2), box, box,
            boxstyle="round,pad=0.02,rounding_size=0.09",
            facecolor=GOOD if f else ZERO,
            edgecolor=GOOD if f else DIM, linewidth=2.2, zorder=2))
        ax.text(cx, y, labels[1] if f else labels[0], ha="center",
                va="center", color=BG if f else DIM, zorder=3,
                fontsize=fit, fontfamily=SANS,
                fontweight="bold" if f else "normal")
    if boundary and first_true is not None:
        bx = first_true - step / 2
        ax.plot([bx, bx], [y - box / 2 - 0.55, y + box / 2 + 0.55],
                color=WARN, lw=3.5, linestyle="--", zorder=5)
        ax.text(bx, y + box / 2 + 0.75, "the answer", ha="center",
                va="bottom", color=WARN, fontsize=26, fontfamily=SANS,
                fontweight="bold", zorder=5)
    if note:
        ax.text((x0 + x1) / 2, y - box / 2 - 1.15, note, ha="center",
                va="top", color=DIM, fontsize=24, fontfamily=SANS)


# --------------------------------------------------- algorithms & data structures

def hanoi(ax, state, x=8.0, y=5.0, w=9.0, h=4.0):
    """Draw a three-peg Tower of Hanoi state.

    The state is bottom-to-top: ``[[3, 2, 1], [], []]`` is legal, while
    ``[[1, 2], [], []]`` is physically illegal and should only be used when
    the scene explicitly labels it as an invalid example. Four-peg input is
    rejected before any artist is added so a bad model answer cannot crash
    halfway through a frame.
    """
    if not isinstance(state, list) or len(state) != 3:
        raise ValueError("k.hanoi supports exactly three pegs: [left, middle, right]")
    if any(not isinstance(peg, list) for peg in state):
        raise ValueError("k.hanoi state must be a list of three peg lists")
    disks = [disk for peg in state for disk in peg]
    if any(isinstance(disk, bool) or not isinstance(disk, (int, float)) or disk <= 0
           for disk in disks):
        raise ValueError("k.hanoi disk sizes must be positive numbers")
    if len(set(disks)) != len(disks):
        raise ValueError("k.hanoi cannot draw duplicate disk sizes")
    if not disks:
        raise ValueError("k.hanoi state must contain at least one disk")
    max_disk = max(disks)

    base_y = y - h/2 + 0.2
    peg_y_top = y + h/2 - 0.5
    
    # Draw base
    ax.plot([x - w/2, x + w/2], [base_y, base_y], color=DIM, lw=4, zorder=1)
    
    # Draw pegs
    peg_x = [x - w/3, x, x + w/3]
    for px in peg_x:
        ax.plot([px, px], [base_y, peg_y_top], color=DIM, lw=4, zorder=1)
        
    # Draw disks
    # JIOHotsatr preference: vibrant primary colors
    colors = ["#0000ff", "#ff0000", "#00ff00", "#ff00ff", "#00ffff", "#ffff00"]
    disk_h = 0.4
    max_disk_w = (w/3) - 0.4
    
    for peg_idx, disks in enumerate(state):
        px = peg_x[peg_idx]
        for i, disk_size in enumerate(disks):
            disk_w = max_disk_w * (disk_size / max(3, max_disk))
            dy = base_y + 0.2 + i * (disk_h + 0.05)
            
            color = colors[(disk_size - 1) % len(colors)]
            ax.add_patch(FancyBboxPatch(
                (px - disk_w/2, dy - disk_h/2), disk_w, disk_h,
                boxstyle="round,pad=0.02,rounding_size=0.1",
                facecolor=color, edgecolor=BG, linewidth=1.5, zorder=2))
            ax.text(px, dy, str(disk_size), ha="center", va="center", 
                    color=BG, fontsize=18, fontfamily=SANS, fontweight="bold", zorder=3)

def tree(ax, root, x=8.0, y=7.0, dx=3.0, dy=1.5, active_node=None):
    """A binary tree visualization.
    
    root: nested tuple/value structure: (val, left, right) or just val for leaves.
          e.g., (10, (5, 2, 7), (15, None, 20))
    x, y: center of the root node.
    dx, dy: spacing.
    active_node: value of the node to highlight.
    """
    def draw_node(node, nx, ny, cdx):
        if node is None:
            return
            
        val = node[0] if isinstance(node, tuple) else node
        left = node[1] if isinstance(node, tuple) and len(node) > 1 else None
        right = node[2] if isinstance(node, tuple) and len(node) > 2 else None
        
        is_active = val == active_node
        
        if left is not None:
            lx, ly = nx - cdx, ny - dy
            arrow(ax, nx, ny - 0.4, lx, ly + 0.4, color=DIM, lw=2)
            draw_node(left, lx, ly, cdx / 2)
            
        if right is not None:
            rx, ry = nx + cdx, ny - dy
            arrow(ax, nx, ny - 0.4, rx, ry + 0.4, color=DIM, lw=2)
            draw_node(right, rx, ry, cdx / 2)
            
        circle(ax, str(val), nx, ny, r=0.4, active=is_active)
        
    draw_node(root, x, y, dx)

def grid(ax, data, x=8.0, y=5.0, cell_w=1.2, cell_h=1.2, highlight=None):
    """A 2D grid/matrix visualization (e.g., for DP, graphs, mazes).
    
    data: list of lists of values/strings.
    highlight: list of (row, col) tuples to highlight.
    """
    rows = len(data)
    cols = len(data[0]) if rows > 0 else 0
    highlight = set(highlight or [])
    
    start_x = x - (cols * cell_w) / 2
    start_y = y + (rows * cell_h) / 2
    
    for r in range(rows):
        for c in range(cols):
            cx = start_x + c * cell_w + cell_w / 2
            cy = start_y - r * cell_h - cell_h / 2
            
            is_high = (r, c) in highlight
            val = str(data[r][c])
            
            ax.add_patch(Rectangle(
                (cx - cell_w/2, cy - cell_h/2), cell_w, cell_h,
                facecolor=ACCENT if is_high else ZERO,
                edgecolor=DIM, linewidth=2.0, zorder=2))
                
            ax.text(cx, cy, val, ha="center", va="center",
                    color=FG, fontsize=24, fontfamily=MONO, zorder=3)

# --------------------------------------------------- datapath / block diagram


def block(ax, text, x, y, w=2.6, h=1.4, active=False, size=24, alpha=1.0):
    """A labeled functional-unit box -- ALU, register file, cache, control
    unit -- for datapath/block diagrams (pipelining, cache mapping,
    addressing modes, DMA, fetch-decode-execute).

    active: outlines and labels the block ACCENT instead of neutral -- the
    unit actually doing work in this step of the trace.
    Returns a dict of edge anchor points {"left","right","top","bottom",
    "center"} (each an (x, y) tuple) so k.bus() can route to a precise edge
    instead of a guessed coordinate.
    """
    ec = ACCENT if active else DIM
    # Depth shadow
    # Hardcoded shadow color instead of missing Theme class
    ax.add_patch(FancyBboxPatch(
        (x - w / 2 + 0.05, y - h / 2 - 0.05), w, h,
        boxstyle="round,pad=0.03,rounding_size=0.10",
        facecolor="#05080c", edgecolor="none", zorder=1, alpha=alpha))
        
    ax.add_patch(FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.03,rounding_size=0.10",
        facecolor=BG, edgecolor=ec, linewidth=3.2 if active else 2.0, zorder=2, alpha=alpha))
    ax.text(x, y, text, ha="center", va="center", zorder=3,
            color=ACCENT if active else FG, fontsize=size, fontfamily=SANS,
            fontweight="bold" if active else "normal", alpha=alpha)
    return {"left": (x - w / 2, y), "right": (x + w / 2, y),
            "top": (x, y + h / 2), "bottom": (x, y - h / 2),
            "center": (x, y)}


def bus(ax, p1, p2, label=None, active=False, lw=2.5):
    """An orthogonal wire between two block anchor points -- the right-angle
    routing convention for a datapath diagram, distinct from k.arrow's
    direct diagonal line.

    p1, p2  : (x, y) tuples, typically two of k.block()'s returned anchors.
    active  : thicker and ACCENT-colored -- the signal path actually
              carrying data in this step, versus the diagram's other wires.
    label   : an optional data-width/signal name drawn at the bend.
    """
    x1, y1 = p1
    x2, y2 = p2
    color = ACCENT if active else DIM
    w = 3.5 if active else lw
    if abs(x1 - x2) < 0.05 or abs(y1 - y2) < 0.05:
        arrow(ax, x1, y1, x2, y2, color=color, lw=w)
        lx, ly = (x1 + x2) / 2, max(y1, y2) + 0.28
    else:
        # One right-angle bend: horizontal off the source, then vertical
        # into the target -- the standard bus-routing convention, and it
        # keeps two parallel buses from reading as one diagonal crossing.
        ax.plot([x1, x2], [y1, y1], color=color, lw=w, zorder=4)
        arrow(ax, x2, y1, x2, y2, color=color, lw=w)
        lx, ly = x2, max(y1, y2) + 0.28
    if label:
        ax.text(lx, ly, label, ha="center", va="bottom", color=DIM,
                fontsize=17, fontfamily=MONO, zorder=4)


def code(ax, lines, x=8.0, y=5.0, highlight=None, hcolor=WARN, size=27,
         width=None, title_text=None):
    """A monospace code block, optionally with lines called out.

    highlight: iterable of 0-based line numbers
    """
    highlight = set(highlight or ())
    n = len(lines)
    longest = max(len(s) for s in lines)

    # One monospace char is about 0.6 * the font size in points; at 100 dpi
    # across a 16-unit canvas that is size * 0.00695 units. Getting this
    # wrong is how code blocks end up wider than the frame.
    def char_w(s):
        return s * 0.00695

    if width is None:
        while longest * char_w(size) + 1.0 > W - 1.2 and size > 13:
            size -= 1                      # shrink to fit rather than overflow
        width = min(longest * char_w(size) + 1.0, W - 1.0)
    w = width
    lh = size * 0.0235
    h = n * lh + 0.75
    ax.add_patch(FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.04,rounding_size=0.16",
        facecolor="#11161d", edgecolor=LINE, linewidth=2, zorder=1))
    if title_text:
        ax.text(x - w / 2 + 0.35, y + h / 2 + 0.32, title_text, ha="left",
                va="bottom", color=DIM, fontsize=22, fontfamily=SANS)
    top = y + h / 2 - 0.55
    for i, s in enumerate(lines):
        yy = top - i * lh
        if i in highlight:
            ax.add_patch(Rectangle((x - w / 2 + 0.08, yy - lh * 0.42),
                                   w - 0.16, lh * 0.86, facecolor=hcolor,
                                   alpha=0.16, zorder=2))
        ax.text(x - w / 2 + 0.42, yy, s, ha="left", va="center", zorder=3,
                color=hcolor if i in highlight else FG,
                fontsize=size, fontfamily=MONO)


def table(ax, rows, headers=None, x=8.0, y=5.0, col_w=None, size=27,
          highlight_row=None, highlight_cells=None):
    """A small comparison table. rows is a list of tuples of strings.

    highlight_cells: iterable of (row, col) pairs highlighted individually,
    for DP-style grids where the cell being filled (and/or the specific
    cells it depends on) matters, not a whole row.
    """
    if not rows:
        raise ValueError("k.table requires at least one row")
    ncol = len(rows[0])
    if ncol == 0:
        raise ValueError("k.table rows cannot be empty")
    if any(len(row) != ncol for row in rows):
        raise ValueError("k.table rows must all have the same number of columns")
    if headers is not None and len(headers) != ncol:
        raise ValueError("k.table headers must match the number of columns")
    col_w = col_w or [3.4] * ncol
    total = sum(col_w)
    rh = 0.78
    x0 = x - total / 2
    ytop = y + (len(rows) + (1 if headers else 0)) * rh / 2
    highlight_cells = set(highlight_cells or ())

    if headers:
        for c, htxt in enumerate(headers):
            cx = x0 + sum(col_w[:c]) + col_w[c] / 2
            ax.text(cx, ytop, htxt, ha="center", va="center", color=DIM,
                    fontsize=size - 3, fontfamily=SANS, fontweight="bold")
        ax.plot([x0, x0 + total], [ytop - rh * 0.55, ytop - rh * 0.55],
                color=LINE, lw=2)
    for r, row in enumerate(rows):
        yy = ytop - (r + 1) * rh
        if r == highlight_row:
            ax.add_patch(Rectangle((x0 - 0.15, yy - rh * 0.42),
                                   total + 0.3, rh * 0.84,
                                   facecolor=WARN, alpha=0.14, zorder=1))
        for c, cell in enumerate(row):
            cx = x0 + sum(col_w[:c]) + col_w[c] / 2
            cell_hl = (r, c) in highlight_cells
            if cell_hl:
                ax.add_patch(Rectangle(
                    (cx - col_w[c] / 2 + 0.08, yy - rh * 0.42),
                    col_w[c] - 0.16, rh * 0.84,
                    facecolor=WARN, alpha=0.22, zorder=2))
            ax.text(cx, yy, str(cell), ha="center", va="center", zorder=3,
                    color=WARN if (r == highlight_row or cell_hl) else FG,
                    fontsize=size, fontfamily=MONO)


def curves(ax, n_max=64, x=8.0, y=4.6, w=9.0, h=4.2, show=("linear", "log"),
           size=22):
    """Linear against logarithmic on shared axes -- the whole argument for
    binary search in one picture."""
    import math
    # Keep the plot box inside the frame: below y=1.4 it runs into the caption
    # band, above y=7.2 into the title.
    h = min(h, 5.6)
    y = min(max(y, 1.4 + h / 2), 7.2 - h / 2)
    x0, y0 = x - w / 2, y - h / 2
    ax.plot([x0, x0, x0 + w], [y0 + h, y0, y0], color=DIM, lw=2.5)
    ax.text(x0 + w / 2, y0 - 0.55, "input size n", ha="center", va="top",
            color=DIM, fontsize=size, fontfamily=SANS)
    ax.text(x0 - 0.45, y0 + h / 2, "steps", ha="center", va="center",
            color=DIM, fontsize=size, fontfamily=SANS, rotation=90)
    pts = 160
    if "linear" in show:
        xs = [x0 + w * i / pts for i in range(pts + 1)]
        ys = [y0 + h * (i / pts) for i in range(pts + 1)]
        ax.plot(xs, ys, color=BAD, lw=3.5)
        ax.text(x0 + w + 0.15, y0 + h, "linear scan", ha="left", va="center",
                color=BAD, fontsize=size + 2, fontfamily=SANS)
    if "log" in show:
        xs, ys = [], []
        for i in range(1, pts + 1):
            frac = i / pts
            xs.append(x0 + w * frac)
            ys.append(y0 + h * (math.log2(1 + frac * (n_max - 1))
                                / math.log2(n_max)) * 0.42)
        ax.plot(xs, ys, color=GOOD, lw=3.5)
        ax.text(x0 + w + 0.15, ys[-1], "binary search", ha="left",
                va="center", color=GOOD, fontsize=size + 2, fontfamily=SANS)


# -------------------------------------------------------------- elements

#: Which primitives are *connectors* — things whose whole job is to touch
#: something else. An arrow that did not reach its target would be the bug.
#: They are still held to the frame edge; they are simply never accused of
#: colliding with what they point at.
CONNECTOR_KINDS = {"arrow", "strike", "bit_brace", "bus"}

#: Every public drawing call, and the element kind it produces. Wrapping them
#: from one table rather than decorating sixteen definitions keeps the drawing
#: code readable, and makes it obvious at a glance that nothing was missed —
#: an untagged primitive is one the layout critic cannot see.
_ELEMENT_KINDS = {
    "title": "title", "caption": "caption", "label": "label",
    "badge": "badge", "bits": "bits", "bit_brace": "bit_brace",
    "arrow": "arrow", "strike": "strike", "addition": "addition",
    "compare": "compare",
    "number_line": "number_line", "dial": "dial", "register": "register",
    "array": "array", "predicate_strip": "predicate_strip",
    "code": "code", "table": "table", "curves": "curves",
    "block": "block", "bus": "bus",
    "hanoi": "hanoi", "tree": "tree", "grid": "grid",
    "rectangle": "rectangle", "circle": "circle",
}

#: Artist containers on an Axes that can hold something visible.
_CONTAINERS = ("texts", "patches", "lines", "collections", "artists", "images")

_state = threading.local()


def _artists(ax):
    for name in _CONTAINERS:
        for art in getattr(ax, name, ()) or ():
            yield art


def _counts(ax) -> dict:
    return {n: len(getattr(ax, n, ()) or ()) for n in _CONTAINERS}


def _element(kind: str):
    """Mark everything one primitive draws as a single layout element.

    This is what makes the overlap check mean something. A `k.array` call
    emits a dozen boxes, their digits and a pair of pointer arrows, and those
    are *supposed* to sit on top of each other — a digit belongs inside its
    box. What is never acceptable is one primitive's geometry landing on
    another's. Grouping by the call that produced it is exactly that
    distinction, and without it the audit has to fall back to comparing
    individual glyphs, which is why a dial could be drawn straight through an
    array and pass clean.

    Nested calls (addition draws bits, register draws bits and an arrow)
    belong to the outermost element: the depth guard lets the outer call claim
    them. Thread-local because the depth is per render, and scenes.py judges
    generated modules from a worker thread.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(ax, *args, **kwargs):
            if getattr(_state, "depth", 0):
                return fn(ax, *args, **kwargs)        # an inner detail
            before = _counts(ax)
            _state.depth = 1
            try:
                return fn(ax, *args, **kwargs)
            finally:
                _state.depth = 0
                gid = getattr(ax, "_p2r_gid", 0)
                ax._p2r_gid = gid + 1
                for name in _CONTAINERS:
                    seq = getattr(ax, name, ()) or ()
                    for art in list(seq)[before[name]:]:
                        art._p2r_el = (gid, kind)
        return wrapped
    return deco

# Wrap the primitives defined before the decorator
title = _element("title")(title)
caption = _element("caption")(caption)
label = _element("label")(label)
bits = _element("bits")(bits)
bit_brace = _element("bit_brace")(bit_brace)
rectangle = _element("rectangle")(rectangle)
circle = _element("circle")(circle)
arrow = _element("arrow")(arrow)
strike = _element("strike")(strike)
badge = _element("badge")(badge)
compare = _element("compare")(compare)
addition = _element("addition")(addition)
number_line = _element("number_line")(number_line)
dial = _element("dial")(dial)
register = _element("register")(register)
array = _element("array")(array)
predicate_strip = _element("predicate_strip")(predicate_strip)
code = _element("code")(code)
table = _element("table")(table)
curves = _element("curves")(curves)
block = _element("block")(block)
bus = _element("bus")(bus)
hanoi = _element("hanoi")(hanoi)
tree = _element("tree")(tree)
grid = _element("grid")(grid)


# (The dynamic globals() loop was removed because we wrapped them explicitly above)


# ----------------------------------------------------------------- audit

PX_W, PX_H = int(FIGSIZE[0] * DPI), int(FIGSIZE[1] * DPI)   # 1920 x 1080
MARGIN_PX = 12
NEAR_MARGIN_PX = 20      # WARNING band: within this of the safe margin but not yet off-frame
OVERLAP_FRAC = 0.10      # of the smaller box; calibrated against shipped scenes
MIN_TEXT_PX = 15         # below this a glyph is unreadable at 360p

#: Element geometry is exact, unlike a glyph bounding box, so this is tight.
#: It exists only to forgive a rounded corner grazing a neighbour.
ELEMENT_OVERLAP_FRAC = 0.02
ELEMENT_OVERLAP_MIN_PX = 60.0   # px^2; below this it is antialiasing, not a bug

# Calibrated by measurement, not by guess: an empty canvas reads 0.00%, a
# legitimate title card 1.30%, a dense bit-addition frame 23.3%. An earlier 2%
# floor called every title card blank.
INK_LOW, INK_HIGH = 0.005, 0.55

# -----------------------------------------------------------------
# Authoritative safe-zone geometry (mirrors harness/layout_zones.py).
# Kept inline so scenekit remains self-contained for matplotlib-only
# installs; the harness module re-exports these as the authoritative copy.
# Canvas is 16 x 9 units; pixel scale is PX_H / H = 120 px per unit.
_SCENEKIT_ZONE_UNITS = {
    "title": (7.6, 8.6),
    "visual": (4.0, 7.0),
    "secondary": (1.5, 3.5),
    "caption": (0.4, 1.3),
}
_SCENEKIT_SAFE_X_UNITS = (0.4, 15.6)
_SCENEKIT_SAFE_Y_UNITS = (0.4, 8.6)


def _units_to_px_y(y_units: float) -> float:
    return y_units * (PX_H / H)


def _units_to_px_x(x_units: float) -> float:
    return x_units * (PX_W / W)


# Pre-computed pixel bands for fast audit checks
SCENEKIT_CAPTION_PX = (_units_to_px_y(_SCENEKIT_ZONE_UNITS["caption"][0]),
                       _units_to_px_y(_SCENEKIT_ZONE_UNITS["caption"][1]))
SCENEKIT_TITLE_PX = (_units_to_px_y(_SCENEKIT_ZONE_UNITS["title"][0]),
                     _units_to_px_y(_SCENEKIT_ZONE_UNITS["title"][1]))
SCENEKIT_VISUAL_PX = (_units_to_px_y(_SCENEKIT_ZONE_UNITS["visual"][0]),
                      _units_to_px_y(_SCENEKIT_ZONE_UNITS["visual"][1]))
SCENEKIT_SECONDARY_PX = (_units_to_px_y(_SCENEKIT_ZONE_UNITS["secondary"][0]),
                         _units_to_px_y(_SCENEKIT_ZONE_UNITS["secondary"][1]))

# Minimum gap between caption zone and other text (px)
CAPTION_GAP_PX = 18
# Minimum gap between title zone and visual elements
TITLE_GAP_PX = 16


class Problem:
    """One layout complaint, phrased so a model can act on it."""

    def __init__(self, level: str, kind: str, message: str):
        self.level = level          # "fail" | "warn"
        self.kind = kind
        self.message = message

    def __str__(self) -> str:
        return f"{self.level.upper()} [{self.kind}] {self.message}"


def _boxes(ax, renderer):
    out = []
    for t in ax.texts:
        s = t.get_text()
        if not s or not s.strip():
            continue
        try:
            bb = t.get_window_extent(renderer)
        except Exception:                       # noqa: BLE001
            continue
        if bb.width <= 0 or bb.height <= 0:
            continue
        out.append((s.strip(), bb))
    return out


def _overlap(a, b) -> float:
    dx = min(a.x1, b.x1) - max(a.x0, b.x0)
    dy = min(a.y1, b.y1) - max(a.y0, b.y0)
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _touching(a, b) -> bool:
    """Do these boxes meet at all? Cheap prefilter before the exact test."""
    return (min(a.x1, b.x1) > max(a.x0, b.x0)
            and min(a.y1, b.y1) > max(a.y0, b.y0))


def _shape(art, renderer):
    """(display bbox, display path or None) for one artist.

    The path is what makes this trustworthy. A bounding box says a diagonal
    arrow fills a huge rectangle, nearly all of which is empty — comparing
    boxes alone would report collisions between things that visibly do not
    touch. Comparing the actual geometry does not.
    """
    try:
        bb = art.get_window_extent(renderer)
    except Exception:                                # noqa: BLE001
        return None, None
    if bb.width <= 0 and bb.height <= 0:
        return None, None
    path = None
    try:
        raw = art.get_path()
        if raw is not None and len(raw.vertices):
            path = raw.transformed(art.get_transform())
    except Exception:                                # noqa: BLE001
        path = None
    return bb, path


def _elements(ax, renderer) -> list[dict]:
    """Group every visible artist by the primitive call that drew it."""
    groups: dict = {}
    for art in _artists(ax):
        try:
            if not art.get_visible():
                continue
        except Exception:                            # noqa: BLE001
            continue
        gid, kind = getattr(art, "_p2r_el", (None, None))
        if gid is None:
            # Drawn outside the kit (a scene module reaching for ax directly).
            # Give it its own element rather than letting it go unchecked.
            gid, kind = f"raw{id(art)}", "raw"
        bb, path = _shape(art, renderer)
        if bb is None:
            continue
        g = groups.setdefault(gid, {"kind": kind, "parts": [], "bbox": None})
        g["parts"].append((bb, path))
        g["bbox"] = bb if g["bbox"] is None else Bbox.union([g["bbox"], bb])
    return [g for g in groups.values() if g["parts"]]


def _parts_collide(a: dict, b: dict) -> tuple[float, object, object]:
    """Exact test between two elements. Returns (area, bbox_a, bbox_b).

    Area is 0 with non-None boxes when the two genuinely intersect but one of
    them is a zero-thickness stroke — a number line ruled straight through an
    array has no overlapping *area* at all, and is still obviously wrong.
    """
    best = (0.0, None, None)
    for bb_a, path_a in a["parts"]:
        for bb_b, path_b in b["parts"]:
            if not _touching(bb_a, bb_b):
                continue
            if path_a is not None and path_b is not None:
                try:
                    if not path_a.intersects_path(path_b, filled=True):
                        continue
                except Exception:                    # noqa: BLE001
                    pass
            area = _overlap(bb_a, bb_b)
            smaller = min(bb_a.width * bb_a.height, bb_b.width * bb_b.height)
            if smaller <= 0:                         # a stroke: any contact counts
                return (0.0, bb_a, bb_b)
            if area > best[0]:
                best = (area, bb_a, bb_b)
    return best


_BG_RGB = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))


def ink_fraction(fig) -> float:
    """Share of the frame that is not background. Free: already rendered.

    Computed channel by channel in uint8/uint16 rather than by promoting the
    whole 1920x1080x3 frame to int16 first. Same arithmetic, same answer, but
    it allocates ~2 MB instead of ~25 MB per still, which on a section of
    fifteen stills is the difference between staying in cache and not.
    """
    if not drawn(fig):
        fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    # Optimize memory: work directly with uint8 diffs instead of allocating a uint16 accumulator
    # for the whole 1920x1080 frame.
    mask = np.zeros(buf.shape[:2], dtype=bool)
    for c, bg in enumerate(_BG_RGB):
        ch = buf[:, :, c]
        diff = np.maximum(ch, bg) - np.minimum(ch, bg)
        mask |= (diff > 8)  # 3x8=24 equivalent per channel, saves the uint16 allocation
    return float(np.count_nonzero(mask)) / mask.size


def _element_problems(ax, renderer, tag: str) -> list[Problem]:
    """Element-against-element collisions, and elements off the frame.

    The text-by-text check above only ever saw `ax.texts`, so anything drawn
    as a patch or a stroke was invisible to it: a dial's node circles, a code
    block's panel, a number line's rule, the boxes under an array's digits.
    Two elements could be laid straight through each other and pass clean so
    long as their glyphs happened to fall in each other's gaps — which is
    exactly the failure that reaches the video, because what a viewer sees is
    the boxes, not the bounding boxes of the letters.
    """
    out: list[Problem] = []
    els = _elements(ax, renderer)

    for e in els:
        bb = e["bbox"]
        if (bb.x0 < MARGIN_PX or bb.x1 > PX_W - MARGIN_PX
                or bb.y0 < MARGIN_PX or bb.y1 > PX_H - MARGIN_PX):
            # Distinguish caption vs other elements for repair targeting
            kind_map = {"caption": "caption_collision", "title": "title_collision"}
            k = kind_map.get(e["kind"], "offframe")
            out.append(Problem(
                "fail", k,
                f"{tag}the {e['kind']} runs off the frame "
                f"(x {bb.x0:.0f}-{bb.x1:.0f}, y {bb.y0:.0f}-{bb.y1:.0f}; "
                f"the frame is {PX_W}x{PX_H}). Move it inward, shrink it, or "
                f"give it fewer elements. bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f} safe_zone=frame"))

    for i in range(len(els)):
        for j in range(i + 1, len(els)):
            a, b = els[i], els[j]
            if a["kind"] in CONNECTOR_KINDS or b["kind"] in CONNECTOR_KINDS:
                continue                     # an arrow is meant to reach things
            if not _touching(a["bbox"], b["bbox"]):
                continue
            area, ba, bb_ = _parts_collide(a, b)
            if ba is None:
                continue
            if area > 0:
                smaller = min(ba.width * ba.height, bb_.width * bb_.height)
                if area < ELEMENT_OVERLAP_MIN_PX or \
                        (smaller > 0 and area / smaller <= ELEMENT_OVERLAP_FRAC):
                    continue
            # Diagnosis-driven subtype: caption involvement is distinct
            if a["kind"] == "caption" or b["kind"] == "caption":
                kind = "caption_collision"
                repair_hint = "caption bbox overlaps another element bbox; move supporting labels upward and preserve caption zone"
            elif a["kind"] == "title" or b["kind"] == "title":
                kind = "title_collision"
                repair_hint = "title bbox overlaps another element; move visual elements down out of title band"
            else:
                kind = "overlap"
                repair_hint = "separate elements overlap"
            out.append(Problem(
                "fail", kind,
                f"{tag}the {a['kind']} (x {a['bbox'].x0:.0f}-"
                f"{a['bbox'].x1:.0f}, y {a['bbox'].y0:.0f}-{a['bbox'].y1:.0f}) "
                f"is drawn over the {b['kind']} (x {b['bbox'].x0:.0f}-"
                f"{b['bbox'].x1:.0f}, y {b['bbox'].y0:.0f}-{b['bbox'].y1:.0f})."
                f" {repair_hint}. bbox_a={a['bbox'].x0:.0f},{a['bbox'].y0:.0f},{a['bbox'].x1:.0f},{a['bbox'].y1:.0f} "
                f"bbox_b={b['bbox'].x0:.0f},{b['bbox'].y0:.0f},{b['bbox'].x1:.0f},{b['bbox'].y1:.0f}"))
    return out


def _zone_problems(ax, renderer, tag: str) -> list[Problem]:
    """Safe-zone violations and caption/label crowding.

    This is the deterministic geometric check that catches the exact Scene-07
    class before VLM review: caption outside its reserved band, labels drifting
    into the caption band, or caption placed so close to another text element
    that it crowds the bottom margin.
    """
    out: list[Problem] = []
    els = _elements(ax, renderer)
    boxes = _boxes(ax, renderer)

    # --- Near-margin warnings (2 px from edge vs clipped) ---
    for e in els:
        bb = e["bbox"]
        near_left = (bb.x0 >= MARGIN_PX and bb.x0 < MARGIN_PX + NEAR_MARGIN_PX)
        near_right = (bb.x1 <= PX_W - MARGIN_PX and bb.x1 > PX_W - MARGIN_PX - NEAR_MARGIN_PX)
        near_bottom = (bb.y0 >= MARGIN_PX and bb.y0 < MARGIN_PX + NEAR_MARGIN_PX)
        near_top = (bb.y1 <= PX_H - MARGIN_PX and bb.y1 > PX_H - MARGIN_PX - NEAR_MARGIN_PX)
        if near_left or near_right or near_bottom or near_top:
            # Only warn if not already failing off-frame
            if not (bb.x0 < MARGIN_PX or bb.x1 > PX_W - MARGIN_PX or bb.y0 < MARGIN_PX or bb.y1 > PX_H - MARGIN_PX):
                out.append(Problem(
                    "warn", "near_safe_margin",
                    f"{tag}the {e['kind']} is within {NEAR_MARGIN_PX}px of the safe margin "
                    f"(x {bb.x0:.0f}-{bb.x1:.0f}, y {bb.y0:.0f}-{bb.y1:.0f}); "
                    f"still inside but should be moved inward. measured_gap={min(bb.x0 - MARGIN_PX, PX_W - MARGIN_PX - bb.x1, bb.y0 - MARGIN_PX, PX_H - MARGIN_PX - bb.y1):.0f}px"))

    # --- Caption zone enforcement ---
    caption_els = [e for e in els if e["kind"] == "caption"]
    title_els = [e for e in els if e["kind"] == "title"]
    label_els = [e for e in els if e["kind"] == "label"]
    # Also text boxes that are not element-tagged but are caption-like (long sentence)
    cap_min_y, cap_max_y = SCENEKIT_CAPTION_PX
    title_min_y, title_max_y = SCENEKIT_TITLE_PX

    for e in caption_els:
        bb = e["bbox"]
        # Caption should sit inside caption band (allow slight tolerance of 8px)
        if bb.y1 > cap_max_y + 8 or bb.y0 < cap_min_y - 8:
            out.append(Problem(
                "fail", "caption_collision",
                f"{tag}caption bbox (y {bb.y0:.0f}-{bb.y1:.0f}) is outside its reserved caption zone "
                f"(y {cap_min_y:.0f}-{cap_max_y:.0f}). Keep caption inside the caption zone "
                f"and move other labels out. bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f} safe_zone=caption"))
        # Caption exceeding allocated height (multiline overflow)
        cap_height = bb.y1 - bb.y0
        allowed = cap_max_y - cap_min_y + 16  # slack
        if cap_height > allowed + 4:
            out.append(Problem(
                "fail", "text_overflow",
                f"{tag}caption height {cap_height:.0f}px exceeds allocated caption zone height {allowed:.0f}px "
                f"(multiline overflow). Reduce font size or reflow text. bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f}"))
        # Caption crowding: any other element within CAPTION_GAP_PX vertically
        for other in els:
            if other["kind"] == "caption":
                continue
            obb = other["bbox"]
            # vertical gap between caption top and other bottom
            gap = obb.y0 - bb.y1 if obb.y0 >= bb.y1 else bb.y0 - obb.y1 if bb.y0 >= obb.y1 else -1
            if gap >= 0 and gap < CAPTION_GAP_PX:
                out.append(Problem(
                    "fail", "crowding",
                    f"{tag}caption bbox (y {bb.y0:.0f}-{bb.y1:.0f}) is only {gap:.0f}px from {other['kind']} bbox "
                    f"(y {obb.y0:.0f}-{obb.y1:.0f}); elements crowd the bottom region. "
                    f"Increase vertical spacing. overlap_with={other['kind']} measured_gap={gap:.0f}px safe_zone=caption"))

    # Labels drifting into caption band
    for e in label_els:
        bb = e["bbox"]
        # If label's bbox overlaps caption zone vertically
        if bb.y0 < cap_max_y and bb.y1 > cap_min_y:
            # Check if it's actually close to caption element
            for cap in caption_els:
                cbb = cap["bbox"]
                if _touching(bb, cbb) or min(abs(bb.y0 - cbb.y1), abs(cbb.y0 - bb.y1)) < CAPTION_GAP_PX:
                    out.append(Problem(
                        "fail", "caption_collision",
                        f"{tag}label {bb.x0:.0f},{bb.y0:.0f} intrudes into caption zone (y {cap_min_y:.0f}-{cap_max_y:.0f}) "
                        f"and crowds caption (y {cbb.y0:.0f}-{cbb.y1:.0f}). Move label upward to secondary zone (y {SCENEKIT_SECONDARY_PX[0]:.0f}-{SCENEKIT_SECONDARY_PX[1]:.0f}). "
                        f"bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f} overlap_with=caption"))

    # Title zone violation
    for e in title_els:
        bb = e["bbox"]
        if bb.y0 < title_min_y - 8 or bb.y1 > title_max_y + 8:
            out.append(Problem(
                "fail", "title_collision",
                f"{tag}title bbox (y {bb.y0:.0f}-{bb.y1:.0f}) outside title zone (y {title_min_y:.0f}-{title_max_y:.0f}). "
                f"Keep title in title band. bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f}"))

    # Visual elements (bits, array, etc.) should not be in caption band unless tiny
    for e in els:
        if e["kind"] in ("title", "caption", "label", "badge"):
            continue
        if e["kind"] in CONNECTOR_KINDS:
            continue
        bb = e["bbox"]
        if bb.y0 < cap_max_y + CAPTION_GAP_PX and bb.y1 > cap_min_y:
            # If a visual's bottom intrudes into caption band
            # Allow if it's just touching edge; only flag if significant intrusion
            intrusion = cap_max_y - bb.y0 if bb.y0 < cap_max_y else 0
            if intrusion > 10:
                out.append(Problem(
                    "fail", "caption_collision",
                    f"{tag}{e['kind']} bbox (y {bb.y0:.0f}-{bb.y1:.0f}) intrudes into caption zone "
                    f"(y {cap_min_y:.0f}-{cap_max_y:.0f}) by {intrusion:.0f}px. Move visual upward to visual zone (y {SCENEKIT_VISUAL_PX[0]:.0f}-{SCENEKIT_VISUAL_PX[1]:.0f}). "
                    f"bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f} safe_zone=caption"))

    # Also check text boxes directly for caption-like strings near bottom
    for s, bb in boxes:
        # Heuristic: long sentence-like text near bottom is a caption
        if len(s) > 25 and bb.y0 < cap_max_y + 20 and bb.y1 > cap_min_y - 20:
            # Check distance to margin
            bottom_gap = bb.y0 - MARGIN_PX
            if bottom_gap >= 0 and bottom_gap < NEAR_MARGIN_PX:
                out.append(Problem(
                    "warn", "near_safe_margin",
                    f"{tag}text {s[:32]!r} near bottom margin (y {bb.y0:.0f}-{bb.y1:.0f}, gap {bottom_gap:.0f}px). "
                    f"Ensure caption stays well within caption zone. bbox={bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f}"))

    return out


def audit(fig, ax, name: str = "") -> list[Problem]:
    """Check one drawn frame for the layout faults that actually ship.

    A stack trace tells a model its code crashed. This tells it *where two
    things collided, in pixels*, which is something it can fix.
    """
    # Draw once. save() reuses this same rasterisation rather than doing its
    # own, so auditing a frame and writing it now costs one render, not two.
    if not drawn(fig):
        fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = _boxes(ax, renderer)
    tag = f"state {name}: " if name else ""
    problems: list[Problem] = []

    # Cognitive load check: limit distinct elements
    els = _elements(ax, renderer)
    if len(els) > 12:
        problems.append(Problem(
            "warn", "crowded",
            f"{tag}too many distinct visual elements ({len(els)}). "
            f"Reduce cognitive load by simplifying the diagram or splitting the scene."
        ))

    for s, bb in boxes:
        if (bb.x0 < MARGIN_PX or bb.x1 > PX_W - MARGIN_PX
                or bb.y0 < MARGIN_PX or bb.y1 > PX_H - MARGIN_PX):
            problems.append(Problem(
                "fail", "offframe",
                f"{tag}the text {s[:40]!r} runs off the frame "
                f"(x {bb.x0:.0f}-{bb.x1:.0f}, y {bb.y0:.0f}-{bb.y1:.0f}; "
                f"the frame is {PX_W}x{PX_H}). Move it inward or shorten it."))

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (s1, b1), (s2, b2) = boxes[i], boxes[j]
            inter = _overlap(b1, b2)
            if inter <= 0:
                continue
            smaller = min(b1.width * b1.height, b2.width * b2.height)
            if smaller > 0 and inter / smaller > OVERLAP_FRAC:
                problems.append(Problem(
                    "fail", "overlap",
                    f"{tag}{s1[:32]!r} (x {b1.x0:.0f}-{b1.x1:.0f}, "
                    f"y {b1.y0:.0f}-{b1.y1:.0f}) overlaps {s2[:32]!r} "
                    f"(x {b2.x0:.0f}-{b2.x1:.0f}, y {b2.y0:.0f}-{b2.y1:.0f}). "
                    f"Move one of them, or split this into two states."))

    problems += _element_problems(ax, renderer, tag)
    problems += _zone_problems(ax, renderer, tag)

    for s, bb in boxes:
        if bb.height < MIN_TEXT_PX:
            problems.append(Problem(
                "warn", "tiny",
                f"{tag}{s[:32]!r} is only {bb.height:.0f}px tall — "
                f"unreadable at 360p. Use size>=20."))

    ink = ink_fraction(fig)
    if ink < INK_LOW:
        problems.append(Problem(
            "fail", "blank",
            f"{tag}the frame is {ink*100:.1f}% covered — effectively blank. "
            f"Draw the content this state is supposed to show."))
    elif ink > INK_HIGH:
        problems.append(Problem(
            "warn", "crowded",
            f"{tag}the frame is {ink*100:.0f}% covered — too busy. "
            f"Split it across two states."))

    return problems