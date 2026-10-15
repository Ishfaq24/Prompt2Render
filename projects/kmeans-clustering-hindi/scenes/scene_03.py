from manim import *

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Lloyd's Algorithm: The 4 Core Iterative Steps", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("लॉयड का एल्गोरिदम: चक्रीय कार्यप्रणाली और कन्वर्जेंस", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. The 4 Step Cards
        coords = [
            (LEFT * 4.4 + UP * 0.4, "Step 1: Initialization", "Choose K initial centroids\nrandomly in feature space", "#38BDF8"),
            (LEFT * 1.5 + DOWN * 0.8, "Step 2: Assignment", "Assign each point x_i\nto the nearest centroid", "#10B981"),
            (RIGHT * 1.5 + UP * 0.4, "Step 3: Update", "Recalculate centroids as\nthe mean of assigned points", "#F59E0B"),
            (RIGHT * 4.4 + DOWN * 0.8, "Step 4: Convergence", "Check if centroids stopped\nmoving or delta J < epsilon", "#EC4899"),
        ]

        cards = []
        for pos, stitle, sdesc, col in coords:
            box = RoundedRectangle(
                corner_radius=0.15, width=2.7, height=2.8,
                stroke_color=col, stroke_width=1.5,
                fill_color="#0F172A", fill_opacity=0.9
            ).move_to(pos)
            h = Text(stitle, font_size=12, color=col, weight=BOLD).move_to(box.get_top() + DOWN * 0.4)
            d = Text(sdesc, font_size=10, color="#CBD5E1").move_to(box.get_center() + DOWN * 0.2)
            cards.append(VGroup(box, h, d))

        for i, card in enumerate(cards):
            self.play(FadeIn(card, shift=UP*0.2), run_time=1.5)
            self.wait(3.5 if i < 3 else 5.0)

        # 3. Connecting Flow Arrows
        a1 = Arrow(cards[0].get_right(), cards[1].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        a2 = Arrow(cards[1].get_right(), cards[2].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        a3 = Arrow(cards[2].get_right(), cards[3].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        arrows = VGroup(a1, a2, a3)
        self.play(Create(arrows), run_time=2.0)
        self.wait(3.0)

        # 4. Repeat Loop Back
        loop_curve = CurvedArrow(
            cards[3].get_bottom() + LEFT * 0.3,
            cards[1].get_bottom() + RIGHT * 0.3,
            radius=4.5, color="#F59E0B", stroke_width=3.0
        )
        loop_lbl = Text("Repeat Until Convergence (Centroids Stable)", font_size=12, color="#FDE68A", weight=BOLD).next_to(loop_curve, DOWN, buff=0.15)
        self.play(Create(loop_curve), FadeIn(loop_lbl), run_time=2.0)
        self.wait(15.0)
