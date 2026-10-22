from manim import *
import numpy as np

class Scene02(Scene):
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
        COLOR_RED = "#EF4444"
        COLOR_DARK = "#111C33"
        COLOR_BORDER = "#1E2E4A"
        COLOR_TEXT_MUTED = "#94A3B8"
        
        # ----------------------------------------------------
        # Universal Header
        # ----------------------------------------------------
        badge_box = RoundedRectangle(
            corner_radius=0.1, width=3.4, height=0.42,
            color=COLOR_CYAN, fill_color=COLOR_CYAN, fill_opacity=0.15, stroke_width=1.5
        )
        badge_txt = Text("PART 02  •  PAGING & TRANSLATION", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(badge_box)
        badge = VGroup(badge_box, badge_txt).to_corner(UL, buff=0.45)
        
        title_txt = Text("Address Anatomy & The Page Table", font=FONT_MAIN, font_size=22, color=WHITE, weight="BOLD")
        title_txt.next_to(badge, RIGHT, buff=0.35)
        
        div_line = Line(LEFT * 6.8, RIGHT * 6.8, stroke_color="#1E293B", stroke_width=1.5)
        div_line.to_edge(UP, buff=0.95)
        
        header = VGroup(badge, title_txt, div_line)
        self.play(FadeIn(header, shift=DOWN * 0.15), run_time=0.8)
        self.wait(2.3) # Reach 3.1s (Sentence 0 ends at 3.05s)

        # ----------------------------------------------------
        # Sentence 1, 2, 3: 4 KB Chunks: Pages vs Frames
        # (3.1s - 15.8s)
        # ----------------------------------------------------
        # Virtual Pages column (Left)
        vp_card = RoundedRectangle(corner_radius=0.14, width=4.6, height=3.6, color=COLOR_CYAN, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=1.8).move_to(LEFT * 4.2 + DOWN * 0.1)
        vp_header = Text("VIRTUAL MEMORY (Pages)", font=FONT_MAIN, font_size=12, color=COLOR_CYAN, weight="BOLD").move_to(vp_card.get_top() + DOWN * 0.3)
        
        pages_group = VGroup()
        page_titles = [("Page 0", "Code Segment", COLOR_CYAN), ("Page 1", "Static Data", "#38BDF8"),
                       ("Page 2", "Heap Dynamic", "#60A5FA"), ("Page 3", "Runtime Stack", "#818CF8")]
        for p_num, p_desc, col in page_titles:
            p_box = RoundedRectangle(corner_radius=0.08, width=4.0, height=0.58, color=col, fill_color=col, fill_opacity=0.25, stroke_width=1.2)
            p_t1 = Text(p_num, font=FONT_MAIN, font_size=11, color=WHITE, weight="BOLD").move_to(p_box.get_left() + RIGHT * 0.8)
            p_t2 = Text(f"{p_desc} [4 KB]", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).move_to(p_box.get_right() + LEFT * 1.1)
            pages_group.add(VGroup(p_box, p_t1, p_t2))
        pages_group.arrange(DOWN, buff=0.12).next_to(vp_header, DOWN, buff=0.22)
        vp_full = VGroup(vp_card, vp_header, pages_group)

        # Physical Frames column (Right)
        pf_card = RoundedRectangle(corner_radius=0.14, width=4.6, height=3.6, color=COLOR_GREEN, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=1.8).move_to(RIGHT * 4.2 + DOWN * 0.1)
        pf_header = Text("PHYSICAL RAM (Frames)", font=FONT_MAIN, font_size=12, color=COLOR_GREEN, weight="BOLD").move_to(pf_card.get_top() + DOWN * 0.3)
        
        frames_group = VGroup()
        frame_titles = [("Frame 0", "OS Kernel", "#475569"), ("Frame 1", "Free Frame", "#1E293B"),
                        ("Frame 2", "Page 1 (Data)", COLOR_GREEN), ("Frame 3", "Page 0 (Code)", COLOR_GREEN),
                        ("Frame 4", "Background Daemon", "#475569")]
        for f_num, f_desc, col in frame_titles:
            f_box = RoundedRectangle(corner_radius=0.08, width=4.0, height=0.48, color=col, fill_color=col, fill_opacity=0.35, stroke_width=1.2)
            f_t1 = Text(f_num, font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(f_box.get_left() + RIGHT * 0.8)
            f_t2 = Text(f"{f_desc} [4 KB]", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).move_to(f_box.get_right() + LEFT * 1.1)
            frames_group.add(VGroup(f_box, f_t1, f_t2))
        frames_group.arrange(DOWN, buff=0.1).next_to(pf_header, DOWN, buff=0.22)
        pf_full = VGroup(pf_card, pf_header, frames_group)

        # Central Chunk Size Identity Card
        chunk_card = RoundedRectangle(corner_radius=0.12, width=3.6, height=1.5, color=COLOR_AMBER, fill_color="#261601", fill_opacity=0.95, stroke_width=2).move_to(DOWN * 0.1)
        c_t1 = Text("Equal Sized Blocks", font=FONT_MAIN, font_size=12, color=COLOR_AMBER, weight="BOLD").move_to(chunk_card.get_top() + DOWN * 0.32)
        c_t2 = Text("4,096 Bytes (4 KB)", font=FONT_MAIN, font_size=15, color=WHITE, weight="BOLD").next_to(c_t1, DOWN, buff=0.12)
        c_t3 = Text("2^12 Bytes  •  12-bit Offset", font=FONT_MAIN, font_size=10, color=COLOR_AMBER).next_to(c_t2, DOWN, buff=0.1)
        chunk_full = VGroup(chunk_card, c_t1, c_t2, c_t3)

        self.play(
            FadeIn(vp_full, shift=RIGHT * 0.3),
            FadeIn(pf_full, shift=LEFT * 0.3),
            FadeIn(chunk_full, scale=0.9),
            run_time=2.2
        )
        self.wait(4.6) # Reach 9.9s (Sentence 1 ends at 9.89s)

        # S2: Emphasize Pages in Virtual Space (10.2s - 13.1s)
        aura_pages = SurroundingRectangle(pages_group, color=COLOR_CYAN, buff=0.1, stroke_width=2.5)
        page_badge = Text("Virtual Units: PAGES", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").next_to(aura_pages, DOWN, buff=0.15)
        self.play(Create(aura_pages), FadeIn(page_badge), run_time=1.2)
        self.wait(2.0) # Reach 13.1s (Sentence 2 ends at 13.12s)

        # S3: Emphasize Frames in Physical RAM (13.4s - 15.8s)
        aura_frames = SurroundingRectangle(frames_group, color=COLOR_GREEN, buff=0.1, stroke_width=2.5)
        frame_badge = Text("Physical Units: FRAMES", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").next_to(aura_frames, DOWN, buff=0.15)
        self.play(
            FadeOut(aura_pages), FadeOut(page_badge),
            Create(aura_frames), FadeIn(frame_badge),
            run_time=1.2
        )
        self.wait(1.5) # Reach 15.8s (Sentence 3 ends at 15.77s)

        # Clean up Phase 1
        self.play(
            FadeOut(aura_frames), FadeOut(frame_badge),
            FadeOut(vp_full), FadeOut(pf_full), FadeOut(chunk_full),
            run_time=0.9
        )

        # ----------------------------------------------------
        # Sentence 4: Splitting the 32-bit Virtual Address
        # (16.7s - 24.2s)
        # ----------------------------------------------------
        reg_title = Text("CPU Instruction Targets 32-Bit Virtual Address: 0x000031A4", font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(np.array([0, 2.45, 0]))
        
        # Register container
        vpn_box = RoundedRectangle(corner_radius=0.1, width=5.6, height=0.75, color=COLOR_CYAN, fill_color="#0A243D", fill_opacity=0.92, stroke_width=2).move_to(np.array([-2.4, 1.8, 0]))
        vpn_t1 = Text("Virtual Page Number (VPN)  [20 bits]", font=FONT_MAIN, font_size=10, color=COLOR_CYAN, weight="BOLD").move_to(vpn_box.get_top() + DOWN * 0.22)
        vpn_t2 = Text("0x00003  (Page Index 3)", font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(vpn_box.get_bottom() + UP * 0.22)
        vpn_group = VGroup(vpn_box, vpn_t1, vpn_t2)

        off_box = RoundedRectangle(corner_radius=0.1, width=4.4, height=0.75, color=COLOR_AMBER, fill_color="#361D02", fill_opacity=0.92, stroke_width=2).move_to(np.array([2.8, 1.8, 0]))
        off_t1 = Text("Page Offset  [12 bits]", font=FONT_MAIN, font_size=10, color=COLOR_AMBER, weight="BOLD").move_to(off_box.get_top() + DOWN * 0.22)
        off_t2 = Text("0x1A4  (Byte 420)", font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(off_box.get_bottom() + UP * 0.22)
        off_group = VGroup(off_box, off_t1, off_t2)

        split_icon = Line(vpn_box.get_right() + UP * 0.38, vpn_box.get_right() + DOWN * 0.38, color=WHITE, stroke_width=2.5)

        self.play(
            FadeIn(reg_title),
            FadeIn(vpn_group, shift=DOWN * 0.2),
            FadeIn(off_group, shift=DOWN * 0.2),
            Create(split_icon),
            run_time=2.0
        )
        self.wait(5.5) # Reach 24.2s (Sentence 4 ends at 24.17s)

        # ----------------------------------------------------
        # Sentence 5: Page Table Lookup via VPN
        # (24.2s - 29.6s)
        # ----------------------------------------------------
        pt_card = RoundedRectangle(corner_radius=0.12, width=11.2, height=1.9, color="#334155", fill_color="#09101D", fill_opacity=0.95, stroke_width=1.5).move_to(np.array([0, 0.1, 0]))
        pt_header_bar = RoundedRectangle(corner_radius=0.08, width=11.2, height=0.38, color="#334155", fill_color="#1E293B", fill_opacity=0.8, stroke_width=0).move_to(pt_card.get_top() + DOWN * 0.19)
        
        pt_title = Text("PAGE TABLE (In-Memory Lookup Directory)", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(pt_header_bar.get_left() + RIGHT * 2.6)
        pt_cols = Text("Index (VPN)       Present       Physical Frame (PFN)       Access Rights", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).move_to(pt_header_bar.get_right() + LEFT * 3.4)
        
        # Rows
        rows_group = VGroup()
        row_data = [
            ("VPN 0x00000", "P = 1", "PFN: 0x00018", "Read / Execute (Code)"),
            ("VPN 0x00001", "P = 1", "PFN: 0x00022", "Read / Write (Data)"),
            ("VPN 0x00002", "P = 0", "PFN: [ On Disk ]", "--- (Not Present)"),
            ("VPN 0x00003", "P = 1", "PFN: 0x0007E", "Read / Write (Target)")
        ]
        
        for r_vpn, r_p, r_pfn, r_acc in row_data:
            r_box = Rectangle(width=10.8, height=0.28, color="#1E2E4A", fill_color="#0F172A", fill_opacity=0.6, stroke_width=0.8)
            t_vpn = Text(r_vpn, font=FONT_MAIN, font_size=9, color=COLOR_CYAN).move_to(r_box.get_left() + RIGHT * 1.2)
            t_p = Text(r_p, font=FONT_MAIN, font_size=9, color=COLOR_GREEN if "1" in r_p else COLOR_RED).move_to(r_box.get_left() + RIGHT * 3.5)
            t_pfn = Text(r_pfn, font=FONT_MAIN, font_size=9, color=COLOR_GREEN if "1" in r_p else COLOR_AMBER, weight="BOLD").move_to(r_box.get_left() + RIGHT * 6.2)
            t_acc = Text(r_acc, font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).move_to(r_box.get_left() + RIGHT * 9.2)
            rows_group.add(VGroup(r_box, t_vpn, t_p, t_pfn, t_acc))
            
        rows_group.arrange(DOWN, buff=0.06).next_to(pt_header_bar, DOWN, buff=0.12)
        pt_full = VGroup(pt_card, pt_header_bar, pt_title, pt_cols, rows_group)

        self.play(FadeIn(pt_full, shift=UP * 0.2), run_time=1.8)

        # Index pointer arrow from VPN box to Row 3
        row_3 = rows_group[3]
        index_arrow = Arrow(
            start=vpn_box.get_bottom() + LEFT * 0.5,
            end=row_3.get_left() + RIGHT * 0.1,
            color=COLOR_CYAN, stroke_width=3, tip_length=0.16
        )
        row_highlight = SurroundingRectangle(row_3, color=COLOR_GREEN, buff=0.04, stroke_width=2.5)

        self.play(
            Create(index_arrow),
            Create(row_highlight),
            row_3.animate.set_color(COLOR_GREEN),
            run_time=2.2
        )
        self.wait(1.4) # Reach 29.6s (Sentence 5 ends at 29.57s)

        # ----------------------------------------------------
        # Sentence 6: Physical Address Synthesis & Straight Offset
        # (29.6s - 38.922s)
        # ----------------------------------------------------
        phys_title = Text("Synthesized 32-Bit Physical Address: 0x0007E1A4", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(np.array([0, -1.25, 0]))

        pfn_box = RoundedRectangle(corner_radius=0.1, width=5.6, height=0.72, color=COLOR_GREEN, fill_color="#042618", fill_opacity=0.92, stroke_width=2).move_to(np.array([-2.4, -1.75, 0]))
        pfn_t1 = Text("Physical Frame Number (PFN)  [20 bits]", font=FONT_MAIN, font_size=10, color=COLOR_GREEN, weight="BOLD").move_to(pfn_box.get_top() + DOWN * 0.2)
        pfn_t2 = Text("0x0007E  (From Page Table)", font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(pfn_box.get_bottom() + UP * 0.2)
        pfn_group = VGroup(pfn_box, pfn_t1, pfn_t2)

        phys_off_box = RoundedRectangle(corner_radius=0.1, width=4.4, height=0.72, color=COLOR_AMBER, fill_color="#361D02", fill_opacity=0.92, stroke_width=2).move_to(np.array([2.8, -1.75, 0]))
        phys_off_t1 = Text("Page Offset  [12 bits]", font=FONT_MAIN, font_size=10, color=COLOR_AMBER, weight="BOLD").move_to(phys_off_box.get_top() + DOWN * 0.2)
        phys_off_t2 = Text("0x1A4  (Untouched Direct Bypass)", font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(phys_off_box.get_bottom() + UP * 0.2)
        phys_off_group = VGroup(phys_off_box, phys_off_t1, phys_off_t2)

        # Arrow from Row 3 PFN to bottom PFN box
        pfn_arrow = Arrow(
            start=row_3[3].get_bottom() + DOWN * 0.05,
            end=pfn_box.get_top(),
            color=COLOR_GREEN, stroke_width=3, tip_length=0.16
        )

        # Offset bypass arrow passing straight down on right side!
        offset_arrow = Line(
            start=off_box.get_bottom(),
            end=phys_off_box.get_top(),
            color=COLOR_AMBER, stroke_width=3.5
        ).add_tip(tip_length=0.18)
        
        offset_tag = RoundedRectangle(corner_radius=0.08, width=2.4, height=0.32, color=COLOR_AMBER, fill_color="#241301", fill_opacity=0.9, stroke_width=1.2).move_to(np.array([4.2, 0.0, 0]))
        offset_tag_txt = Text("Passed Untouched", font=FONT_MAIN, font_size=9, color=COLOR_AMBER, weight="BOLD").move_to(offset_tag)
        offset_tag_group = VGroup(offset_tag, offset_tag_txt)

        self.play(
            FadeIn(phys_title),
            Create(pfn_arrow),
            FadeIn(pfn_group, shift=UP * 0.15),
            run_time=2.2
        )
        
        self.play(
            Create(offset_arrow),
            FadeIn(offset_tag_group),
            FadeIn(phys_off_group, shift=UP * 0.15),
            run_time=2.2
        )
        
        # Complete Badge at y = -2.35
        comp_badge = RoundedRectangle(corner_radius=0.08, width=8.6, height=0.38, color=COLOR_GREEN, fill_color="#032115", fill_opacity=0.95, stroke_width=1.5).move_to(np.array([0, -2.35, 0]))
        comp_txt = Text("TRANSLATION RESOLVED: Pinpoints Exact Byte 420 in Physical Frame 0x0007E", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(comp_badge)
        comp_group = VGroup(comp_badge, comp_txt)
        
        self.play(FadeIn(comp_group, scale=0.95), run_time=1.4)
        self.wait(3.522) # Exactly reaches 38.922s!
