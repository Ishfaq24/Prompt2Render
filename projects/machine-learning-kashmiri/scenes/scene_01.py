from manim import *

class Scene01(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 31.65

        # 1. Header Zone (y = 3.3 and 2.8)
        title = Text("Machine Learning: Paradigm Shift", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ کیا چھُ؟ (Rules vs Learning)", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.0)

        # 2. Left Card: Traditional Programming
        card_l = RoundedRectangle(corner_radius=0.2, width=5.4, height=4.2, stroke_color="#334155", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 3.2 + DOWN * 0.55)
        t_l = Text("Traditional Programming", font_size=16, weight=BOLD, color="#94A3B8").move_to(card_l.get_top() + DOWN * 0.35)
        s_l = Text("روایتی پروگرامنگ (قواعد دِنہٕ سٟتؠ)", font="Arial", font_size=11, color="#64748B").next_to(t_l, DOWN, buff=0.08)
        
        box_d = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#475569", fill_color="#1E293B", fill_opacity=0.9).move_to(LEFT * 3.2 + UP * 0.25)
        txt_d = Text("Data (ڈیٹا)", font="Arial", font_size=12, color=WHITE).move_to(box_d.get_center())

        box_r = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#6366F1", fill_color="#312E81", fill_opacity=0.9).move_to(LEFT * 3.2 + DOWN * 0.40)
        txt_r = Text("Rules (قواعد)", font="Arial", font_size=12, color="#A5B4FC").move_to(box_r.get_center())

        arr_l = Arrow(start=LEFT * 3.2 + DOWN * 0.75, end=LEFT * 3.2 + DOWN * 1.35, color="#94A3B8", buff=0.06)

        box_o = RoundedRectangle(corner_radius=0.1, width=3.6, height=0.55, color="#10B981", fill_color="#064E3B", fill_opacity=0.95).move_to(LEFT * 3.2 + DOWN * 1.8)
        txt_o = Text("Output (جواب)", font="Arial", font_size=12, weight=BOLD, color="#34D399").move_to(box_o.get_center())

        grp_left = VGroup(card_l, t_l, s_l, box_d, txt_d, box_r, txt_r, arr_l, box_o, txt_o)

        # 3. Right Card: Machine Learning
        card_r = RoundedRectangle(corner_radius=0.2, width=5.4, height=4.2, stroke_color="#38BDF8", stroke_width=2.5, fill_color="#082F49", fill_opacity=0.88).move_to(RIGHT * 3.2 + DOWN * 0.55)
        t_r = Text("Machine Learning", font_size=18, weight=BOLD, color="#38BDF8").move_to(card_r.get_top() + DOWN * 0.35)
        s_r = Text("مشین لرننگ (ڈیٹا پؠٹھٕ سؠکھُن)", font="Arial", font_size=11, color="#7DD3FC").next_to(t_r, DOWN, buff=0.08)

        box_md = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#0284C7", fill_color="#075985", fill_opacity=0.9).move_to(RIGHT * 3.2 + UP * 0.25)
        txt_md = Text("Historical Data (ڈیٹا)", font="Arial", font_size=12, color=WHITE).move_to(box_md.get_center())

        box_ma = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#10B981", fill_color="#064E3B", fill_opacity=0.9).move_to(RIGHT * 3.2 + DOWN * 0.40)
        txt_ma = Text("Answers (ماضی ہٕنٛدِ جواب)", font="Arial", font_size=12, color="#6EE7B7").move_to(box_ma.get_center())

        arr_r = Arrow(start=RIGHT * 3.2 + DOWN * 0.75, end=RIGHT * 3.2 + DOWN * 1.35, color="#38BDF8", buff=0.06)

        box_mo = RoundedRectangle(corner_radius=0.12, width=3.8, height=0.6, color="#F59E0B", fill_color="#78350F", fill_opacity=0.95).move_to(RIGHT * 3.2 + DOWN * 1.8)
        txt_mo = Text("Learned Model (ماڈل)", font="Arial", font_size=13, weight=BOLD, color="#FCD34D").move_to(box_mo.get_center())

        grp_right = VGroup(card_r, t_r, s_r, box_md, txt_md, box_ma, txt_ma, arr_r, box_mo, txt_mo)

        self.play(FadeIn(grp_left, shift=RIGHT*0.25), run_time=1.4)
        self.wait(1.0)
        self.play(FadeIn(grp_right, shift=LEFT*0.25), run_time=1.4)
        self.wait(2.0)

        # Subtle highlight on Learned Model
        ring = RoundedRectangle(corner_radius=0.15, width=4.0, height=0.75, color="#FBBF24", stroke_width=2.5).move_to(box_mo.get_center())
        self.play(Create(ring), run_time=1.0)
        self.play(FadeOut(ring), run_time=0.8)

        elapsed = 1.0 + 1.4 + 1.0 + 1.4 + 2.0 + 1.0 + 0.8
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
