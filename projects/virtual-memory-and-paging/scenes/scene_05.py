from manim import *
import numpy as np

class Scene05(Scene):
    def construct(self):
        # ----------------------------------------------------
        # Styling & Palette
        # ----------------------------------------------------
        self.camera.background_color = "#0A0F1D"
        
        FONT_MAIN = "Segoe UI"
        COLOR_CYAN = "#00F0FF"
        COLOR_AMBER = "#F59E0B"
        COLOR_GREEN = "#10B981"
        COLOR_PURPLE = "#8B5CF6"
        COLOR_DARK = "#111C33"
        COLOR_BORDER = "#1E2E4A"
        COLOR_TEXT_MUTED = "#94A3B8"
        
        # ----------------------------------------------------
        # Universal Header
        # ----------------------------------------------------
        badge_box = RoundedRectangle(
            corner_radius=0.1, width=3.4, height=0.42,
            color=COLOR_PURPLE, fill_color=COLOR_PURPLE, fill_opacity=0.15, stroke_width=1.5
        )
        badge_txt = Text("PART 05  •  THE BIG PICTURE", font=FONT_MAIN, font_size=11, color=COLOR_PURPLE, weight="BOLD").move_to(badge_box)
        badge = VGroup(badge_box, badge_txt).to_corner(UL, buff=0.45)
        
        title_txt = Text("The Three Superpowers of Virtual Memory", font=FONT_MAIN, font_size=22, color=WHITE, weight="BOLD")
        title_txt.next_to(badge, RIGHT, buff=0.35)
        
        div_line = Line(LEFT * 6.8, RIGHT * 6.8, stroke_color="#1E293B", stroke_width=1.5)
        div_line.to_edge(UP, buff=0.95)
        
        header = VGroup(badge, title_txt, div_line)
        self.play(FadeIn(header, shift=DOWN * 0.15), run_time=0.8)
        self.wait(3.7) # Reach 4.5s (Sentence 0 ends at 4.54s)

        # ----------------------------------------------------
        # Sentence 1: Superpower 1: Complete Process Isolation
        # (4.5s - 15.4s)
        # ----------------------------------------------------
        # Process 1 Card (Left, y = 1.1)
        p1_card = RoundedRectangle(corner_radius=0.12, width=3.6, height=1.9, color=COLOR_CYAN, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=1.8).move_to(LEFT * 4.4 + UP * 1.1)
        p1_title = Text("Process A: Browser", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(p1_card.get_top() + DOWN * 0.25)
        p1_addr1 = Text("VPN: 0x0040 (Private)", font=FONT_MAIN, font_size=9, color=WHITE).move_to(p1_card.get_top() + DOWN * 0.65)
        p1_addr2 = Text("VPN: 0x7FFF (Libc)", font=FONT_MAIN, font_size=9, color=COLOR_PURPLE).move_to(p1_card.get_top() + DOWN * 1.05)
        p1_full = VGroup(p1_card, p1_title, p1_addr1, p1_addr2)

        # Process 2 Card (Right, y = 1.1)
        p2_card = RoundedRectangle(corner_radius=0.12, width=3.6, height=1.9, color=COLOR_GREEN, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=1.8).move_to(RIGHT * 4.4 + UP * 1.1)
        p2_title = Text("Process B: Database", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(p2_card.get_top() + DOWN * 0.25)
        p2_addr1 = Text("VPN: 0x0040 (Private)", font=FONT_MAIN, font_size=9, color=WHITE).move_to(p2_card.get_top() + DOWN * 0.65)
        p2_addr2 = Text("VPN: 0x7FFF (Libc)", font=FONT_MAIN, font_size=9, color=COLOR_PURPLE).move_to(p2_card.get_top() + DOWN * 1.05)
        p2_full = VGroup(p2_card, p2_title, p2_addr1, p2_addr2)

        # Physical RAM (Center, y = 1.1)
        ram_card = RoundedRectangle(corner_radius=0.12, width=3.8, height=2.4, color=COLOR_AMBER, fill_color="#080F1E", fill_opacity=0.95, stroke_width=1.8).move_to(UP * 1.0)
        ram_title = Text("PHYSICAL RAM", font=FONT_MAIN, font_size=11, color=COLOR_AMBER, weight="BOLD").move_to(ram_card.get_top() + DOWN * 0.25)
        
        f2_box = RoundedRectangle(corner_radius=0.06, width=3.2, height=0.42, color=COLOR_CYAN, fill_color="#072B3E", fill_opacity=0.9, stroke_width=1.2).move_to(ram_card.get_top() + DOWN * 0.7)
        f2_txt = Text("Frame 2: Browser Data", font=FONT_MAIN, font_size=9, color=COLOR_CYAN, weight="BOLD").move_to(f2_box)
        
        f4_box = RoundedRectangle(corner_radius=0.06, width=3.2, height=0.42, color=COLOR_PURPLE, fill_color="#2B0E44", fill_opacity=0.9, stroke_width=1.2).move_to(ram_card.get_top() + DOWN * 1.25)
        f4_txt = Text("Frame 4: Shared Libc DLL", font=FONT_MAIN, font_size=9, color=COLOR_PURPLE, weight="BOLD").move_to(f4_box)
        
        f6_box = RoundedRectangle(corner_radius=0.06, width=3.2, height=0.42, color=COLOR_GREEN, fill_color="#032B1A", fill_opacity=0.9, stroke_width=1.2).move_to(ram_card.get_top() + DOWN * 1.8)
        f6_txt = Text("Frame 6: Database Data", font=FONT_MAIN, font_size=9, color=COLOR_GREEN, weight="BOLD").move_to(f6_box)
        
        ram_full = VGroup(ram_card, ram_title, f2_box, f2_txt, f4_box, f4_txt, f6_box, f6_txt)

        self.play(FadeIn(p1_full, shift=RIGHT * 0.3), FadeIn(p2_full, shift=LEFT * 0.3), FadeIn(ram_full), run_time=2.2)

        # Draw isolation mapping arrows
        arrow_iso_a = Arrow(start=p1_card.get_right() + UP * 0.3, end=f2_box.get_left(), color=COLOR_CYAN, stroke_width=2.5, tip_length=0.15)
        arrow_iso_b = Arrow(start=p2_card.get_left() + UP * 0.3, end=f6_box.get_right(), color=COLOR_GREEN, stroke_width=2.5, tip_length=0.15)

        iso_badge = RoundedRectangle(corner_radius=0.1, width=8.8, height=0.4, color=COLOR_CYAN, fill_color="#021E2B", fill_opacity=0.95, stroke_width=1.5).move_to(DOWN * 0.55)
        iso_badge_txt = Text("1. PROCESS ISOLATION: Identical Virtual 0x0040 -> Distinct Physical Frames!", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(iso_badge)
        iso_group = VGroup(iso_badge, iso_badge_txt)

        self.play(Create(arrow_iso_a), Create(arrow_iso_b), FadeIn(iso_group, shift=UP * 0.1), run_time=2.2)
        self.wait(6.5) # Reach 15.4s (Sentence 1 ends at 15.42s)

        # ----------------------------------------------------
        # Sentence 2: Superpower 2: Efficient Memory Sharing
        # (15.4s - 24.5s)
        # ----------------------------------------------------
        arrow_share_a = Arrow(start=p1_card.get_right() + DOWN * 0.2, end=f4_box.get_left(), color=COLOR_PURPLE, stroke_width=2.5, tip_length=0.15)
        arrow_share_b = Arrow(start=p2_card.get_left() + DOWN * 0.2, end=f4_box.get_right(), color=COLOR_PURPLE, stroke_width=2.5, tip_length=0.15)

        share_badge = RoundedRectangle(corner_radius=0.1, width=8.8, height=0.4, color=COLOR_PURPLE, fill_color="#2A0B42", fill_opacity=0.95, stroke_width=1.5).move_to(DOWN * 0.55)
        share_badge_txt = Text("2. SHARED LIBRARIES: 1 Physical Copy in RAM Serves Hundreds of Processes!", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(share_badge)
        share_group = VGroup(share_badge, share_badge_txt)

        self.play(
            FadeOut(iso_group),
            Create(arrow_share_a), Create(arrow_share_b),
            FadeIn(share_group, shift=UP * 0.1),
            run_time=2.2
        )
        self.wait(6.9) # Reach 24.5s (Sentence 2 ends at 24.45s)

        # ----------------------------------------------------
        # Sentence 3 & 4: Superpower 3 & The Big Picture Summary
        # (24.5s - 37.791s)
        # ----------------------------------------------------
        self.play(
            FadeOut(share_group),
            FadeOut(arrow_iso_a), FadeOut(arrow_iso_b),
            FadeOut(arrow_share_a), FadeOut(arrow_share_b),
            p1_full.animate.scale(0.7).move_to(LEFT * 4.6 + UP * 1.55),
            p2_full.animate.scale(0.7).move_to(RIGHT * 4.6 + UP * 1.55),
            ram_full.animate.scale(0.7).move_to(UP * 1.55),
            run_time=1.2
        )

        # Three Grand KPI Cards at Bottom (y = -1.2)
        kpi_1 = RoundedRectangle(corner_radius=0.12, width=3.8, height=1.55, color=COLOR_CYAN, fill_color="#0A1E36", fill_opacity=0.95, stroke_width=1.8).move_to(LEFT * 4.2 + DOWN * 1.2)
        t_k1_head = Text("PROCESS ISOLATION", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(kpi_1.get_top() + DOWN * 0.28)
        t_k1_body = Text("Zero cross-process corruption.\nHardware-enforced bounds.\nComplete security sandbox.", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED, line_spacing=0.8).next_to(t_k1_head, DOWN, buff=0.12)
        card1 = VGroup(kpi_1, t_k1_head, t_k1_body)

        kpi_2 = RoundedRectangle(corner_radius=0.12, width=3.8, height=1.55, color=COLOR_PURPLE, fill_color="#230B38", fill_opacity=0.95, stroke_width=1.8).move_to(DOWN * 1.2)
        t_k2_head = Text("MEMORY SHARING", font=FONT_MAIN, font_size=11, color=COLOR_PURPLE, weight="BOLD").move_to(kpi_2.get_top() + DOWN * 0.28)
        t_k2_body = Text("Shared code loaded once.\nZero duplicated libraries.\nEnormous RAM efficiency.", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED, line_spacing=0.8).next_to(t_k2_head, DOWN, buff=0.12)
        card2 = VGroup(kpi_2, t_k2_head, t_k2_body)

        kpi_3 = RoundedRectangle(corner_radius=0.12, width=3.8, height=1.55, color=COLOR_GREEN, fill_color="#032617", fill_opacity=0.95, stroke_width=1.8).move_to(RIGHT * 4.2 + DOWN * 1.2)
        t_k3_head = Text("TOTAL TRANSPARENCY", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(kpi_3.get_top() + DOWN * 0.28)
        t_k3_body = Text("Demand paging from SSD.\nBoundless 64-bit addresses.\nSeamless execution restart.", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED, line_spacing=0.8).next_to(t_k3_head, DOWN, buff=0.12)
        card3 = VGroup(kpi_3, t_k3_head, t_k3_body)

        kpis = VGroup(card1, card2, card3)
        self.play(FadeIn(kpis, shift=UP * 0.25), run_time=2.2)

        # Climax Banner in center
        climax_banner = RoundedRectangle(corner_radius=0.1, width=9.8, height=0.5, color=COLOR_AMBER, fill_color="#2D1A04", fill_opacity=0.95, stroke_width=2).move_to(DOWN * 0.05)
        climax_txt = Text("Virtual Memory: Turning Finite Silicon into an Infinite Playground", font=FONT_MAIN, font_size=11, color=WHITE, weight="BOLD").move_to(climax_banner)
        climax_group = VGroup(climax_banner, climax_txt)

        self.play(FadeIn(climax_group, scale=0.95), run_time=1.5)
        self.wait(8.391) # Exactly reaches 37.791s!
