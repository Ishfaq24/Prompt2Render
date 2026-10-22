from manim import *

class Scene07(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 43.49

        # 1. Header Zone
        title = Text("Why Quick Sort Wins in Practice & Hybrid Introsort", font="Segoe UI", font_size=23, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        subtitle = Text("  عملی اطلاقات، دیگر الگورتھمز سے موازنہ اور مکمل خلاصہ  ", font="Arial", font_size=14, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.2)

        # 2. Three Pillar Cards (y = -0.15, height = 3.90 -> spans -2.10 to +1.80)
        # Card 1: Hardware & Cache Locality
        c1 = RoundedRectangle(corner_radius=0.16, width=3.9, height=3.90, stroke_color="#10B981", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 4.25 + DOWN * 0.15)
        h1 = Text("1. Why So Fast in RAM?", font="Segoe UI", font_size=14, weight=BOLD, color="#34D399").move_to(c1.get_top() + DOWN * 0.35)
        u1 = Text("  ہارڈویئر کیشے اور ان پلیس رفتار  ", font="Arial", font_size=10, color="#6EE7B7").next_to(h1, DOWN, buff=0.08)
        items1 = VGroup(
            Text("• CPU Cache Locality:", font="Segoe UI", font_size=11, weight=BOLD, color=WHITE),
            Text("  Sequential array scan fits L1/L2 cache", font="Segoe UI", font_size=10, color="#CBD5E1"),
            Text("• Tiny Constant Factor:", font="Segoe UI", font_size=11, weight=BOLD, color=WHITE),
            Text("  Tight inner loop with minimal swaps", font="Segoe UI", font_size=10, color="#CBD5E1"),
            Text("• Zero Heap Allocation:", font="Segoe UI", font_size=11, weight=BOLD, color=WHITE),
            Text("  No O(n) buffer like Merge Sort", font="Segoe UI", font_size=10, color="#6EE7B7"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14).move_to(c1.get_center() + DOWN * 0.25)
        grp1 = VGroup(c1, h1, u1, items1)

        # Card 2: Sorting Algorithm Showdown
        c2 = RoundedRectangle(corner_radius=0.16, width=3.9, height=3.90, stroke_color="#38BDF8", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(DOWN * 0.15)
        h2 = Text("2. Algorithm Comparison", font="Segoe UI", font_size=14, weight=BOLD, color="#38BDF8").move_to(c2.get_top() + DOWN * 0.35)
        u2 = Text("  سورٹنگ الگورتھمز کا موازنہ  ", font="Arial", font_size=10, color="#7DD3FC").next_to(h2, DOWN, buff=0.08)
        items2 = VGroup(
            Text("• Quick Sort:", font="Segoe UI", font_size=11, weight=BOLD, color="#34D399"),
            Text("  O(n log n) avg | O(log n) space | Unstable", font="Segoe UI", font_size=9.5, color="#CBD5E1"),
            Text("• Merge Sort:", font="Segoe UI", font_size=11, weight=BOLD, color="#38BDF8"),
            Text("  O(n log n) all | O(n) space | Stable", font="Segoe UI", font_size=9.5, color="#CBD5E1"),
            Text("• Heap Sort:", font="Segoe UI", font_size=11, weight=BOLD, color="#FBBF24"),
            Text("  O(n log n) all | O(1) space | Cache misses", font="Segoe UI", font_size=9.5, color="#CBD5E1"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14).move_to(c2.get_center() + DOWN * 0.25)
        grp2 = VGroup(c2, h2, u2, items2)

        # Card 3: Production Hybrid (Introsort)
        c3 = RoundedRectangle(corner_radius=0.16, width=3.9, height=3.90, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(RIGHT * 4.25 + DOWN * 0.15)
        h3 = Text("3. Standard Library: Introsort", font="Segoe UI", font_size=14, weight=BOLD, color="#FBBF24").move_to(c3.get_top() + DOWN * 0.35)
        u3 = Text("  جدید لائبریریز میں انٹرو سورٹ کا استعمال  ", font="Arial", font_size=10, color="#FDE68A").next_to(h3, DOWN, buff=0.08)
        items3 = VGroup(
            Text("• Used in C++ std::sort & .NET:", font="Segoe UI", font_size=11, weight=BOLD, color=WHITE),
            Text("  1. Starts with fast Quick Sort", font="Segoe UI", font_size=10, color="#6EE7B7"),
            Text("  2. Switches to Heap Sort if", font="Segoe UI", font_size=10, color="#FDE68A"),
            Text("     recursion depth exceeds 2*log(n)", font="Segoe UI", font_size=10, color="#CBD5E1"),
            Text("  3. Uses Insertion Sort for small", font="Segoe UI", font_size=10, color="#7DD3FC"),
            Text("     sub-arrays (size <= 16)", font="Segoe UI", font_size=10, color="#CBD5E1"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12).move_to(c3.get_center() + DOWN * 0.25)
        grp3 = VGroup(c3, h3, u3, items3)

        self.play(FadeIn(grp1, shift=UP*0.2), run_time=1.8)
        self.wait(6.0)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.8)
        self.wait(6.0)
        self.play(FadeIn(grp3, shift=UP*0.2), run_time=1.8)
        self.wait(6.0)

        # 3. Concluding Banner (y = -2.82, height = 0.72 -> spans -3.18 to -2.46)
        end_box = RoundedRectangle(
            corner_radius=0.15, width=12.2, height=0.72,
            stroke_color="#38BDF8", stroke_width=2.2,
            fill_color="#082F49", fill_opacity=0.96
        ).move_to(DOWN * 2.82)
        end_t1 = Text("Quick Sort Complete!  Divide & Conquer  |  In-Place Partitioning  |  O(n log n)", font="Segoe UI", font_size=12, weight=BOLD, color=WHITE).move_to(end_box.get_center() + UP * 0.14)
        end_t2 = Text("Thank You for Learning with Prompt2Render! (دیکھنے کا بہت شکریہ)", font="Arial", font_size=11, color="#38BDF8").move_to(end_box.get_center() + DOWN * 0.15)
        self.play(FadeIn(end_box), FadeIn(end_t1), FadeIn(end_t2), run_time=1.5)

        elapsed = 1.2 + 1.8 + 6.0 + 1.8 + 6.0 + 1.8 + 6.0 + 1.5
        rem = max(0.5, total_time - elapsed)
        self.wait(rem)
