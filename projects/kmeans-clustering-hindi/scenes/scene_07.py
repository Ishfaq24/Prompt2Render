from manim import *

class Scene07(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Summary: Strengths, Limitations & Applications", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("फायदे, सीमाएं, वास्तविक अनुप्रयोग और निष्कर्ष", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Three Pillar Cards
        coords = [
            (LEFT * 4.2 + DOWN * 0.3, "1. Core Strengths", [
                "• High Computational Speed",
                "• Time Complexity: O(t * K * n * d)",
                "• Easy to Implement & Interpret",
                "• Scales to Millions of Samples"
            ], "#10B981"),
            (DOWN * 0.3, "2. Key Limitations", [
                "• Assumes Spherical Clusters",
                "• Sensitive to Scale (Scale First!)",
                "• Highly Sensitive to Outliers",
                "• Requires Manual Choice of K"
            ], "#F43F5E"),
            (RIGHT * 4.2 + DOWN * 0.3, "3. Real-World Uses", [
                "• Customer Segmentation",
                "• Image Color Quantization",
                "• Document & Topic Grouping",
                "• Anomaly / Fraud Detection"
            ], "#38BDF8"),
        ]

        cards = []
        for pos, chdr, citems, col in coords:
            box = RoundedRectangle(
                corner_radius=0.15, width=3.8, height=4.2,
                stroke_color=col, stroke_width=1.5,
                fill_color="#0F172A", fill_opacity=0.9
            ).move_to(pos)
            h = Text(chdr, font_size=13, color=col, weight=BOLD).move_to(box.get_top() + DOWN * 0.4)
            lines = VGroup(*[Text(it, font_size=10, color="#CBD5E1") for it in citems]).arrange(DOWN, aligned_edge=LEFT, buff=0.25).move_to(box.get_center() + DOWN * 0.2)
            cards.append(VGroup(box, h, lines))

        for i, card in enumerate(cards):
            self.play(FadeIn(card, shift=UP*0.2), run_time=1.5)
            self.wait(3.0 if i < 2 else 5.0)

        # 3. Final Takeaway Banner
        banner = RoundedRectangle(
            corner_radius=0.15, width=10.5, height=0.6,
            color="#F59E0B", fill_color="#451A03", fill_opacity=0.9
        ).move_to(DOWN * 2.7)
        banner_txt = Text("K-Means: The Essential Foundation of Unsupervised Learning", font_size=13, color="#FDE68A", weight=BOLD).move_to(banner.get_center())
        self.play(FadeIn(VGroup(banner, banner_txt), shift=UP*0.1), run_time=1.2)
        self.wait(18.0)
