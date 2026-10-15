from manim import *
import numpy as np

class Scene02(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # 1. Title Band
        title = Text("The Chain Rule: Calculus of Responsibility", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # 2. Main Stage Container Card
        stage_bg = RoundedRectangle(
            corner_radius=0.2,
            width=13.0,
            height=5.2,
            stroke_color="#1E293B",
            stroke_width=1.5,
            fill_color="#0F172A",
            fill_opacity=0.6
        ).shift(UP * 0.1)
        self.play(FadeIn(stage_bg), run_time=0.8)

        # 3. Three Cascaded Function Boxes
        box_w, box_h = 3.2, 1.5
        y_box = 1.0

        # Box 1: Pre-activation
        b1_rect = RoundedRectangle(corner_radius=0.15, width=box_w, height=box_h, color="#38BDF8", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.85)
        b1_title = Text("1. Linear Combination", font_size=12, color="#7DD3FC", weight=BOLD).move_to(b1_rect.get_top() + DOWN * 0.28)
        b1_eq = MathTex(r"z = w \cdot a + b", font_size=22, color=WHITE).next_to(b1_title, DOWN, buff=0.2)
        box1 = VGroup(b1_rect, b1_title, b1_eq).move_to(np.array([-4.4, y_box, 0]))

        # Box 2: Activation
        b2_rect = RoundedRectangle(corner_radius=0.15, width=box_w, height=box_h, color="#C084FC", stroke_width=2.0, fill_color="#3B0764", fill_opacity=0.85)
        b2_title = Text("2. Activation Function", font_size=12, color="#E9D5FF", weight=BOLD).move_to(b2_rect.get_top() + DOWN * 0.28)
        b2_eq = MathTex(r"a = \sigma(z)", font_size=22, color=WHITE).next_to(b2_title, DOWN, buff=0.2)
        box2 = VGroup(b2_rect, b2_title, b2_eq).move_to(np.array([0.0, y_box, 0]))

        # Box 3: Loss Function
        b3_rect = RoundedRectangle(corner_radius=0.15, width=box_w, height=box_h, color="#34D399", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.85)
        b3_title = Text("3. Loss Function", font_size=12, color="#A7F3D0", weight=BOLD).move_to(b3_rect.get_top() + DOWN * 0.28)
        b3_eq = MathTex(r"L = \frac{1}{2}(\hat{y} - y)^2", font_size=22, color=WHITE).next_to(b3_title, DOWN, buff=0.2)
        box3 = VGroup(b3_rect, b3_title, b3_eq).move_to(np.array([4.4, y_box, 0]))

        # Forward Connecting Arrows
        fwd_arr1 = Arrow(box1.get_right(), box2.get_left(), buff=0.15, color="#FBBF24", stroke_width=2.5, tip_length=0.2)
        fwd_arr2 = Arrow(box2.get_right(), box3.get_left(), buff=0.15, color="#FBBF24", stroke_width=2.5, tip_length=0.2)
        fwd_lbl1 = MathTex("z", font_size=18, color="#FCD34D").next_to(fwd_arr1, UP, buff=0.1)
        fwd_lbl2 = MathTex("a", font_size=18, color="#FCD34D").next_to(fwd_arr2, UP, buff=0.1)

        fwd_group = VGroup(box1, fwd_arr1, fwd_lbl1, box2, fwd_arr2, fwd_lbl2, box3)

        # [0.0 - 3.8s] Intro boxes appear
        self.play(
            FadeIn(box1, shift=RIGHT * 0.3),
            GrowArrow(fwd_arr1), Write(fwd_lbl1),
            FadeIn(box2, shift=RIGHT * 0.3),
            GrowArrow(fwd_arr2), Write(fwd_lbl2),
            FadeIn(box3, shift=RIGHT * 0.3),
            run_time=2.0
        )

        # [4.1 - 15.1s] Chain Rule Equation display
        chain_box = RoundedRectangle(
            corner_radius=0.15,
            width=9.6,
            height=1.8,
            color="#818CF8",
            stroke_width=1.8,
            fill_color="#1E1B4B",
            fill_opacity=0.9
        ).move_to(DOWN * 1.1)

        chain_title = Text("The Chain Rule of Calculus", font_size=13, color="#C7D2FE", weight=BOLD).move_to(chain_box.get_top() + DOWN * 0.28)
        
        chain_formula = MathTex(
            r"\frac{\partial L}{\partial w}",
            r"=",
            r"\frac{\partial L}{\partial a}",
            r"\cdot",
            r"\frac{\partial a}{\partial z}",
            r"\cdot",
            r"\frac{\partial z}{\partial w}",
            font_size=28,
            color=WHITE
        ).next_to(chain_title, DOWN, buff=0.25)
        
        chain_formula[0].set_color("#F59E0B") # dL/dw in amber
        chain_formula[2].set_color("#34D399") # dL/da in green
        chain_formula[4].set_color("#C084FC") # da/dz in purple
        chain_formula[6].set_color("#38BDF8") # dz/dw in cyan

        chain_group = VGroup(chain_box, chain_title, chain_formula)

        self.play(FadeIn(chain_group, shift=UP * 0.3), run_time=1.5)

        # Reverse gradient flow arrows from Box 3 -> Box 2 -> Box 1
        rev_arr1 = CurvedArrow(box3.get_top() + LEFT * 0.5, box2.get_top() + RIGHT * 0.5, angle=TAU/6, color="#34D399", stroke_width=2.5)
        rev_arr2 = CurvedArrow(box2.get_top() + LEFT * 0.5, box1.get_top() + RIGHT * 0.5, angle=TAU/6, color="#C084FC", stroke_width=2.5)
        
        self.play(Create(rev_arr1), Create(rev_arr2), run_time=2.0)
        self.wait(5.5)

        # [15.5 - 18.7s] Factor 1: dL/da (Loss wrt Activation)
        self.play(
            Indicate(b3_rect, color="#34D399", scale_factor=1.06),
            Indicate(chain_formula[2], color="#34D399", scale_factor=1.2),
            run_time=1.4
        )
        self.wait(1.8)

        # [19.0 - 26.1s] Factor 2: da/dz (Activation Function Derivative)
        self.play(
            Indicate(b2_rect, color="#C084FC", scale_factor=1.06),
            Indicate(chain_formula[4], color="#C084FC", scale_factor=1.2),
            run_time=1.5
        )
        deriv_callout = MathTex(r"\sigma^{\prime}(z) = \sigma(z)(1 - \sigma(z))", font_size=18, color="#E9D5FF").next_to(box2, DOWN, buff=0.15)
        self.play(FadeIn(deriv_callout, shift=UP * 0.1), run_time=1.0)
        self.wait(4.6)

        # [26.5 - 29.8s] Factor 3: dz/dw (Pre-activation wrt Weight)
        self.play(
            FadeOut(deriv_callout),
            Indicate(b1_rect, color="#38BDF8", scale_factor=1.06),
            Indicate(chain_formula[6], color="#38BDF8", scale_factor=1.2),
            run_time=1.4
        )
        self.wait(1.9)

        # [30.1 - 33.7s] Each factor is simple to compute individually
        badge_card = RoundedRectangle(corner_radius=0.12, width=9.2, height=0.6, color="#F59E0B", stroke_width=1.5, fill_color="#451A03", fill_opacity=0.9).next_to(chain_box, DOWN, buff=0.15)
        badge_text = Text("Each local derivative is elementary to evaluate in closed form", font_size=12, color="#FDE68A", weight=BOLD).move_to(badge_card.get_center())
        local_badge = VGroup(badge_card, badge_text)
        
        self.play(FadeIn(local_badge, shift=UP * 0.15), run_time=1.0)
        self.wait(2.6)

        # [34.0 - 36.7s] The chain rule says multiply them together
        product_glow = SurroundingRectangle(chain_formula, color="#FBBF24", buff=0.15, stroke_width=2.5)
        self.play(Create(product_glow), run_time=1.0)
        self.wait(1.7)

        # [37.0 - 40.6s] Foundation of Backpropagation
        self.play(
            FadeOut(local_badge),
            FadeOut(product_glow),
            run_time=0.8
        )
        fnd_card = RoundedRectangle(corner_radius=0.12, width=9.2, height=0.6, color="#10B981", stroke_width=1.5, fill_color="#064E3B", fill_opacity=0.9).next_to(chain_box, DOWN, buff=0.15)
        fnd_text = Text("The Entire Mathematical Foundation of Deep Neural Learning", font_size=12, color="#A7F3D0", weight=BOLD).move_to(fnd_card.get_center())
        fnd_badge = VGroup(fnd_card, fnd_text)
        self.play(FadeIn(fnd_badge, shift=UP * 0.15), run_time=0.8)
        self.wait(2.8)

        # [40.9 - 47.7s] Arbitrary depth generalization
        self.play(FadeOut(fnd_badge), run_time=0.6)
        
        depth_card = RoundedRectangle(corner_radius=0.12, width=9.2, height=0.65, color="#818CF8", stroke_width=1.5, fill_color="#1E1B4B", fill_opacity=0.9).next_to(chain_box, DOWN, buff=0.15)
        depth_text = Text("Applied Layer by Layer Across Arbitrary Depth: 1 to 100+ Layers", font_size=12, color="#C7D2FE", weight=BOLD).move_to(depth_card.get_center())
        depth_badge = VGroup(depth_card, depth_text)
        
        self.play(FadeIn(depth_badge, shift=UP * 0.15), run_time=0.8)
        
        # Subtle energy flow across all three boxes until audio conclusion
        for b in [box3, box2, box1]:
            self.play(Indicate(b, color="#FBBF24", scale_factor=1.03), run_time=1.2)
        self.wait(2.2)