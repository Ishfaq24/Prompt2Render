from manim import *
import math
import numpy as np

class Scene01(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("1. The Grand Translation: Bridging Human Thought to Silicon", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 7.3s] Human code on the left
        # Code card: width 4.2, placed on left
        code_box = RoundedRectangle(corner_radius=0.15, width=4.2, height=3.0, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        code_title = Text("source.c", font="monospace", font_size=13, color="#94A3B8")
        code_lines = VGroup(
            Text("int count = 10;", font="monospace", font_size=14, color="#E2E8F0"),
            Text("int total;", font="monospace", font_size=14, color="#E2E8F0"),
            Text("total = count * 2 + 5;", font="monospace", font_size=14, color="#00F0FF")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        code_content = VGroup(code_title, code_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        code_card = VGroup(code_box, code_content).move_to(np.array([-4.4, 0.0, 0]))

        self.play(FadeIn(code_card, shift=RIGHT*0.3), run_time=1.0)
        self.wait(2.0)

        # [7.6s -> 11.6s] Hardware CPU representation on the right
        cpu_box = RoundedRectangle(corner_radius=0.15, width=4.2, height=3.0, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        cpu_title = Text("CPU Hardware Silicon", font_size=14, color="#10B981")
        cpu_sub = Text("Registers & Logic Gates", font_size=12, color="#94A3B8")
        cpu_diagram = VGroup(
            Rectangle(width=1.6, height=0.7, stroke_color="#388BFD", fill_color="#1E293B", fill_opacity=0.8),
            Text("ALU", font_size=14, color="#388BFD")
        )
        cpu_content = VGroup(cpu_title, cpu_diagram, cpu_sub).arrange(DOWN, buff=0.25)
        cpu_card = VGroup(cpu_box, cpu_content).move_to(np.array([4.4, 0.0, 0]))

        self.play(FadeIn(cpu_card, shift=LEFT*0.3), run_time=1.0)
        self.wait(3.0)

        # [11.9s -> 18.7s] Transform the right side into raw hexadecimal machine opcodes & binary
        binary_title = Text("Machine Binary / Hex", font_size=14, color="#10B981")
        binary_lines = VGroup(
            Text("01001000 10001011", font="monospace", font_size=13, color="#10B981"),
            Text("0x8B 0x45 0xFC", font="monospace", font_size=13, color="#FFB703"),
            Text("01001000 11010001", font="monospace", font_size=13, color="#10B981"),
            Text("0xD1 0xE0", font="monospace", font_size=13, color="#A855F7")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        binary_content = VGroup(binary_title, binary_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        binary_box = RoundedRectangle(corner_radius=0.15, width=4.2, height=3.0, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        binary_container = VGroup(binary_box, binary_content).move_to(np.array([4.4, 0.0, 0]))

        self.play(Transform(cpu_card, binary_container), run_time=1.2)
        self.wait(2.0)

        # [19.0s -> 21.3s] Draw the compiler bridge between them
        bridge_box = RoundedRectangle(corner_radius=0.15, width=2.8, height=2.2, stroke_color="#FFB703", stroke_width=2, fill_color="#0F172A", fill_opacity=0.95)
        bridge_title = Text("The Compiler", font_size=17, color="#FFB703").move_to(bridge_box.get_center())
        bridge_group = VGroup(bridge_box, bridge_title).move_to(np.array([0.0, 0.0, 0]))

        arrow1 = Arrow(code_card.get_right(), bridge_group.get_left(), color="#00F0FF", buff=0.15, stroke_width=3, max_tip_length_to_length_ratio=0.3)
        arrow2 = Arrow(bridge_group.get_right(), binary_container.get_left(), color="#FFB703", buff=0.15, stroke_width=3, max_tip_length_to_length_ratio=0.3)

        self.play(
            FadeIn(bridge_group),
            GrowArrow(arrow1),
            GrowArrow(arrow2),
            run_time=1.5
        )
        self.wait(0.8)

        # [21.6s -> 28.8s] Elaborate pipeline stages inside the compiler bridge
        stages = VGroup(
            Text("The Compiler", font_size=14, color="#FFB703"),
            Line(LEFT*1.0, RIGHT*1.0, color="#FFB703", stroke_width=1),
            Text("Lexer", font_size=13, color=WHITE),
            Text("Parser", font_size=13, color=WHITE),
            Text("Optimizer", font_size=13, color=WHITE),
            Text("Codegen", font_size=13, color=WHITE)
        ).arrange(DOWN, buff=0.12).move_to(bridge_box.get_center())

        self.play(
            Transform(bridge_title, stages[0]),
            FadeIn(stages[1:]),
            run_time=1.5
        )
        self.wait(2.0)

        # [29.1s -> 34.0s] Final emphasis on human text reshaping into silicon instructions
        self.play(
            Indicate(code_card, color="#00F0FF", scale_factor=1.03),
            Indicate(cpu_card, color="#10B981", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(2.9)