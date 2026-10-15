from manim import *

class Scene02(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 36.86

        title = Text("Three Paradigms of Machine Learning", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ ہٕنٛدی ترٛے اہم قسٕم", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # Card 1: Supervised
        c1 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#0284C7", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.9).move_to(LEFT * 4.2 + DOWN * 0.55)
        t1 = Text("Supervised", font_size=16, weight=BOLD, color="#38BDF8").move_to(c1.get_top() + DOWN * 0.35)
        s1 = Text("سُوپر وائزڈ (لیبلڈ ڈیٹا)", font="Arial", font_size=11, color="#7DD3FC").next_to(t1, DOWN, buff=0.08)
        pill1 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#0369A1", fill_color="#075985", fill_opacity=0.85).move_to(c1.get_center() + UP * 0.45)
        ptxt1 = Text("Input X -> Label Y", font_size=10, color=WHITE, weight=BOLD).move_to(pill1.get_center())
        # Visual
        d_a = Dot(point=c1.get_center() + LEFT*0.5 + DOWN*0.2, color="#38BDF8", radius=0.07)
        d_b = Dot(point=c1.get_center() + RIGHT*0.5 + DOWN*0.4, color="#F43F5E", radius=0.07)
        sep_l = Line(start=c1.get_center() + LEFT*0.8 + DOWN*0.6, end=c1.get_center() + RIGHT*0.8 + DOWN*0.0, color="#64748B", stroke_width=1.5)
        b_a1 = Text("• Classification", font_size=11, color="#CBD5E1").move_to(c1.get_bottom() + UP * 0.8)
        b_a2 = Text("• Regression", font_size=11, color="#CBD5E1").next_to(b_a1, DOWN, buff=0.12)
        grp1 = VGroup(c1, t1, s1, pill1, ptxt1, d_a, d_b, sep_l, b_a1, b_a2)

        # Card 2: Unsupervised
        c2 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.9).move_to(DOWN * 0.55)
        t2 = Text("Unsupervised", font_size=16, weight=BOLD, color="#34D399").move_to(c2.get_top() + DOWN * 0.35)
        s2 = Text("اَن سُوپر وائزڈ (بغیر لیبل)", font="Arial", font_size=11, color="#6EE7B7").next_to(t2, DOWN, buff=0.08)
        pill2 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#047857", fill_color="#065F46", fill_opacity=0.85).move_to(c2.get_center() + UP * 0.45)
        ptxt2 = Text("Unlabeled Patterns", font_size=10, color=WHITE, weight=BOLD).move_to(pill2.get_center())
        # Visual
        cir1 = Circle(radius=0.28, color="#34D399", fill_opacity=0.2).move_to(c2.get_center() + LEFT*0.5 + DOWN*0.3)
        cir2 = Circle(radius=0.28, color="#A78BFA", fill_opacity=0.2).move_to(c2.get_center() + RIGHT*0.5 + DOWN*0.3)
        b_b1 = Text("• Clustering", font_size=11, color="#CBD5E1").move_to(c2.get_bottom() + UP * 0.8)
        b_b2 = Text("• Dimensionality", font_size=11, color="#CBD5E1").next_to(b_b1, DOWN, buff=0.12)
        grp2 = VGroup(c2, t2, s2, pill2, ptxt2, cir1, cir2, b_b1, b_b2)

        # Card 3: Reinforcement
        c3 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.9).move_to(RIGHT * 4.2 + DOWN * 0.55)
        t3 = Text("Reinforcement", font_size=16, weight=BOLD, color="#FBBF24").move_to(c3.get_top() + DOWN * 0.35)
        s3 = Text("ری اِنفورسمنٹ (انعام و سزا)", font="Arial", font_size=11, color="#FDE68A").next_to(t3, DOWN, buff=0.08)
        pill3 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#B45309", fill_color="#92400E", fill_opacity=0.85).move_to(c3.get_center() + UP * 0.45)
        ptxt3 = Text("Agent <-> Reward", font_size=10, color=WHITE, weight=BOLD).move_to(pill3.get_center())
        # Visual
        carrow = CurvedArrow(start_point=c3.get_center() + LEFT*0.6 + DOWN*0.35, end_point=c3.get_center() + RIGHT*0.6 + DOWN*0.35, angle=TAU/3, color="#FBBF24")
        b_c1 = Text("• Policy & Rewards", font_size=11, color="#CBD5E1").move_to(c3.get_bottom() + UP * 0.8)
        b_c2 = Text("• Robotics & Games", font_size=11, color="#CBD5E1").next_to(b_c1, DOWN, buff=0.12)
        grp3 = VGroup(c3, t3, s3, pill3, ptxt3, carrow, b_c1, b_c2)

        self.play(FadeIn(grp1, shift=UP*0.2), run_time=1.2)
        self.wait(1.2)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.2)
        self.wait(1.2)
        self.play(FadeIn(grp3, shift=UP*0.2), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.2 + 1.2 + 1.2 + 1.2 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
