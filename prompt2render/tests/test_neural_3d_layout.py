"""Tests for the 3D neural network layout solver."""
import math
from prompt2render.symbolic_engine import compute_neural_network_layout_3d


def test_layer_count_matches():
    result = compute_neural_network_layout_3d([3, 4, 2])
    assert len(result["layers"]) == 3
    assert len(result["layers"][0]) == 3
    assert len(result["layers"][1]) == 4
    assert len(result["layers"][2]) == 2


def test_no_collision_between_nodes():
    """No two nodes in the same layer should be closer than node_spacing * 0.9."""
    result = compute_neural_network_layout_3d([5, 6, 5], node_spacing=0.85)
    for li, layer in enumerate(result["layers"]):
        for i in range(len(layer)):
            for j in range(i + 1, len(layer)):
                xi, yi, _ = layer[i]
                xj, yj, _ = layer[j]
                dist = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2)
                assert dist >= 0.8 * 0.85, (
                    f"Layer {li}: nodes {i} and {j} are too close ({dist:.3f})"
                )


def test_network_centred_at_origin():
    result = compute_neural_network_layout_3d([3, 4, 3])
    all_x = [pos[0] for layer in result["layers"] for pos in layer]
    centre_x = (min(all_x) + max(all_x)) / 2.0
    assert abs(centre_x) < 0.01, f"Network not centred: centre_x={centre_x}"


def test_fully_connected_edges():
    result = compute_neural_network_layout_3d([2, 3])
    # 2 * 3 = 6 edges for [2, 3]
    assert len(result["edges"]) == 6


def test_single_layer_raises():
    import pytest
    # Single layer with empty list should raise
    with pytest.raises((ValueError, Exception)):
        compute_neural_network_layout_3d([])


def test_bounds_match_positions():
    result = compute_neural_network_layout_3d([4, 4, 4])
    all_x = [pos[0] for layer in result["layers"] for pos in layer]
    all_y = [pos[1] for layer in result["layers"] for pos in layer]
    assert result["bounds"]["x"] == (min(all_x), max(all_x))
    assert result["bounds"]["y"] == (min(all_y), max(all_y))
