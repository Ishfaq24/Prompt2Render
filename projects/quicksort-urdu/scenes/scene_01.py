from manim import *

class Scene01(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 40.93

        # 1. Header Zone (y = +3.45 and +2.92)
        title = Text("Quick Sort: Divide & Conquer Algorithm", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  کوئیک سورٹ کا تعارف اور تقسیم و فتح کا اصول (Tony Hoare, 1959)  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        # 2. Top Array Container (y = +1.45, height = 1.65 -> spans +0.62 to +2.27)
        arr_bg = RoundedRectangle(
            corner_radius=0.16, width=12.4, height=1.65,
            stroke_color="#1E293B", stroke_width=1.8,
            fill_color="#0F172A", fill_opacity=0.92
        ).move_to(UP * 1.45)

        state_lbl = Text("Unsorted Input Array (غیر ترتیب شدہ فہرست)", font="Arial", font_size=12, color="#94A3B8")
        state_lbl.move_to(arr_bg.get_top() + DOWN * 0.26)

        vals_unsorted = [29, 10, 14, 37, 13, 25, 19]
        vals_sorted = [10, 13, 14, 19, 25, 29, 37]
        cells = VGroup()
        for idx, val in enumerate(vals_unsorted):
            x_pos = -4.2 + idx * 1.4
            is_piv = (idx == 6)
            col = "#F59E0B" if is_piv else "#38BDF8"
            fill_c = "#78350F" if is_piv else "#082F49"
            box = RoundedRectangle(
                corner_radius=0.10, width=1.15, height=0.78,
                stroke_color=col, stroke_width=2.0,
                fill_color=fill_c, fill_opacity=0.90
            ).move_to([x_pos, 1.38, 0])
            num = Text(str(val), font="Segoe UI", font_size=18, weight=BOLD, color=WHITE).move_to(box.get_center())
            idx_txt = Text(f"idx {idx}", font="Segoe UI", font_size=9, color="#64748B").next_to(box, DOWN, buff=0.06)
            cells.add(VGroup(box, num, idx_txt))

        self.play(FadeIn(arr_bg), FadeIn(state_lbl), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(c, shift=UP*0.15) for c in cells], lag_ratio=0.08), run_time=2.2)
        self.wait(2.5)

        # Highlight Pivot 19 at idx 6
        piv_tag = Text("Pivot = 19", font="Segoe UI", font_size=11, weight=BOLD, color="#FBBF24").next_to(cells[6][0], UP, buff=0.08)
        self.play(FadeIn(piv_tag), Indicate(cells[6][0], scale_factor=1.12, color="#FBBF24"), run_time=1.8)
        self.wait(2.5)

        # 3. Three Divide-and-Conquer Pillar Cards (y = -0.80, height = 2.45 -> spans -2.02 to +0.42)
        # Card 1: Divide
        c1 = RoundedRectangle(corner_radius=0.16, width=3.9, height=2.45, stroke_color="#38BDF8", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.90).move_to(LEFT * 4.25 + DOWN * 0.80)
        t1 = Text("1. Divide (تقسیم)", font="Arial", font_size=15, weight=BOLD, color="#38BDF8").move_to(c1.get_top() + DOWN * 0.35)
        b1_1 = Text("• Select a Pivot element (p)", font="Segoe UI", font_size=11, color=WHITE).move_to(c1.get_center() + UP * 0.25)
        b1_2 = Text("• Partition array around Pivot:", font="Segoe UI", font_size=11, color="#CBD5E1").next_to(b1_1, DOWN, buff=0.14)
        b1_3 = Text("  Left <= Pivot  |  Right > Pivot", font="Segoe UI", font_size=11, weight=BOLD, color="#7DD3FC").next_to(b1_2, DOWN, buff=0.14)
        b1_4 = Text("  پیوٹ کے گرد دو حصوں میں تقسیم  ", font="Arial", font_size=10, color="#94A3B8").move_to(c1.get_bottom() + UP * 0.28)
        grp1 = VGroup(c1, t1, b1_1, b1_2, b1_3, b1_4)

        # Card 2: Conquer
        c2 = RoundedRectangle(corner_radius=0.16, width=3.9, height=2.45, stroke_color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.90).move_to(DOWN * 0.80)
        t2 = Text("2. Conquer (فتح)", font="Arial", font_size=15, weight=BOLD, color="#34D399").move_to(c2.get_top() + DOWN * 0.35)
        b2_1 = Text("• Recursively sort Left sub-array", font="Segoe UI", font_size=11, color=WHITE).move_to(c2.get_center() + UP * 0.25)
        b2_2 = Text("• Recursively sort Right sub-array", font="Segoe UI", font_size=11, color="#CBD5E1").next_to(b2_1, DOWN, buff=0.14)
        b2_3 = Text("  quickSort(low, p-1) & (p+1, high)", font="Segoe UI", font_size=10, weight=BOLD, color="#6EE7B7").next_to(b2_2, DOWN, buff=0.14)
        b2_4 = Text("  دونوں حصوں کی ریکرسیو ترتیب  ", font="Arial", font_size=10, color="#94A3B8").move_to(c2.get_bottom() + UP * 0.28)
        grp2 = VGroup(c2, t2, b2_1, b2_2, b2_3, b2_4)

        # Card 3: Combine
        c3 = RoundedRectangle(corner_radius=0.16, width=3.9, height=2.45, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.90).move_to(RIGHT * 4.25 + DOWN * 0.80)
        t3 = Text("3. Combine (یکجا)", font="Arial", font_size=15, weight=BOLD, color="#FBBF24").move_to(c3.get_top() + DOWN * 0.35)
        b3_1 = Text("• In-Place Sorting Architecture", font="Segoe UI", font_size=11, color=WHITE).move_to(c3.get_center() + UP * 0.25)
        b3_2 = Text("• Zero extra merging step needed!", font="Segoe UI", font_size=11, color="#CBD5E1").next_to(b3_1, DOWN, buff=0.14)
        b3_3 = Text("  O(1) Extra Merge Overhead", font="Segoe UI", font_size=11, weight=BOLD, color="#FDE68A").next_to(b3_2, DOWN, buff=0.14)
        b3_4 = Text("  بغیر اضافی میموری کے مکمل ترتیب  ", font="Arial", font_size=10, color="#94A3B8").move_to(c3.get_bottom() + UP * 0.28)
        grp3 = VGroup(c3, t3, b3_1, b3_2, b3_3, b3_4)

        self.play(FadeIn(grp1, shift=UP*0.2), run_time=1.6)
        self.wait(4.5)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.6)
        self.wait(4.5)
        self.play(FadeIn(grp3, shift=UP*0.2), run_time=1.6)
        self.wait(3.5)

        # 4. Transform top array into Sorted Order to demonstrate final result
        sorted_lbl = Text("Sorted Output Array (مکمل ترتیب شدہ فہرست)", font="Arial", font_size=12, color="#34D399", weight=BOLD)
        sorted_lbl.move_to(state_lbl.get_center())
        sorted_cells = VGroup()
        for idx, val in enumerate(vals_sorted):
            x_pos = -4.2 + idx * 1.4
            is_piv = (val == 19)
            col = "#F59E0B" if is_piv else "#10B981"
            fill_c = "#78350F" if is_piv else "#064E3B"
            box = RoundedRectangle(
                corner_radius=0.10, width=1.15, height=0.78,
                stroke_color=col, stroke_width=2.2,
                fill_color=fill_c, fill_opacity=0.95
            ).move_to([x_pos, 1.38, 0])
            num = Text(str(val), font="Segoe UI", font_size=18, weight=BOLD, color=WHITE).move_to(box.get_center())
            idx_txt = Text(f"idx {idx}", font="Segoe UI", font_size=9, color="#6EE7B7").next_to(box, DOWN, buff=0.06)
            sorted_cells.add(VGroup(box, num, idx_txt))

        self.play(
            FadeOut(piv_tag),
            ReplacementTransform(state_lbl, sorted_lbl),
            ReplacementTransform(cells, sorted_cells),
            run_time=2.2
        )
        self.wait(2.0)

        # 5. Footer Banner (y = -2.85, height = 0.62 -> spans -3.16 to -2.54)
        footer_box = RoundedRectangle(
            corner_radius=0.14, width=12.4, height=0.62,
            stroke_color="#38BDF8", stroke_width=1.6,
            fill_color="#0F172A", fill_opacity=0.95
        ).move_to(DOWN * 2.85)
        footer_txt = Text(
            "Average Time Complexity: O(n log n)   |   In-Place Auxiliary Space: O(log n) Call Stack",
            font="Segoe UI", font_size=12, weight=BOLD, color="#FDE68A"
        ).move_to(footer_box.get_center())
        self.play(FadeIn(footer_box), FadeIn(footer_txt), run_time=1.2)

        elapsed = 1.2 + 1.0 + 2.2 + 2.5 + 1.8 + 2.5 + 1.6 + 4.5 + 1.6 + 4.5 + 1.6 + 3.5 + 2.2 + 2.0 + 1.2
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
