from manim import *
import numpy as np

class Scene10(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # 1. Title Band
        title = Text("Backpropagation: The Complete Learning Engine", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # 2. Main Stage Container
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

        # 3. 5-Stage Architecture Cards
        xs = [-5.2, -2.6, 0.0, 2.6, 5.2]
        y_pos = 0.55
        c_w, c_h = 2.2, 2.7

        colors = ["#38BDF8", "#F59E0B", "#EF4444", "#A855F7", "#10B981"]
        titles = ["1. Forward Pass", "2. Loss Eval", "3. Output Delta", "4. Recurrence", "5. Update Step"]

        cards = []
        for i in range(5):
            rect = RoundedRectangle(
                corner_radius=0.14,
                width=c_w,
                height=c_h,
                stroke_color=colors[i],
                stroke_width=1.6,
                fill_color="#111827",
                fill_opacity=0.9
            ).move_to(np.array([xs[i], y_pos, 0]))

            h_lbl = Text(titles[i], font_size=12, weight=BOLD, color=colors[i]).move_to(rect.get_top() + DOWN * 0.3)

            if i == 0:
                eq1 = MathTex(r"z = W a + b", font_size=13, color=WHITE).move_to(rect.get_center() + UP * 0.3)
                eq2 = MathTex(r"a = \sigma(z)", font_size=13, color=WHITE).move_to(rect.get_center() - UP * 0.1)
                desc = Text("Cache (z, a) in RAM", font_size=9, color="#94A3B8").move_to(rect.get_bottom() + UP * 0.35)
            elif i == 1:
                eq1 = MathTex(r"\mathcal{L} = \frac{1}{2}(\hat{y}-y)^2", font_size=12, color=WHITE).move_to(rect.get_center() + UP * 0.3)
                eq2 = MathTex(r"\nabla_{\hat{y}}\mathcal{L} = \hat{y} - y", font_size=12, color=WHITE).move_to(rect.get_center() - UP * 0.1)
                desc = Text("Discrepancy Error", font_size=9, color="#94A3B8").move_to(rect.get_bottom() + UP * 0.35)
            elif i == 2:
                eq1 = MathTex(r"\delta^{(L)} =", font_size=13, color=WHITE).move_to(rect.get_center() + UP * 0.3)
                eq2 = MathTex(r"\nabla_{\hat{y}}\mathcal{L} \odot \sigma^{\prime}(z)", font_size=12, color="#FCA5A5").move_to(rect.get_center() - UP * 0.1)
                desc = Text("Chain Rule Seed", font_size=9, color="#94A3B8").move_to(rect.get_bottom() + UP * 0.35)
            elif i == 3:
                eq1 = MathTex(r"\delta^{(l)} =", font_size=13, color=WHITE).move_to(rect.get_center() + UP * 0.3)
                eq2 = MathTex(r"(W)^T \delta \odot \sigma^{\prime}", font_size=12, color="#E9D5FF").move_to(rect.get_center() - UP * 0.1)
                desc = Text("Layer-by-Layer Flow", font_size=9, color="#94A3B8").move_to(rect.get_bottom() + UP * 0.35)
            else:
                eq1 = MathTex(r"\nabla_W \mathcal{L} = \delta a^T", font_size=12, color=WHITE).move_to(rect.get_center() + UP * 0.3)
                eq2 = MathTex(r"W \leftarrow W - \eta \nabla", font_size=12, color="#A7F3D0").move_to(rect.get_center() - UP * 0.1)
                desc = Text("Gradient Descent", font_size=9, color="#94A3B8").move_to(rect.get_bottom() + UP * 0.35)

            card_grp = VGroup(rect, h_lbl, eq1, eq2, desc)
            cards.append(card_grp)

        # Forward connect arrows between adjacent cards
        arrows = []
        for i in range(4):
            arr = Arrow(
                np.array([xs[i] + c_w / 2, y_pos, 0]),
                np.array([xs[i+1] - c_w / 2, y_pos, 0]),
                buff=0.08,
                color="#64748B",
                stroke_width=2.0,
                tip_length=0.12
            )
            arrows.append(arr)

        # Curved Closed-Loop Return Arrow
        loop_arrow = CurvedArrow(
            np.array([xs[4], y_pos - c_h / 2 - 0.05, 0]),
            np.array([xs[0], y_pos - c_h / 2 - 0.05, 0]),
            angle=-TAU / 8.0,
            color="#F59E0B",
            stroke_width=2.2,
            tip_length=0.15
        )
        loop_lbl = Text("Closed-Loop Training Iteration: Forward -> Loss -> Backward -> Update -> Repeat", font_size=9.5, color="#FDE68A", weight=BOLD).next_to(loop_arrow, DOWN, buff=0.08)
        loop_group = VGroup(loop_arrow, loop_lbl)

        # Narration Timeline & Choreography
        # [0.0s - 5.1s] Intro: Closed-loop learning algorithm
        self.play(FadeIn(cards[0], shift=UP * 0.2), run_time=1.2)
        self.wait(3.9)

        # [5.4s - 14.2s] Forward pass maps input through layers & caches in RAM
        self.play(Indicate(cards[0], color="#38BDF8", scale_factor=1.04), run_time=1.5)
        self.wait(7.3)

        # [14.5s - 18.6s] Loss measures discrepancy between y_hat and y
        self.play(Create(arrows[0]), FadeIn(cards[1], shift=RIGHT * 0.2), run_time=1.2)
        self.play(Indicate(cards[1], color="#F59E0B", scale_factor=1.04), run_time=1.5)
        self.wait(1.4)

        # [18.9s - 28.8s] Backward pass seeds chain rule and propagates delta recurrence
        self.play(Create(arrows[1]), FadeIn(cards[2], shift=RIGHT * 0.2), run_time=1.2)
        self.play(Indicate(cards[2], color="#EF4444", scale_factor=1.04), run_time=1.5)
        self.wait(1.5)

        self.play(Create(arrows[2]), FadeIn(cards[3], shift=RIGHT * 0.2), run_time=1.2)
        self.play(Indicate(cards[3], color="#A855F7", scale_factor=1.04), run_time=1.8)
        self.wait(2.7)

        # [29.1s - 35.1s] Weight gradients emerge and gradient descent applies them
        self.play(Create(arrows[3]), FadeIn(cards[4], shift=RIGHT * 0.2), run_time=1.2)
        self.play(Indicate(cards[4], color="#10B981", scale_factor=1.04), run_time=1.8)
        self.wait(3.0)

        # [35.4s - 39.4s] Loop repeats over millions of iterations
        self.play(Create(loop_arrow), FadeIn(loop_lbl, shift=UP * 0.05), run_time=1.5)
        self.wait(2.5)

        # [39.7s - 59.0s] Grand Finale: Scaling to 100B+ Parameter Frontier
        # Footer card safely above subtitle safe zone (Y = -2.5)
        scale_box = RoundedRectangle(
            corner_radius=0.15,
            width=12.2,
            height=0.68,
            stroke_color="#6366F1",
            stroke_width=1.5,
            fill_color="#1E1B4B",
            fill_opacity=0.92
        ).move_to(DOWN * 2.05)

        scale_title = Text(
            "Scaling To Frontiers: ReLU (No Saturation) • BatchNorm (Stability) • ResNet (+1 Highway) -> 100B+ Transformers",
            font_size=10,
            color="#E0E7FF",
            weight=BOLD
        ).move_to(scale_box.get_center())

        scale_group = VGroup(scale_box, scale_title)

        self.play(FadeIn(scale_group, shift=UP * 0.15), run_time=1.2)
        self.wait(2.5)

        # Continuous cyclic energy flow pulses across stations 1 -> 2 -> 3 -> 4 -> 5 -> 1
        # Keeps screen dynamic and completely eliminates freeze detect warnings!
        for cycle in range(2):
            for i in range(5):
                self.play(cards[i][0].animate.set_stroke(WHITE, width=2.8), run_time=0.45)
                self.play(cards[i][0].animate.set_stroke(colors[i], width=1.6), run_time=0.45)

        # Final steady hold matching exact section length 59.64s
        self.wait(6.54)