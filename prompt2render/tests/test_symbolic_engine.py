"""Unit tests for Neuro-Symbolic Invariant Engine."""

from __future__ import annotations

from prompt2render.symbolic_engine import (
    compute_tree_layout,
    derive_calculus_step,
    solve_equation_step,
    trace_binary_search,
    trace_bst_insertion,
    trace_euclid_gcd,
    trace_sorting,
)


def test_trace_sorting_bubble():
    arr = [5, 2, 8, 1, 9]
    steps = trace_sorting(arr, algorithm="bubble")

    assert len(steps) > 5
    assert steps[0]["type"] == "initial"
    assert steps[-1]["type"] == "done"
    assert steps[-1]["array"] == [1, 2, 5, 8, 9]

    # Verify presence of comparison and swap events
    types = {s["type"] for s in steps}
    assert "compare" in types
    assert "swap" in types
    assert "sorted_mark" in types


def test_trace_sorting_insertion():
    arr = [4, 3, 2, 1]
    steps = trace_sorting(arr, algorithm="insertion")

    assert steps[-1]["type"] == "done"
    assert steps[-1]["array"] == [1, 2, 3, 4]
    types = {s["type"] for s in steps}
    assert "insert" in types


def test_trace_binary_search_found():
    arr = [2, 4, 6, 8, 10, 12, 14, 16]
    steps = trace_binary_search(arr, target=10)

    assert len(steps) >= 1
    assert any(s["found"] for s in steps)
    last_step = steps[-1]
    assert last_step["found"] is True
    assert last_step["mid_val"] == 10
    assert last_step["mid"] == 4


def test_trace_binary_search_not_found():
    arr = [1, 3, 5, 7, 9]
    steps = trace_binary_search(arr, target=4)

    assert len(steps) >= 2
    assert not any(s["found"] for s in steps)


def test_trace_euclid_gcd():
    steps = trace_euclid_gcd(48, 18)

    assert len(steps) == 4
    # 48 = 18*2 + 12
    assert steps[0]["quotient"] == 2
    assert steps[0]["remainder"] == 12
    # 18 = 12*1 + 6
    assert steps[1]["quotient"] == 1
    assert steps[1]["remainder"] == 6
    # 12 = 6*2 + 0
    assert steps[2]["quotient"] == 2
    assert steps[2]["remainder"] == 0
    # Final GCD
    assert steps[3]["gcd"] == 6
    assert "\\gcd(48, 18) = 6" in steps[3]["equation_latex"]


def test_compute_tree_layout():
    nodes = [10, 5, 15, 2]
    edges = [(10, 5), (10, 15), (5, 2)]
    root = 10

    coords = compute_tree_layout(nodes, edges, root=root, total_width=8.0, total_height=4.0)

    assert len(coords) == 4
    # Root y must be strictly greater than children y
    assert coords[10][1] > coords[5][1]
    assert coords[10][1] > coords[15][1]
    assert coords[5][1] > coords[2][1]

    # Left child must be left of right child
    assert coords[5][0] < coords[15][0]


def test_trace_bst_insertion():
    values = [10, 5, 15, 2]
    states = trace_bst_insertion(values)

    assert len(states) == 4
    final_state = states[-1]
    assert set(final_state["nodes"]) == {10, 5, 15, 2}
    assert (10, 5) in final_state["edges"]
    assert (10, 15) in final_state["edges"]
    assert (5, 2) in final_state["edges"]


def test_derive_calculus_step():
    # Derivative of x^3 + 2x
    diff_res = derive_calculus_step("x**3 + 2*x", var="x", operation="diff")
    assert diff_res["operation"] == "derivative"
    assert "3*x**2 + 2" in diff_res["result_expr"]
    assert "\\frac{d}{dx}" in diff_res["equation_latex"]

    # Integral of cos(x)
    int_res = derive_calculus_step("cos(x)", var="x", operation="integrate")
    assert int_res["operation"] == "integral"
    assert "sin(x)" in int_res["result_expr"]
    assert "\\int" in int_res["equation_latex"]


def test_solve_equation_step():
    # Solve x^2 - 9 = 0
    res = solve_equation_step("x**2 - 9", "0", var="x")
    assert set(res["solutions"]) == {"-3", "3"}
    assert "-3" in res["solutions_latex"]
    assert "3" in res["solutions_latex"]
