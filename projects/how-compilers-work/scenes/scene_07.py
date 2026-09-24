from manim import *
import numpy as np

class Scene07(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("7. Code Generation and Register Allocation", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 8.4s] Compiler's backend converts IR to native assembly
        backend_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.5, height=0.65, color="#00F0FF", fill_opacity=0.2),
            Text("Phase 5: Backend & Register Allocation", font_size=15, color="#00F0FF")
        ).shift(UP * 2.2)
        self.play(FadeIn(backend_badge, shift=DOWN*0.2), run_time=1.2)
        self.wait(2.0)

        # [8.7s -> 12.9s] CPUs possess limited physical registers (Placed Top-Right)
        self.play(backend_badge.animate.scale(0.8).to_edge(UP, buff=1.0).to_edge(LEFT, buff=0.8), run_time=1.0)

        reg_box = RoundedRectangle(corner_radius=0.12, width=5.6, height=1.3, stroke_color="#F59E0B", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        reg_title = Text("Physical CPU Registers (Hardware):", font_size=13, color="#F59E0B")
        reg_slots = VGroup(
            VGroup(RoundedRectangle(corner_radius=0.08, width=1.1, height=0.55, stroke_color="#F59E0B", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.9), Text("EAX", font_size=13, color="#F59E0B")),
            VGroup(RoundedRectangle(corner_radius=0.08, width=1.1, height=0.55, stroke_color="#388BFD", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.9), Text("EBX", font_size=13, color="#388BFD")),
            VGroup(RoundedRectangle(corner_radius=0.08, width=1.1, height=0.55, stroke_color="#10B981", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.9), Text("ECX", font_size=13, color="#10B981")),
            VGroup(RoundedRectangle(corner_radius=0.08, width=1.1, height=0.55, stroke_color="#A855F7", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.9), Text("EDX", font_size=13, color="#A855F7"))
        ).arrange(RIGHT, buff=0.18)
        reg_content = VGroup(reg_title, reg_slots).arrange(DOWN, buff=0.15)
        reg_card = VGroup(reg_box, reg_content).move_to(np.array([3.6, 1.2, 0]))

        self.play(FadeIn(reg_card, shift=LEFT*0.3), run_time=1.5)
        self.wait(2.7)

        # [13.2s -> 25.2s] Register allocation via Graph Coloring (Left Container)
        graph_box = RoundedRectangle(corner_radius=0.15, width=5.6, height=3.6, stroke_color="#64748B", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9).move_to(np.array([-3.6, -0.1, 0]))
        graph_title = Text("Interference Graph (Chaitin's Coloring):", font_size=13, color="#94A3B8").move_to(np.array([-3.6, 1.2, 0]))

        # Graph nodes with safe internal positioning inside graph_box
        c1 = Circle(radius=0.35, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([-4.8, 0.1, 0]))
        t1 = Text("count", font_size=12, color=WHITE).move_to(c1)
        node1 = VGroup(c1, t1)

        c2 = Circle(radius=0.35, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([-3.6, 0.6, 0]))
        t2 = Text("t0", font_size=12, color=WHITE).move_to(c2)
        node2 = VGroup(c2, t2)

        c3 = Circle(radius=0.35, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([-2.4, 0.1, 0]))
        t3 = Text("total", font_size=12, color=WHITE).move_to(c3)
        node3 = VGroup(c3, t3)

        edge_a = Line(c1.get_center(), c2.get_center(), color="#64748B", stroke_width=1.5)
        edge_b = Line(c2.get_center(), c3.get_center(), color="#64748B", stroke_width=1.5)

        # Concise string under 42 chars with scale_to_fit_width so it fits inside graph_box
        map_label = Text("Alloc: count, t0 -> EAX | total -> Stack", font_size=12, color="#10B981").scale_to_fit_width(4.5).move_to(np.array([-3.6, -1.2, 0]))

        graph_mobs = VGroup(graph_box, graph_title, edge_a, edge_b, node1, node2, node3)

        self.play(FadeIn(graph_mobs), run_time=2.0)
        self.wait(1.5)

        # Color the graph nodes (mapping to physical registers)
        self.play(
            c1.animate.set_stroke(color="#F59E0B", width=2.5).set_fill(color="#F59E0B", opacity=0.25),
            c2.animate.set_stroke(color="#F59E0B", width=2.5).set_fill(color="#F59E0B", opacity=0.25),
            c3.animate.set_stroke(color="#10B981", width=2.5).set_fill(color="#10B981", opacity=0.25),
            run_time=2.0
        )
        self.play(Write(map_label), run_time=1.5)
        self.wait(3.8)

        # [25.5s -> 35.9s] Emitting final native assembly (Bottom-Right)
        asm_box = RoundedRectangle(corner_radius=0.12, width=5.6, height=2.2, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        asm_title = Text("Emitted x86_64 Assembly:", font_size=13, color="#00F0FF")
        asm_lines = VGroup(
            Text("mov  eax, DWORD PTR [rbp-4]  ; load 'count'", font="monospace", font_size=11, color="#E2E8F0"),
            Text("shl  eax, 1                   ; count * 2", font="monospace", font_size=11, color="#10B981"),
            Text("add  eax, 5                   ; + 5", font="monospace", font_size=11, color="#10B981"),
            Text("mov  DWORD PTR [rbp-8], eax  ; store 'total'", font="monospace", font_size=11, color="#E2E8F0")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)

        asm_content = VGroup(asm_title, asm_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        asm_card = VGroup(asm_box, asm_content).move_to(np.array([3.6, -1.0, 0]))

        self.play(FadeIn(asm_card, shift=UP*0.2), run_time=2.0)
        self.wait(3.5)

        self.play(Indicate(asm_card, color="#10B981", scale_factor=1.03), run_time=2.0)
        self.wait(2.9)