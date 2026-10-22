from manim import *

class Scene06(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 45.30

        # 1. Header Zone
        title = Text("Time & Space Complexity: Mathematical Analysis", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  ٹائم اور اسپیس کمپلیکسٹی کا ریاضیاتی تجزیہ (Best, Average & Worst Case)  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        # 2. Left Card: Best & Average Case O(n log n) (y = -0.10, height = 3.95 -> spans -2.07 to +1.87)
        c_left = RoundedRectangle(
            corner_radius=0.18, width=5.9, height=3.95,
            stroke_color="#10B981", stroke_width=2.2,
            fill_color="#0F172A", fill_opacity=0.92
        ).move_to(LEFT * 3.15 + DOWN * 0.10)

        lh = Text("Best & Average Case: O(n log n)", font="Segoe UI", font_size=15, weight=BOLD, color="#34D399").move_to(c_left.get_top() + DOWN * 0.35)
        ls = Text("  متوازن تقسیم: ہر لیول پر نصف عناصر  ", font="Arial", font_size=11, color="#6EE7B7").next_to(lh, DOWN, buff=0.08)

        l_rec_lbl = Text("Balanced Recurrence Relation:", font="Segoe UI", font_size=11, color="#94A3B8").move_to(c_left.get_top() + DOWN * 1.05)
        l_rec = MathTex(r"T(n) = 2T\left(\frac{n}{2}\right) + \Theta(n)", font_size=22, color="#38BDF8").next_to(l_rec_lbl, DOWN, buff=0.15)

        l_depth = Text("• Recursion Tree Height = log2(n) levels", font="Segoe UI", font_size=11, color=WHITE).next_to(l_rec, DOWN, buff=0.22)
        l_work = Text("• Work per Level = O(n) comparisons", font="Segoe UI", font_size=11, color="#CBD5E1").next_to(l_depth, DOWN, buff=0.12)
        l_res = MathTex(r"T(n) = \Theta(n \log_2 n)", font_size=23, color="#34D399").next_to(l_work, DOWN, buff=0.20)

        grp_left = VGroup(c_left, lh, ls, l_rec_lbl, l_rec, l_depth, l_work, l_res)

        # 3. Right Card: Worst Case O(n^2) (y = -0.10, height = 3.95 -> spans -2.07 to +1.87)
        c_right = RoundedRectangle(
            corner_radius=0.18, width=5.9, height=3.95,
            stroke_color="#F43F5E", stroke_width=2.2,
            fill_color="#0F172A", fill_opacity=0.92
        ).move_to(RIGHT * 3.15 + DOWN * 0.10)

        rh = Text("Worst Case: O(n^2)  (Unbalanced)", font="Segoe UI", font_size=15, weight=BOLD, color="#FB7185").move_to(c_right.get_top() + DOWN * 0.35)
        rs = Text("  پہلے سے سورٹڈ ایرے اور خراب پیوٹ کا انتخاب  ", font="Arial", font_size=11, color="#FDA4AF").next_to(rh, DOWN, buff=0.08)

        r_rec_lbl = Text("Skewed Recurrence (0 and n-1 split):", font="Segoe UI", font_size=11, color="#94A3B8").move_to(c_right.get_top() + DOWN * 1.05)
        r_rec = MathTex(r"T(n) = T(n-1) + \Theta(n)", font_size=22, color="#FBBF24").next_to(r_rec_lbl, DOWN, buff=0.15)

        r_sum = MathTex(r"= n + (n-1) + (n-2) + \dots + 1", font_size=18, color="#CBD5E1").next_to(r_rec, DOWN, buff=0.20)
        r_res = MathTex(r"T(n) = \frac{n(n-1)}{2} = \Theta(n^2)", font_size=22, color="#FB7185").next_to(r_sum, DOWN, buff=0.20)
        r_fix = Text("Fix: Random Pivot or Median-of-Three!", font="Segoe UI", font_size=11, weight=BOLD, color="#38BDF8").next_to(r_res, DOWN, buff=0.18)

        grp_right = VGroup(c_right, rh, rs, r_rec_lbl, r_rec, r_sum, r_res, r_fix)

        self.play(FadeIn(grp_left, shift=RIGHT*0.2), run_time=2.0)
        self.wait(6.5)
        self.play(Indicate(l_res, scale_factor=1.12, color="#34D399"), run_time=1.8)
        self.wait(3.5)

        self.play(FadeIn(grp_right, shift=LEFT*0.2), run_time=2.0)
        self.wait(6.5)
        self.play(Indicate(r_res, scale_factor=1.12, color="#FB7185"), run_time=1.8)
        self.wait(3.0)

        # 4. Bottom Space & Time Summary Strip (y = -2.85, height = 0.68 -> spans -3.19 to -2.51)
        b_strip = VGroup()
        specs = [
            ("Best Time: O(n log n)", "#10B981", "#064E3B", -4.6),
            ("Avg Time: O(n log n)", "#38BDF8", "#082F49", -1.55),
            ("Worst Time: O(n^2)", "#F43F5E", "#4C0519", 1.55),
            ("Aux Space: O(log n)", "#F59E0B", "#78350F", 4.6),
        ]
        for txt_s, sc, fc, xp in specs:
            pill = RoundedRectangle(corner_radius=0.12, width=2.85, height=0.62, stroke_color=sc, stroke_width=1.8, fill_color=fc, fill_opacity=0.92).move_to([xp, -2.85, 0])
            pt = Text(txt_s, font="Segoe UI", font_size=11, weight=BOLD, color=WHITE).move_to(pill.get_center())
            b_strip.add(VGroup(pill, pt))

        self.play(LaggedStart(*[FadeIn(p, shift=UP*0.15) for p in b_strip], lag_ratio=0.12), run_time=2.0)

        elapsed = 1.2 + 2.0 + 6.5 + 1.8 + 3.5 + 2.0 + 6.5 + 1.8 + 3.0 + 2.0
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
