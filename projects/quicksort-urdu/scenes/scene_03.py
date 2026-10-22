from manim import *

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 59.91

        # 1. Header Zone
        title = Text("Lomuto Partitioning: Step-by-Step Execution", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  لوموٹو پارٹیشننگ الگورتھم: پوائنٹرز آئی اور جے کے ساتھ مرحلہ وار عمل  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.0)

        # 2. Rule & Step Status Bar (y = +1.85, height = 0.72 -> spans +1.49 to +2.21)
        rule_box = RoundedRectangle(
            corner_radius=0.14, width=12.2, height=0.72,
            stroke_color="#38BDF8", stroke_width=1.6,
            fill_color="#0F172A", fill_opacity=0.95
        ).move_to(UP * 1.85)
        rule_txt = Text(
            "Rule: Compare arr[j] with Pivot (19).  If arr[j] <= 19  -->  Increment i, then Swap(arr[i], arr[j])",
            font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC"
        ).move_to(rule_box.get_center())
        self.play(FadeIn(rule_box), FadeIn(rule_txt), run_time=1.0)

        # 3. Array Cells at y = +0.35 (height = 1.15 -> spans -0.22 to +0.92)
        x_coords = [-4.25 + k * 1.70 for k in range(6)]
        init_vals = [29, 10, 14, 37, 13, 19]

        idx_labels = VGroup()
        cell_boxes = []
        cell_nums = []

        for k, val in enumerate(init_vals):
            xp = x_coords[k]
            ilbl = Text(f"idx {k}", font="Segoe UI", font_size=11, color="#94A3B8").move_to([xp, 1.12, 0])
            idx_labels.add(ilbl)

            is_piv = (k == 5)
            box = RoundedRectangle(
                corner_radius=0.12, width=1.35, height=1.05,
                stroke_color="#F59E0B" if is_piv else "#475569",
                stroke_width=2.4 if is_piv else 1.8,
                fill_color="#78350F" if is_piv else "#1E293B",
                fill_opacity=0.92
            ).move_to([xp, 0.35, 0])
            num = Text(str(val), font="Segoe UI", font_size=22, weight=BOLD, color=WHITE).move_to(box.get_center())
            cell_boxes.append(box)
            cell_nums.append(num)

        piv_crown = Text("PIVOT", font="Segoe UI", font_size=10, weight=BOLD, color="#FBBF24").move_to([x_coords[5], -0.38, 0])

        self.play(
            FadeIn(idx_labels),
            *[FadeIn(b) for b in cell_boxes],
            *[FadeIn(n) for n in cell_nums],
            FadeIn(piv_crown),
            run_time=1.5
        )
        self.wait(2.2)

        # 4. Pointers i and j in Zone y = -0.95 to -1.75
        i_badge = RoundedRectangle(corner_radius=0.10, width=1.15, height=0.46, color="#10B981", fill_color="#064E3B", fill_opacity=0.95)
        i_txt = Text("i = -1", font="Segoe UI", font_size=12, weight=BOLD, color="#34D399")
        i_grp = VGroup(i_badge, i_txt).move_to([-5.65, -0.95, 0])

        j_badge = RoundedRectangle(corner_radius=0.10, width=1.15, height=0.46, color="#38BDF8", fill_color="#082F49", fill_opacity=0.95)
        j_txt = Text("j = 0", font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC")
        j_grp = VGroup(j_badge, j_txt).move_to([x_coords[0], -1.62, 0])

        # 5. Step Log Banner at y = -2.85
        log_box = RoundedRectangle(
            corner_radius=0.14, width=12.2, height=0.68,
            stroke_color="#334155", stroke_width=1.8,
            fill_color="#0F172A", fill_opacity=0.95
        ).move_to(DOWN * 2.85)
        log_txt = Text("Initial State: i = -1 (boundary of <= 19),  j = 0 (scanner),  Pivot = 19", font="Segoe UI", font_size=12, color="#E2E8F0").move_to(log_box.get_center())

        self.play(FadeIn(i_grp), FadeIn(j_grp), FadeIn(log_box), FadeIn(log_txt), run_time=1.5)
        self.wait(2.5)

        def update_log(new_str, col="#E2E8F0"):
            nt = Text(new_str, font="Segoe UI", font_size=12, weight=BOLD, color=col).move_to(log_box.get_center())
            return ReplacementTransform(log_txt, nt), nt

        # --- STEP j=0: arr[0] = 29 > 19 (No swap) ---
        anim_log, log_txt = update_log("j = 0:  arr[0] = 29 > Pivot (19)  -->  No Swap!  (29 stays in > Pivot region)", "#F87171")
        self.play(
            anim_log,
            cell_boxes[0].animate.set_stroke("#8B5CF6", width=2.2).set_fill("#2E1065", opacity=0.9),
            run_time=1.6
        )
        self.wait(2.2)

        # --- STEP j=1: arr[1] = 10 <= 19 -> i=0, swap(arr[0]=29, arr[1]=10) ---
        new_j1 = Text("j = 1", font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC").move_to([x_coords[1], -1.62, 0])
        new_i0 = Text("i = 0", font="Segoe UI", font_size=12, weight=BOLD, color="#34D399").move_to([x_coords[0], -0.95, 0])
        anim_log, log_txt = update_log("j = 1:  arr[1] = 10 <= 19  -->  i becomes 0,  Swap arr[0] (29) <-> arr[1] (10)", "#34D399")
        self.play(
            j_badge.animate.move_to([x_coords[1], -1.62, 0]),
            ReplacementTransform(j_txt, new_j1),
            i_badge.animate.move_to([x_coords[0], -0.95, 0]),
            ReplacementTransform(i_txt, new_i0),
            anim_log,
            run_time=1.5
        )
        j_txt, i_txt = new_j1, new_i0

        # Swap boxes[0] and boxes[1]
        self.play(
            cell_boxes[0].animate.move_to([x_coords[1], 0.35, 0]),
            cell_nums[0].animate.move_to([x_coords[1], 0.35, 0]),
            cell_boxes[1].animate.move_to([x_coords[0], 0.35, 0]).set_stroke("#10B981", width=2.2).set_fill("#064E3B", opacity=0.92),
            cell_nums[1].animate.move_to([x_coords[0], 0.35, 0]),
            run_time=1.8
        )
        cell_boxes[0], cell_boxes[1] = cell_boxes[1], cell_boxes[0]
        cell_nums[0], cell_nums[1] = cell_nums[1], cell_nums[0]
        self.wait(2.2)

        # --- STEP j=2: arr[2] = 14 <= 19 -> i=1, swap(arr[1]=29, arr[2]=14) ---
        new_j2 = Text("j = 2", font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC").move_to([x_coords[2], -1.62, 0])
        new_i1 = Text("i = 1", font="Segoe UI", font_size=12, weight=BOLD, color="#34D399").move_to([x_coords[1], -0.95, 0])
        anim_log, log_txt = update_log("j = 2:  arr[2] = 14 <= 19  -->  i becomes 1,  Swap arr[1] (29) <-> arr[2] (14)", "#34D399")
        self.play(
            j_badge.animate.move_to([x_coords[2], -1.62, 0]),
            ReplacementTransform(j_txt, new_j2),
            i_badge.animate.move_to([x_coords[1], -0.95, 0]),
            ReplacementTransform(i_txt, new_i1),
            anim_log,
            run_time=1.5
        )
        j_txt, i_txt = new_j2, new_i1

        self.play(
            cell_boxes[1].animate.move_to([x_coords[2], 0.35, 0]),
            cell_nums[1].animate.move_to([x_coords[2], 0.35, 0]),
            cell_boxes[2].animate.move_to([x_coords[1], 0.35, 0]).set_stroke("#10B981", width=2.2).set_fill("#064E3B", opacity=0.92),
            cell_nums[2].animate.move_to([x_coords[1], 0.35, 0]),
            run_time=1.8
        )
        cell_boxes[1], cell_boxes[2] = cell_boxes[2], cell_boxes[1]
        cell_nums[1], cell_nums[2] = cell_nums[2], cell_nums[1]
        self.wait(2.2)

        # --- STEP j=3: arr[3] = 37 > 19 (No swap) ---
        new_j3 = Text("j = 3", font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC").move_to([x_coords[3], -1.62, 0])
        anim_log, log_txt = update_log("j = 3:  arr[3] = 37 > Pivot (19)  -->  No Swap!  (i stays at 1)", "#F87171")
        self.play(
            j_badge.animate.move_to([x_coords[3], -1.62, 0]),
            ReplacementTransform(j_txt, new_j3),
            cell_boxes[3].animate.set_stroke("#8B5CF6", width=2.2).set_fill("#2E1065", opacity=0.9),
            anim_log,
            run_time=1.6
        )
        j_txt = new_j3
        self.wait(1.8)

        # --- STEP j=4: arr[4] = 13 <= 19 -> i=2, swap(arr[2]=29, arr[4]=13) ---
        new_j4 = Text("j = 4", font="Segoe UI", font_size=12, weight=BOLD, color="#7DD3FC").move_to([x_coords[4], -1.62, 0])
        new_i2 = Text("i = 2", font="Segoe UI", font_size=12, weight=BOLD, color="#34D399").move_to([x_coords[2], -0.95, 0])
        anim_log, log_txt = update_log("j = 4:  arr[4] = 13 <= 19  -->  i becomes 2,  Swap arr[2] (29) <-> arr[4] (13)", "#34D399")
        self.play(
            j_badge.animate.move_to([x_coords[4], -1.62, 0]),
            ReplacementTransform(j_txt, new_j4),
            i_badge.animate.move_to([x_coords[2], -0.95, 0]),
            ReplacementTransform(i_txt, new_i2),
            anim_log,
            run_time=1.5
        )
        j_txt, i_txt = new_j4, new_i2

        self.play(
            cell_boxes[2].animate.move_to([x_coords[4], 0.35, 0]),
            cell_nums[2].animate.move_to([x_coords[4], 0.35, 0]),
            cell_boxes[4].animate.move_to([x_coords[2], 0.35, 0]).set_stroke("#10B981", width=2.2).set_fill("#064E3B", opacity=0.92),
            cell_nums[4].animate.move_to([x_coords[2], 0.35, 0]),
            run_time=1.8
        )
        cell_boxes[2], cell_boxes[4] = cell_boxes[4], cell_boxes[2]
        cell_nums[2], cell_nums[4] = cell_nums[4], cell_nums[2]
        self.wait(2.0)

        # --- FINAL PIVOT SWAP: Swap arr[i+1] (idx 3, val 37) with Pivot arr[5] (val 19) ---
        anim_log, log_txt = update_log("Final Step: Swap arr[i+1] (arr[3]=37) with Pivot (arr[5]=19)  -->  Pivot Locked at Index 3!", "#FBBF24")
        self.play(
            anim_log,
            FadeOut(j_badge), FadeOut(j_txt),
            i_badge.animate.move_to([x_coords[3], -0.95, 0]).set_color("#F59E0B"),
            run_time=1.2
        )
        piv_locked_lbl = Text("p = 3 (LOCKED)", font="Segoe UI", font_size=10, weight=BOLD, color="#FDE68A").move_to([x_coords[3], -0.95, 0])
        self.play(
            ReplacementTransform(i_txt, piv_locked_lbl),
            cell_boxes[3].animate.move_to([x_coords[5], 0.35, 0]),
            cell_nums[3].animate.move_to([x_coords[5], 0.35, 0]),
            cell_boxes[5].animate.move_to([x_coords[3], 0.35, 0]).set_stroke("#FBBF24", width=3.0),
            cell_nums[5].animate.move_to([x_coords[3], 0.35, 0]),
            piv_crown.animate.move_to([x_coords[3], -0.38, 0]),
            run_time=2.2
        )
        cell_boxes[3], cell_boxes[5] = cell_boxes[5], cell_boxes[3]
        cell_nums[3], cell_nums[5] = cell_nums[5], cell_nums[3]

        elapsed = 1.0 + 1.0 + 1.5 + 2.2 + 1.5 + 2.5 + 1.6 + 2.2 + 1.5 + 1.8 + 2.2 + 1.5 + 1.8 + 2.2 + 1.6 + 1.8 + 1.5 + 1.8 + 2.0 + 1.2 + 2.2
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
