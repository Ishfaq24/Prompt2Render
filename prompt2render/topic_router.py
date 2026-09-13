"""Semantic renderer routing for Prompt2Render.

Decides whether a section should use the Manim animation renderer or
the SceneKit/Matplotlib renderer based on the educational content described
in the section's animation brief.

The routing is keyword-based and deliberately conservative: it only routes
to Manim when the brief strongly implies motion (elements physically moving,
algorithm steps, signal propagation). Static diagram topics default to
Matplotlib for reliability and speed.
"""
from __future__ import annotations

import re


# Topics where the *motion itself* is the lesson -- Manim wins clearly.
# Must be lower-case strings or regex patterns.
MOTION_TOPIC_KEYWORDS: frozenset[str] = frozenset({
    # Sorting algorithms
    "bubble sort", "bubble-sort", "bubblesort",
    "insertion sort", "insertion-sort",
    "selection sort", "selection-sort",
    "merge sort", "merge-sort",
    "quick sort", "quick-sort", "quicksort",
    "heap sort", "heap-sort",
    "radix sort", "counting sort",
    # Graph / tree traversal
    "breadth-first search", "breadth first search",
    "depth-first search", "depth first search",
    "dijkstra", "a* search", "a-star",
    "bfs traversal", "dfs traversal",
    "tree traversal", "level-order traversal",
    # Neural / ML
    "neural network", "forward propagation", "forward pass",
    "backpropagation", "gradient descent", "weight update",
    "signal propagating", "activation function",
    # Physics / signal
    "wave propagation", "signal wave",
    "projectile motion", "spring mass",
    "pendulum", "oscillation",
    "fourier transform", "fourier series",
    # Matrix transformations
    "matrix multiplication", "linear transformation",
    "eigenvector", "eigenvalue",
    "vector field",
    # Specific animations
    "animate swap", "animate step", "animate move",
    "elements swapping", "nodes highlighted", "path highlighted",
    "pointer moving", "arrow moving",
})

# Topics that look motion-y but work fine as statics in SceneKit
STATIC_OVERRIDE_KEYWORDS: frozenset[str] = frozenset({
    "binary representation", "bit manipulation", "register",
    "memory layout", "cache mapping", "pipeline stages",
    "network packet", "dns resolution", "tcp handshake",
    "flowchart", "block diagram", "datapath",
})


def brief_suggests_motion(anim_brief: str) -> bool:
    """Return True when the animation brief strongly implies animated motion.

    Uses two-pass logic:
      1. Reject if any STATIC_OVERRIDE keyword is found (these topics look
         motion-y but render better as SceneKit diagrams).
      2. Accept if any MOTION_TOPIC_KEYWORD is found.

    Args:
        anim_brief: The text of the section's ANIM brief.

    Returns:
        True if Manim is the better renderer for this section.
    """
    lower = anim_brief.lower()

    # Static override wins -- even if a motion keyword is present
    for kw in STATIC_OVERRIDE_KEYWORDS:
        if kw in lower:
            return False

    for kw in MOTION_TOPIC_KEYWORDS:
        if kw in lower:
            return True

    return False
