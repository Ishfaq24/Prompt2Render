from manim import *

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 45.24

        # 1. Header Zone
        title = Text("Recursive Execution & Complete Recursion Tree", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  ریکرسیو کالز، بیس کیس اور مکمل ریکرژن ٹری کا مشاہدہ  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        def make_tree_node(label_str, sub_str, pos, w, h, stroke_c, fill_c):
            box = RoundedRectangle(corner_radius=0.12, width=w, height=h, stroke_color=stroke_c, stroke_width=2.0, fill_color=fill_c, fill_opacity=0.92).move_to(pos)
            t1 = Text(label_str, font="Segoe UI", font_size=13, weight=BOLD, color=WHITE).move_to(box.get_center() + UP * 0.14)
            t2 = Text(sub_str, font="Segoe UI", font_size=10, color="#CBD5E1").move_to(box.get_center() + DOWN * 0.16)
            return VGroup(box, t1, t2)

        # Level 0 (Root at y = +1.70)
        root = make_tree_node(
            "[29, 10, 14, 37, 13, 19]",
            "Level 0: Pivot = 19 -> Locks at idx 3",
            [0.0, 1.70, 0], 4.8, 0.78, "#38BDF8", "#082F49"
        )
        self.play(FadeIn(root, shift=DOWN*0.15), run_time=1.5)
        self.wait(2.5)

        # Level 1 (y = +0.25)
        l1_left = make_tree_node(
            "Left: [10, 14, 13]",
            "Pivot = 13 -> Locks at idx 1",
            [-3.7, 0.25, 0], 3.5, 0.76, "#10B981", "#064E3B"
        )
        l1_piv = make_tree_node(
            "Pivot: [19]",
            "Fixed @ idx 3",
            [0.0, 0.25, 0], 2.1, 0.76, "#F59E0B", "#78350F"
        )
        l1_right = make_tree_node(
            "Right: [29, 37]",
            "Pivot = 37 -> Locks at idx 5",
            [3.7, 0.25, 0], 3.5, 0.76, "#8B5CF6", "#2E1065"
        )

        arr_0_l = Arrow(root[0].get_bottom() + LEFT*1.2, l1_left[0].get_top(), buff=0.08, color="#10B981", stroke_width=2.2)
        arr_0_p = Arrow(root[0].get_bottom(), l1_piv[0].get_top(), buff=0.08, color="#F59E0B", stroke_width=2.2)
        arr_0_r = Arrow(root[0].get_bottom() + RIGHT*1.2, l1_right[0].get_top(), buff=0.08, color="#8B5CF6", stroke_width=2.2)

        self.play(
            Create(arr_0_l), Create(arr_0_p), Create(arr_0_r),
            FadeIn(l1_left), FadeIn(l1_piv), FadeIn(l1_right),
            run_time=2.2
        )
        self.wait(4.5)

        # Level 2: Left Subtree Children (y = -1.15)
        l2_10 = make_tree_node("[10]", "Base Case (idx 0)", [-5.3, -1.15, 0], 1.75, 0.70, "#34D399", "#064E3B")
        l2_13 = make_tree_node("[13]", "Pivot @ idx 1", [-3.4, -1.15, 0], 1.75, 0.70, "#F59E0B", "#78350F")
        l2_14 = make_tree_node("[14]", "Base Case (idx 2)", [-1.5, -1.15, 0], 1.75, 0.70, "#34D399", "#064E3B")

        a_l_10 = Arrow(l1_left[0].get_bottom() + LEFT*0.8, l2_10[0].get_top(), buff=0.06, color="#34D399", stroke_width=1.8)
        a_l_13 = Arrow(l1_left[0].get_bottom(), l2_13[0].get_top(), buff=0.06, color="#F59E0B", stroke_width=1.8)
        a_l_14 = Arrow(l1_left[0].get_bottom() + RIGHT*0.8, l2_14[0].get_top(), buff=0.06, color="#34D399", stroke_width=1.8)

        self.play(
            Create(a_l_10), Create(a_l_13), Create(a_l_14),
            FadeIn(l2_10), FadeIn(l2_13), FadeIn(l2_14),
            run_time=2.0
        )
        self.wait(5.0)

        # Level 2: Right Subtree Children (y = -1.15)
        l2_29 = make_tree_node("[29]", "Base Case (idx 4)", [2.5, -1.15, 0], 1.9, 0.70, "#34D399", "#064E3B")
        l2_37 = make_tree_node("[37]", "Pivot @ idx 5", [4.7, -1.15, 0], 1.9, 0.70, "#F59E0B", "#78350F")

        a_r_29 = Arrow(l1_right[0].get_bottom() + LEFT*0.6, l2_29[0].get_top(), buff=0.06, color="#34D399", stroke_width=1.8)
        a_r_37 = Arrow(l1_right[0].get_bottom() + RIGHT*0.6, l2_37[0].get_top(), buff=0.06, color="#F59E0B", stroke_width=1.8)

        self.play(
            Create(a_r_29), Create(a_r_37),
            FadeIn(l2_29), FadeIn(l2_37),
            run_time=2.0
        )
        self.wait(4.5)

        # Final Fully Sorted Array Bar at y = -2.65 (height = 0.90 -> spans -3.10 to -2.20)
        final_bg = RoundedRectangle(
            corner_radius=0.15, width=12.2, height=0.92,
            stroke_color="#10B981", stroke_width=2.4,
            fill_color="#064E3B", fill_opacity=0.95
        ).move_to(DOWN * 2.65)
        final_lbl = Text("Final Sorted Array:", font="Segoe UI", font_size=14, weight=BOLD, color="#6EE7B7").move_to(final_bg.get_left() + RIGHT * 1.45)

        final_vals = [10, 13, 14, 19, 29, 37]
        final_chips = VGroup()
        for idx, fv in enumerate(final_vals):
            cx = -2.2 + idx * 1.45
            chip = RoundedRectangle(corner_radius=0.08, width=1.15, height=0.58, stroke_color="#34D399", stroke_width=1.8, fill_color="#0F172A", fill_opacity=0.95).move_to([cx, -2.65, 0])
            ct = Text(str(fv), font="Segoe UI", font_size=16, weight=BOLD, color=WHITE).move_to(chip.get_center())
            final_chips.add(VGroup(chip, ct))

        self.play(
            FadeIn(final_bg), FadeIn(final_lbl),
            LaggedStart(*[FadeIn(ch, scale=0.85) for ch in final_chips], lag_ratio=0.1),
            run_time=2.5
        )

        elapsed = 1.2 + 1.5 + 2.5 + 2.2 + 4.5 + 2.0 + 5.0 + 2.0 + 4.5 + 2.5
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
