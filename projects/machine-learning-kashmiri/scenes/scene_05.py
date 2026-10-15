from manim import *

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 35.21

        title = Text("Real-World Applications of Machine Learning", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("اصل دُنیاہَس مَنٛز استعمال تہٕ اہم خلاصہٕ", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # 4 Application Boxes
        # Top Left
        b1 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#0284C7", stroke_width=1.8, fill_color="#082F49", fill_opacity=0.88).move_to(LEFT * 3.2 + UP * 0.65)
        t1 = Text("Medical Imaging & Healthcare", font_size=13, weight=BOLD, color="#38BDF8").move_to(b1.get_top() + DOWN * 0.3)
        d1 = Text("صحت عامہ: ایکس رے تہٕ ایم آر آئی، بیماری تشخیص", font="Arial", font_size=10, color="#CBD5E1").next_to(t1, DOWN, buff=0.12)
        box1 = VGroup(b1, t1, d1)

        # Top Right
        b2 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#10B981", stroke_width=1.8, fill_color="#064E3B", fill_opacity=0.88).move_to(RIGHT * 3.2 + UP * 0.65)
        t2 = Text("Speech & Kashmiri Translation", font_size=13, weight=BOLD, color="#34D399").move_to(b2.get_top() + DOWN * 0.3)
        d2 = Text("کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ تہٕ آواز ہٕنٛز شناخت", font="Arial", font_size=10, color="#CBD5E1").next_to(t2, DOWN, buff=0.12)
        box2 = VGroup(b2, t2, d2)

        # Bottom Left
        b3 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#F59E0B", stroke_width=1.8, fill_color="#78350F", fill_opacity=0.88).move_to(LEFT * 3.2 + DOWN * 0.95)
        t3 = Text("Autonomous Systems & Robotics", font_size=13, weight=BOLD, color="#FBBF24").move_to(b3.get_top() + DOWN * 0.3)
        d3 = Text("خود مختار گاڑؠن ہٕنٛز ڈرائیونگ تہٕ خودکار روبوٹس", font="Arial", font_size=10, color="#CBD5E1").next_to(t3, DOWN, buff=0.12)
        box3 = VGroup(b3, t3, d3)

        # Bottom Right
        b4 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#8B5CF6", stroke_width=1.8, fill_color="#4C1D95", fill_opacity=0.88).move_to(RIGHT * 3.2 + DOWN * 0.95)
        t4 = Text("Recommendation & Prediction", font_size=13, weight=BOLD, color="#A78BFA").move_to(b4.get_top() + DOWN * 0.3)
        d4 = Text("یوٹیوب، ای کامرس تجاویز تہٕ مالی پیشن گوئی", font="Arial", font_size=10, color="#CBD5E1").next_to(t4, DOWN, buff=0.12)
        box4 = VGroup(b4, t4, d4)

        self.play(FadeIn(box1, shift=RIGHT*0.2), FadeIn(box2, shift=LEFT*0.2), run_time=1.4)
        self.wait(1.0)
        self.play(FadeIn(box3, shift=RIGHT*0.2), FadeIn(box4, shift=LEFT*0.2), run_time=1.4)
        self.wait(2.0)

        # Concluding Banner sitting cleanly BELOW the boxes at y = -2.35
        thx_box = RoundedRectangle(corner_radius=0.15, width=11.2, height=0.85, stroke_color="#38BDF8", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.98).move_to(DOWN * 2.35)
        thx_txt1 = Text("Machine Learning: Shaping the Future of AI", font_size=13, weight=BOLD, color=WHITE).move_to(thx_box.get_center() + UP * 0.16)
        thx_txt2 = Text("شُکریہ! Thank You for Learning with Prompt2Render", font="Arial", font_size=11, color="#38BDF8").move_to(thx_box.get_center() + DOWN * 0.16)
        thx_grp = VGroup(thx_box, thx_txt1, thx_txt2)

        self.play(FadeIn(thx_grp, shift=UP*0.1), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.4 + 1.0 + 1.4 + 2.0 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
