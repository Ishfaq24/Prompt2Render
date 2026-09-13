"""3D Neural Network Mobject for Prompt2Render Manim scenes.

Provides a ready-made, collision-free 3D neural network visualisation
with animatable forward-pass signal propagation.

Usage in a ThreeDScene::

    from prompt2render.assets.mobjects import NeuralNetworkMobject3D

    class SceneNN(ThreeDScene):
        def construct(self):
            self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
            net = NeuralNetworkMobject3D([3, 4, 4, 2])
            self.add(net)
            self.wait(0.5)
            self.play(net.animate_forward_pass(color=YELLOW))
            self.wait(1)
"""
from __future__ import annotations

from typing import Any

try:
    from manim import (
        BLUE, DEGREES, DOWN, GRAY, GREEN, LEFT, ORIGIN, RIGHT, UP, WHITE,
        Animation, AnimationGroup, Circle, Dot3D, FadeIn, FadeOut, Group,
        Indicate, Line, Mobject, Rectangle, Succession, Text, VGroup, VMobject,
        rate_functions,
    )
    import numpy as np
except ImportError:
    # Allow import without Manim (e.g. in unit tests that test layout only)
    VGroup = object  # type: ignore
    np = None  # type: ignore


class NeuralNetworkMobject3D(VGroup):
    """A 3D neural network diagram with layer nodes and edges.

    Built on top of ``compute_neural_network_layout_3d`` from
    ``symbolic_engine`` so all node positions are mathematically
    guaranteed to be collision-free.

    Args:
        layer_sizes:      Number of nodes per layer, e.g. [3, 4, 4, 2].
        node_radius:      Radius of each neuron sphere.
        node_color:       Default node fill colour.
        edge_color:       Colour for inter-layer connections.
        layer_spacing:    Horizontal distance between layers (Manim units).
        node_spacing:     Vertical distance between nodes in the same layer.
        show_labels:      Whether to render layer-index labels.
    """

    def __init__(
        self,
        layer_sizes: list[int],
        *,
        node_radius: float = 0.18,
        node_color: Any = BLUE,
        edge_color: Any = GRAY,
        layer_spacing: float = 2.2,
        node_spacing: float = 0.85,
        show_labels: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        from prompt2render.symbolic_engine import compute_neural_network_layout_3d

        layout = compute_neural_network_layout_3d(
            layer_sizes,
            layer_spacing=layer_spacing,
            node_spacing=node_spacing,
        )

        self._layer_sizes = layer_sizes
        self._node_dots: list[list[Any]] = []  # [layer][node] -> Dot3D
        self._edge_lines: list[Any] = []

        if np is None:
            raise RuntimeError("numpy is required for NeuralNetworkMobject3D")

        # Build nodes
        for li, layer_pos in enumerate(layout["layers"]):
            layer_dots: list[Any] = []
            for ni, (x, y, z) in enumerate(layer_pos):
                dot = Dot3D(
                    point=np.array([x, y, z]),
                    radius=node_radius,
                    color=node_color,
                )
                layer_dots.append(dot)
                self.add(dot)
            self._node_dots.append(layer_dots)

        # Build edges (lines between adjacent layers)
        for li, ni, lj, nj in layout["edges"]:
            x1, y1, z1 = layout["layers"][li][ni]
            x2, y2, z2 = layout["layers"][lj][nj]
            line = Line(
                start=np.array([x1, y1, z1]),
                end=np.array([x2, y2, z2]),
                color=edge_color,
                stroke_width=1.0,
                stroke_opacity=0.4,
            )
            self._edge_lines.append(line)
            self.add(line)

    def animate_forward_pass(
        self,
        color: Any = None,
        run_time_per_layer: float = 0.7,
    ) -> Any:
        """Return a Succession animation that lights up neurons layer by layer.

        Each layer's nodes flash in the given colour in sequence, simulating
        signal propagation from input to output.

        Args:
            color:              Highlight colour (defaults to GREEN).
            run_time_per_layer: Duration of each layer flash.

        Returns:
            A Manim ``Succession`` animation safe to pass to ``self.play()``.
        """
        if color is None:
            color = GREEN
        layer_anims = []
        for layer_dots in self._node_dots:
            layer_anims.append(
                AnimationGroup(
                    *[Indicate(dot, color=color, scale_factor=1.5,
                               run_time=run_time_per_layer,
                               rate_func=rate_functions.there_and_back)
                      for dot in layer_dots]
                )
            )
        return Succession(*layer_anims)

    def get_node(self, layer: int, node: int) -> Any:
        """Return the Dot3D for the specified layer and node index."""
        return self._node_dots[layer][node]
