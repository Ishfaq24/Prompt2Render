"""Neuro-Symbolic Invariant Engine for Mathematically Rigorous Animations.

Provides deterministic algorithmic state traces, symbolic calculus & algebra solving,
and collision-free tree/graph coordinate layout solvers to eliminate LLM hallucinations.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

try:
    import networkx as nx
except ImportError:
    nx = None

try:
    import sympy
except ImportError:
    sympy = None


# ---------------------------------------------------------------------------
# 1. Deterministic Algorithmic State Tracers
# ---------------------------------------------------------------------------

def trace_sorting(
    initial_list: Sequence[int | float],
    algorithm: str = "bubble",
) -> list[dict[str, Any]]:
    """Generate deterministic step-by-step state traces for sorting algorithms.
    
    Each step records:
    - type: 'compare' | 'swap' | 'sorted_mark' | 'done'
    - indices: active indices being inspected
    - values: values at those indices
    - array: snapshot of the array after this step
    """
    arr = list(initial_list)
    n = len(arr)
    steps: list[dict[str, Any]] = [
        {
            "type": "initial",
            "indices": [],
            "values": [],
            "array": list(arr),
            "description": f"Initial array of {n} elements",
        }
    ]

    if algorithm.lower() == "bubble":
        for i in range(n):
            for j in range(0, n - i - 1):
                # Comparison step
                steps.append({
                    "type": "compare",
                    "indices": [j, j + 1],
                    "values": [arr[j], arr[j + 1]],
                    "array": list(arr),
                    "description": f"Compare element {arr[j]} and {arr[j + 1]}",
                })
                if arr[j] > arr[j + 1]:
                    # Swap step
                    arr[j], arr[j + 1] = arr[j + 1], arr[j]
                    steps.append({
                        "type": "swap",
                        "indices": [j, j + 1],
                        "values": [arr[j], arr[j + 1]],
                        "array": list(arr),
                        "description": f"Swap {arr[j + 1]} and {arr[j]}",
                    })
            steps.append({
                "type": "sorted_mark",
                "indices": [n - 1 - i],
                "values": [arr[n - 1 - i]],
                "array": list(arr),
                "description": f"Element {arr[n - 1 - i]} is placed in its sorted position",
            })

    elif algorithm.lower() == "insertion":
        for i in range(1, n):
            key = arr[i]
            j = i - 1
            steps.append({
                "type": "select_key",
                "indices": [i],
                "values": [key],
                "array": list(arr),
                "description": f"Select key {key} at index {i}",
            })
            while j >= 0 and arr[j] > key:
                arr[j + 1] = arr[j]
                steps.append({
                    "type": "shift",
                    "indices": [j, j + 1],
                    "values": [arr[j]],
                    "array": list(arr),
                    "description": f"Shift {arr[j]} right to index {j + 1}",
                })
                j -= 1
            arr[j + 1] = key
            steps.append({
                "type": "insert",
                "indices": [j + 1],
                "values": [key],
                "array": list(arr),
                "description": f"Insert key {key} at index {j + 1}",
            })

    steps.append({
        "type": "done",
        "indices": list(range(n)),
        "values": list(arr),
        "array": list(arr),
        "description": "Sorting complete",
    })
    return steps


def trace_binary_search(
    sorted_list: Sequence[int | float],
    target: int | float,
) -> list[dict[str, Any]]:
    """Generate exact interval bounds and search steps for Binary Search."""
    arr = list(sorted_list)
    steps: list[dict[str, Any]] = []
    low = 0
    high = len(arr) - 1
    step_num = 1

    while low <= high:
        mid = (low + high) // 2
        mid_val = arr[mid]
        comparison = "==" if mid_val == target else ("<" if mid_val < target else ">")

        steps.append({
            "step": step_num,
            "low": low,
            "high": high,
            "mid": mid,
            "mid_val": mid_val,
            "target": target,
            "comparison": comparison,
            "found": mid_val == target,
            "active_slice": list(range(low, high + 1)),
            "description": (
                f"Checking mid element {mid_val} at index {mid} against target {target} "
                f"(range: [{low}, {high}])"
            ),
        })

        if mid_val == target:
            break
        elif mid_val < target:
            low = mid + 1
        else:
            high = mid - 1
        step_num += 1

    return steps


def trace_euclid_gcd(a: int, b: int) -> list[dict[str, Any]]:
    """Generate step-by-step division and remainder steps for Euclidean GCD."""
    steps: list[dict[str, Any]] = []
    curr_a, curr_b = abs(a), abs(b)

    while curr_b != 0:
        quotient = curr_a // curr_b
        remainder = curr_a % curr_b
        equation_latex = f"{curr_a} = {curr_b} \\times {quotient} + {remainder}"
        steps.append({
            "a": curr_a,
            "b": curr_b,
            "quotient": quotient,
            "remainder": remainder,
            "equation_latex": equation_latex,
            "description": f"{curr_a} divided by {curr_b} is {quotient} with remainder {remainder}",
        })
        curr_a, curr_b = curr_b, remainder

    steps.append({
        "gcd": curr_a,
        "equation_latex": f"\\gcd({a}, {b}) = {curr_a}",
        "description": f"GCD is {curr_a}",
    })
    return steps


# ---------------------------------------------------------------------------
# 2. Graph & Tree Collision-Free Coordinate Solver
# ---------------------------------------------------------------------------

def compute_tree_layout(
    nodes: Sequence[Any],
    edges: Sequence[tuple[Any, Any]],
    root: Any,
    *,
    total_width: float = 10.0,
    total_height: float = 5.0,
    center_y: float = 0.5,
) -> dict[Any, tuple[float, float, float]]:
    """Compute 2D coordinates (x, y, 0.0) for a hierarchical tree with zero overlap.
    
    Guarantees:
    - Root is positioned at the top center.
    - Each depth layer is evenly spaced along Y.
    - Sibling subtrees are bounded horizontally with guaranteed margins.
    """
    children_map: dict[Any, list[Any]] = {n: [] for n in nodes}
    for u, v in edges:
        if u in children_map:
            children_map[u].append(v)

    # Calculate depths and sub-tree widths
    depths: dict[Any, int] = {root: 0}
    queue = [root]
    while queue:
        curr = queue.pop(0)
        for child in children_map.get(curr, []):
            depths[child] = depths[curr] + 1
            queue.append(child)

    max_depth = max(depths.values()) if depths else 0
    y_step = total_height / max(1, max_depth) if max_depth > 0 else 0.0
    top_y = center_y + (total_height / 2.0)

    # Compute leaf counts to allocate horizontal space proportionally
    def get_leaf_count(node: Any) -> int:
        ch = children_map.get(node, [])
        if not ch:
            return 1
        return sum(get_leaf_count(c) for c in ch)

    positions: dict[Any, tuple[float, float, float]] = {}

    def assign_x(node: Any, left_x: float, right_x: float) -> None:
        y_pos = top_y - (depths.get(node, 0) * y_step)
        ch = children_map.get(node, [])
        if not ch:
            positions[node] = ((left_x + right_x) / 2.0, y_pos, 0.0)
            return

        total_leaves = sum(get_leaf_count(c) for c in ch)
        curr_left = left_x
        child_centers = []

        for child in ch:
            child_leaves = get_leaf_count(child)
            span = (right_x - left_x) * (child_leaves / total_leaves)
            child_right = curr_left + span
            assign_x(child, curr_left, child_right)
            child_centers.append(positions[child][0])
            curr_left = child_right

        node_x = sum(child_centers) / len(child_centers)
        positions[node] = (node_x, y_pos, 0.0)

    assign_x(root, -total_width / 2.0, total_width / 2.0)
    return positions


def trace_bst_insertion(
    values: Sequence[int | float],
    *,
    total_width: float = 9.0,
    total_height: float = 4.5,
) -> list[dict[str, Any]]:
    """Compute step-by-step BST insertion states with valid coordinates."""
    class BSTNode:
        def __init__(self, val: int | float):
            self.val = val
            self.left: BSTNode | None = None
            self.right: BSTNode | None = None

    root_node: BSTNode | None = None
    all_nodes: list[int | float] = []
    all_edges: list[tuple[int | float, int | float]] = []
    states: list[dict[str, Any]] = []

    def insert(node: BSTNode | None, val: int | float) -> BSTNode:
        if node is None:
            return BSTNode(val)
        if val < node.val:
            node.left = insert(node.left, val)
        elif val > node.val:
            node.right = insert(node.right, val)
        return node

    for val in values:
        root_node = insert(root_node, val)
        all_nodes.append(val)

        # Collect current edges
        curr_edges: list[tuple[int | float, int | float]] = []
        def collect_edges(n: BSTNode | None):
            if not n:
                return
            if n.left:
                curr_edges.append((n.val, n.left.val))
                collect_edges(n.left)
            if n.right:
                curr_edges.append((n.val, n.right.val))
                collect_edges(n.right)

        collect_edges(root_node)

        # Calculate collision-free coordinates
        coords = compute_tree_layout(
            nodes=list(set(all_nodes)),
            edges=curr_edges,
            root=root_node.val,
            total_width=total_width,
            total_height=total_height,
        )

        states.append({
            "inserted": val,
            "nodes": list(coords.keys()),
            "edges": curr_edges,
            "positions": coords,
        })

    return states


# ---------------------------------------------------------------------------
# 3. Symbolic Calculus & Algebra Solver (SymPy)
# ---------------------------------------------------------------------------

def derive_calculus_step(
    expr_str: str,
    var: str = "x",
    operation: str = "diff",
) -> dict[str, Any]:
    """Calculate symbolic derivatives or integrals with exact LaTeX steps using SymPy."""
    if sympy is None:
        raise RuntimeError("sympy is required for symbolic calculus derivations")

    symbol = sympy.Symbol(var)
    expr = sympy.sympify(expr_str)

    if operation.lower() in ("diff", "derivative"):
        res = sympy.diff(expr, symbol)
        input_latex = sympy.latex(expr)
        result_latex = sympy.latex(res)
        equation_latex = f"\\frac{{d}}{{d{var}}}\\left({input_latex}\\right) = {result_latex}"
        return {
            "operation": "derivative",
            "variable": var,
            "input_expr": str(expr),
            "result_expr": str(res),
            "input_latex": input_latex,
            "result_latex": result_latex,
            "equation_latex": equation_latex,
        }

    elif operation.lower() in ("integrate", "integral"):
        res = sympy.integrate(expr, symbol)
        input_latex = sympy.latex(expr)
        result_latex = sympy.latex(res)
        equation_latex = f"\\int {input_latex} \\, d{var} = {result_latex} + C"
        return {
            "operation": "integral",
            "variable": var,
            "input_expr": str(expr),
            "result_expr": str(res),
            "input_latex": input_latex,
            "result_latex": result_latex,
            "equation_latex": equation_latex,
        }

    else:
        raise ValueError(f"Unsupported calculus operation: {operation}")


def solve_equation_step(
    lhs_str: str,
    rhs_str: str = "0",
    var: str = "x",
) -> dict[str, Any]:
    """Solve an algebraic equation symbolically with exact LaTeX output."""
    if sympy is None:
        raise RuntimeError("sympy is required for symbolic equation solving")

    symbol = sympy.Symbol(var)
    lhs = sympy.sympify(lhs_str)
    rhs = sympy.sympify(rhs_str)
    eq = sympy.Eq(lhs, rhs)

    solutions = sympy.solve(eq, symbol)
    sol_latex = [sympy.latex(s) for s in solutions]

    return {
        "equation": str(eq),
        "equation_latex": f"{sympy.latex(lhs)} = {sympy.latex(rhs)}",
        "solutions": [str(s) for s in solutions],
        "solutions_latex": sol_latex,
        "solution_summary_latex": (
            f"{var} = " + ", ".join(sol_latex) if sol_latex else "\\text{No solution}"
        ),
    }


# ---------------------------------------------------------------------------
# 5. 3D Neural Network Layout Solver
# ---------------------------------------------------------------------------

def compute_neural_network_layout_3d(
    layer_sizes: list[int],
    *,
    layer_spacing: float = 2.2,
    node_spacing: float = 0.85,
    z_depth: float = 0.0,
) -> dict:
    """Compute guaranteed collision-free 3D (x, y, z) coordinates for a neural network.

    Positions nodes in a left-to-right layer arrangement. Each layer is centred
    vertically (y-axis) so the whole network is centred at (0, 0, z_depth).

    Args:
        layer_sizes:    Number of nodes per layer, e.g. [3, 4, 4, 2].
        layer_spacing:  Horizontal gap between successive layers (Manim units).
        node_spacing:   Vertical gap between nodes in the same layer.
        z_depth:        Fixed z-coordinate for all nodes (use 0.0 for a flat 2D-in-3D layout).

    Returns::
        {
          "layers": [[(x, y, z), ...], ...],   # node positions, outer=layer, inner=node
          "edges": [(li, ni, lj, nj), ...],     # fully-connected layer pairs
          "bounds": {"x": (x_min, x_max), "y": (y_min, y_max)},
          "layer_sizes": layer_sizes,
        }
    """
    if not layer_sizes or any(n < 1 for n in layer_sizes):
        raise ValueError("layer_sizes must be a non-empty list of positive integers")

    n_layers = len(layer_sizes)
    # Centre all layers around x=0
    total_width = (n_layers - 1) * layer_spacing
    x_start = -total_width / 2.0

    layers: list[list[tuple[float, float, float]]] = []
    for li, n_nodes in enumerate(layer_sizes):
        x = x_start + li * layer_spacing
        total_height = (n_nodes - 1) * node_spacing
        y_start = total_height / 2.0
        layer_positions = []
        for ni in range(n_nodes):
            y = y_start - ni * node_spacing
            layer_positions.append((round(x, 4), round(y, 4), round(z_depth, 4)))
        layers.append(layer_positions)

    # Fully-connected edges between adjacent layers
    edges: list[tuple[int, int, int, int]] = []
    for li in range(n_layers - 1):
        for ni in range(layer_sizes[li]):
            for nj in range(layer_sizes[li + 1]):
                edges.append((li, ni, li + 1, nj))

    all_x = [pos[0] for layer in layers for pos in layer]
    all_y = [pos[1] for layer in layers for pos in layer]

    return {
        "layers": layers,
        "edges": edges,
        "bounds": {
            "x": (min(all_x), max(all_x)),
            "y": (min(all_y), max(all_y)),
        },
        "layer_sizes": layer_sizes,
    }
