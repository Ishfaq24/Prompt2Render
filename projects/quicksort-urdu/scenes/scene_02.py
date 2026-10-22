from manim import *

class Scene02(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 41.50

        # 1. Header Zone
        title = Text("Pivot Selection: Role & 4 Core Strategies", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  پیوٹ کا انتخاب اور اس کی چار اہم حکمت عملیاں  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        # 2. Top Array Strip (y = +1.55, height = 1.50 -> spans +0.80 to +2.30)
        strip_bg = RoundedRectangle(
            corner_radius=0.15, width=12.0, height=1.50,
            stroke_color="#334155", stroke_width=1.6,
            fill_color="#0F172A", fill_opacity=0.92
        ).move_to(UP * 1.55)

        vals = [29, 10, 14, 37, 13, 19]
        boxes = VGroup()
        for i, v in enumerate(vals):
            xp = -3.75 + i * 1.5
            is_last = (i == 5)
            b = RoundedRectangle(
                corner_radius=0.10, width=1.2, height=0.68,
                stroke_color="#F59E0B" if is_last else "#475569",
                stroke_width=2.2 if is_last else 1.6,
                fill_color="#78350F" if is_last else "#1E293B",
                fill_opacity=0.92
            ).move_to([xp, 1.44, 0])
            t = Text(str(v), font="Segoe UI", font_size=18, weight=BOLD, color=WHITE).move_to(b.get_center())
            ix = Text(f"idx {i}", font="Segoe UI", font_size=9, color="#94A3B8").next_to(b, DOWN, buff=0.05)
            boxes.add(VGroup(b, t, ix))

        piv_badge = RoundedRectangle(corner_radius=0.08, width=2.2, height=0.32, color="#F59E0B", fill_color="#451A03", fill_opacity=0.95).move_to([3.75, 2.04, 0])
        piv_btxt = Text("Chosen Pivot = 19", font="Segoe UI", font_size=10, weight=BOLD, color="#FDE68A").move_to(piv_badge.get_center())

        self.play(FadeIn(strip_bg), LaggedStart(*[FadeIn(b, scale=0.9) for b in boxes], lag_ratio=0.07), run_time=2.0)
        self.play(FadeIn(piv_badge), FadeIn(piv_btxt), Indicate(boxes[5][0], color="#FBBF24"), run_time=1.5)
        self.wait(3.0)

        # 3. 2x2 Grid of Strategy Cards (y = +0.02 and y = -1.38)
        # Top-Left: Strategy 1 (First Element)
        s1_box = RoundedRectangle(corner_radius=0.14, width=5.8, height=1.22, stroke_color="#0284C7", stroke_width=1.8, fill_color="#082F49", fill_opacity=0.90).move_to(LEFT * 3.1 + UP * 0.02)
        s1_t = Text("1. First Element Pivot  (arr[low] = 29)", font="Segoe UI", font_size=13, weight=BOLD, color="#38BDF8").move_to(s1_box.get_top() + DOWN * 0.28)
        s1_d = Text("Simple to implement, but degrades to O(n^2) on already sorted inputs.", font="Segoe UI", font_size=10, color="#CBD5E1").next_to(s1_t, DOWN, buff=0.10)
        s1_u = Text("  پہلا عنصر پیوٹ: سادہ لیکن پہلے سے سورٹڈ ڈیٹا پر سست  ", font="Arial", font_size=10, color="#7DD3FC").next_to(s1_d, DOWN, buff=0.08)
        card1 = VGroup(s1_box, s1_t, s1_d, s1_u)

        # Top-Right: Strategy 2 (Last Element - Lomuto)
        s2_box = RoundedRectangle(corner_radius=0.14, width=5.8, height=1.22, stroke_color="#F59E0B", stroke_width=2.2, fill_color="#78350F", fill_opacity=0.90).move_to(RIGHT * 3.1 + UP * 0.02)
        s2_t = Text("2. Last Element Pivot  (arr[high] = 19)", font="Segoe UI", font_size=13, weight=BOLD, color="#FBBF24").move_to(s2_box.get_top() + DOWN * 0.28)
        s2_d = Text("Standard in Lomuto Partitioning; clean single-loop pointer scan.", font="Segoe UI", font_size=10, color=WHITE).next_to(s2_t, DOWN, buff=0.10)
        s2_u = Text("  آخری عنصر پیوٹ: لوموٹو پارٹیشننگ کا معیاری طریقہ  ", font="Arial", font_size=10, color="#FDE68A").next_to(s2_d, DOWN, buff=0.08)
        card2 = VGroup(s2_box, s2_t, s2_d, s2_u)

        # Bottom-Left: Strategy 3 (Random Element)
        s3_box = RoundedRectangle(corner_radius=0.14, width=5.8, height=1.22, stroke_color="#8B5CF6", stroke_width=1.8, fill_color="#4C1D95", fill_opacity=0.90).move_to(LEFT * 3.1 + DOWN * 1.38)
        s3_t = Text("3. Random Pivot  (arr[rand(low, high)])", font="Segoe UI", font_size=13, weight=BOLD, color="#A78BFA").move_to(s3_box.get_top() + DOWN * 0.28)
        s3_d = Text("Eliminates predictable worst-case patterns; guarantees expected O(n log n).", font="Segoe UI", font_size=10, color="#CBD5E1").next_to(s3_t, DOWN, buff=0.10)
        s3_u = Text("  رینڈم پیوٹ: ورسٹ کیس سے بچاؤ کے لیے بے ترتیب انتخاب  ", font="Arial", font_size=10, color="#DDD6FE").next_to(s3_d, DOWN, buff=0.08)
        card3 = VGroup(s3_box, s3_t, s3_d, s3_u)

        # Bottom-Right: Strategy 4 (Median-of-Three)
        s4_box = RoundedRectangle(corner_radius=0.14, width=5.8, height=1.22, stroke_color="#10B981", stroke_width=2.2, fill_color="#064E3B", fill_opacity=0.92).move_to(RIGHT * 3.1 + DOWN * 1.38)
        s4_t = Text("4. Median-of-Three  (median(29, 14, 19) = 19)", font="Segoe UI", font_size=13, weight=BOLD, color="#34D399").move_to(s4_box.get_top() + DOWN * 0.28)
        s4_d = Text("Best production choice: picks median of First, Middle & Last elements.", font="Segoe UI", font_size=10, color=WHITE).next_to(s4_t, DOWN, buff=0.10)
        s4_u = Text("  میڈین آف تھری: متوازن تقسیم کے لیے سب سے بہترین عملی طریقہ  ", font="Arial", font_size=10, color="#6EE7B7").next_to(s4_d, DOWN, buff=0.08)
        card4 = VGroup(s4_box, s4_t, s4_d, s4_u)

        # Animate each strategy card synchronized with narration
        self.play(FadeIn(card1, shift=RIGHT*0.2), Indicate(boxes[0][0], color="#38BDF8"), run_time=1.6)
        self.wait(4.5)

        self.play(FadeIn(card2, shift=LEFT*0.2), Indicate(boxes[5][0], color="#FBBF24"), run_time=1.6)
        self.wait(4.8)

        self.play(FadeIn(card3, shift=RIGHT*0.2), Indicate(boxes[2][0], color="#A78BFA"), run_time=1.6)
        self.wait(4.8)

        self.play(
            FadeIn(card4, shift=LEFT*0.2),
            Indicate(boxes[0][0], color="#34D399"),
            Indicate(boxes[2][0], color="#34D399"),
            Indicate(boxes[5][0], color="#34D399"),
            run_time=1.8
        )
        self.wait(4.0)

        # 4. Footer Banner (y = -2.85)
        f_box = RoundedRectangle(
            corner_radius=0.14, width=12.0, height=0.62,
            stroke_color="#10B981", stroke_width=1.8,
            fill_color="#0F172A", fill_opacity=0.95
        ).move_to(DOWN * 2.85)
        f_txt = Text(
            "After Partitioning: Pivot is permanently locked at its final sorted index!",
            font="Segoe UI", font_size=12, weight=BOLD, color="#6EE7B7"
        ).move_to(f_box.get_center())
        self.play(FadeIn(f_box), FadeIn(f_txt), run_time=1.2)

        elapsed = 1.2 + 2.0 + 1.5 + 3.0 + 1.6 + 4.5 + 1.6 + 4.8 + 1.6 + 4.8 + 1.8 + 4.0 + 1.2
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
