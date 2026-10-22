from manim import *

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 36.20

        # 1. Header Zone
        title = Text("Partitioning Invariant & In-Place Efficiency", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  پارٹیشننگ کا نتیجہ، انویرینٹ اصول اور ان پلیس میموری خصوصیت  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        # 2. Partitioned Array Visualization (y = +1.35)
        x_coords = [-4.25 + k * 1.70 for k in range(6)]
        part_vals = [10, 14, 13, 19, 29, 37]
        cells = VGroup()

        for k, val in enumerate(part_vals):
            xp = x_coords[k]
            if k < 3:
                sc, fc, tag = "#10B981", "#064E3B", "< 19"
            elif k == 3:
                sc, fc, tag = "#F59E0B", "#78350F", "PIVOT"
            else:
                sc, fc, tag = "#8B5CF6", "#2E1065", "> 19"

            box = RoundedRectangle(corner_radius=0.12, width=1.35, height=0.95, stroke_color=sc, stroke_width=2.4, fill_color=fc, fill_opacity=0.92).move_to([xp, 1.35, 0])
            num = Text(str(val), font="Segoe UI", font_size=21, weight=BOLD, color=WHITE).move_to(box.get_center())
            ix = Text(f"idx {k} ({tag})", font="Segoe UI", font_size=9, color="#CBD5E1").next_to(box, UP, buff=0.08)
            cells.add(VGroup(box, num, ix))

        # Three Zone Pills right below the array at y = +0.42
        z_left = RoundedRectangle(corner_radius=0.08, width=4.6, height=0.38, color="#10B981", fill_color="#064E3B", fill_opacity=0.9).move_to([x_coords[1], 0.42, 0])
        zt_left = Text("Left Sub-array: [10, 14, 13]  (All < 19)", font="Segoe UI", font_size=10, weight=BOLD, color="#6EE7B7").move_to(z_left.get_center())

        z_piv = RoundedRectangle(corner_radius=0.08, width=1.45, height=0.38, color="#F59E0B", fill_color="#78350F", fill_opacity=0.95).move_to([x_coords[3], 0.42, 0])
        zt_piv = Text("Fixed @ idx 3", font="Segoe UI", font_size=10, weight=BOLD, color="#FDE68A").move_to(z_piv.get_center())

        z_right = RoundedRectangle(corner_radius=0.08, width=3.0, height=0.38, color="#8B5CF6", fill_color="#2E1065", fill_opacity=0.9).move_to([(x_coords[4]+x_coords[5])/2, 0.42, 0])
        zt_right = Text("Right: [29, 37] (> 19)", font="Segoe UI", font_size=10, weight=BOLD, color="#DDD6FE").move_to(z_right.get_center())

        self.play(LaggedStart(*[FadeIn(c, shift=DOWN*0.15) for c in cells], lag_ratio=0.08), run_time=2.0)
        self.wait(2.5)
        self.play(FadeIn(z_left), FadeIn(zt_left), FadeIn(z_piv), FadeIn(zt_piv), FadeIn(z_right), FadeIn(zt_right), run_time=1.8)
        self.wait(3.5)

        # 3. Two Detailed Cards Below (y = -1.05, height = 2.15 -> spans -2.12 to +0.02)
        # Left Card: Mathematical Partition Invariant
        c_left = RoundedRectangle(corner_radius=0.16, width=5.9, height=2.15, stroke_color="#10B981", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 3.15 + DOWN * 1.05)
        cl_h = Text("1. Partition Invariant Property", font="Segoe UI", font_size=14, weight=BOLD, color="#34D399").move_to(c_left.get_top() + DOWN * 0.32)
        cl_eq1 = MathTex(r"\forall k < p : \; A[k] \le A[p]", font_size=20, color="#6EE7B7").move_to(c_left.get_center() + UP * 0.22)
        cl_eq2 = MathTex(r"\forall k > p : \; A[k] > A[p]", font_size=20, color="#C4B5FD").next_to(cl_eq1, DOWN, buff=0.18)
        cl_u = Text("  بائیں طرف تمام چھوٹے اور دائیں طرف تمام بڑے عناصر  ", font="Arial", font_size=10, color="#94A3B8").move_to(c_left.get_bottom() + UP * 0.25)
        grp_l = VGroup(c_left, cl_h, cl_eq1, cl_eq2, cl_u)

        # Right Card: In-Place Memory Advantage
        c_right = RoundedRectangle(corner_radius=0.16, width=5.9, height=2.15, stroke_color="#38BDF8", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(RIGHT * 3.15 + DOWN * 1.05)
        cr_h = Text("2. In-Place Execution (O(1) Partition Space)", font="Segoe UI", font_size=14, weight=BOLD, color="#38BDF8").move_to(c_right.get_top() + DOWN * 0.32)
        cr_b1 = Text("• All swaps happen directly inside the original array", font="Segoe UI", font_size=11, color=WHITE).move_to(c_right.get_center() + UP * 0.25)
        cr_b2 = Text("• Merge Sort requires O(n) extra array allocation", font="Segoe UI", font_size=11, color="#CBD5E1").next_to(cr_b1, DOWN, buff=0.14)
        cr_b3 = Text("• Quick Sort partition uses O(1) auxiliary variables!", font="Segoe UI", font_size=11, weight=BOLD, color="#FDE68A").next_to(cr_b2, DOWN, buff=0.14)
        cr_u = Text("  اصل ایرے کے اندر ہی تبدیلی، اضافی میموری کا خرچ صفر  ", font="Arial", font_size=10, color="#94A3B8").move_to(c_right.get_bottom() + UP * 0.25)
        grp_r = VGroup(c_right, cr_h, cr_b1, cr_b2, cr_b3, cr_u)

        self.play(FadeIn(grp_l, shift=RIGHT*0.2), run_time=1.8)
        self.wait(5.5)
        self.play(FadeIn(grp_r, shift=LEFT*0.2), run_time=1.8)
        self.wait(5.5)

        # 4. Footer Banner (y = -2.85)
        f_box = RoundedRectangle(corner_radius=0.14, width=12.2, height=0.62, stroke_color="#F59E0B", stroke_width=1.8, fill_color="#0F172A", fill_opacity=0.95).move_to(DOWN * 2.85)
        f_txt = Text(
            "Independent Sub-problems: Left [0..2] and Right [4..5] can now be sorted recursively!",
            font="Segoe UI", font_size=12, weight=BOLD, color="#FDE68A"
        ).move_to(f_box.get_center())
        self.play(FadeIn(f_box), FadeIn(f_txt), Indicate(cells[3][0], color="#FBBF24"), run_time=1.5)

        elapsed = 1.2 + 2.0 + 2.5 + 1.8 + 3.5 + 1.8 + 5.5 + 1.8 + 5.5 + 1.5
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
