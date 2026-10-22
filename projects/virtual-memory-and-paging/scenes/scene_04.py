from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        # ----------------------------------------------------
        # Styling & Palette
        # ----------------------------------------------------
        self.camera.background_color = "#0A0F1D"
        
        FONT_MAIN = "Segoe UI"
        COLOR_CYAN = "#00F0FF"
        COLOR_AMBER = "#F59E0B"
        COLOR_GREEN = "#10B981"
        COLOR_RED = "#EF4444"
        COLOR_PURPLE = "#8B5CF6"
        COLOR_DARK = "#111C33"
        COLOR_BORDER = "#1E2E4A"
        COLOR_TEXT_MUTED = "#94A3B8"
        
        # ----------------------------------------------------
        # Universal Header
        # ----------------------------------------------------
        badge_box = RoundedRectangle(
            corner_radius=0.1, width=3.4, height=0.42,
            color=COLOR_RED, fill_color=COLOR_RED, fill_opacity=0.15, stroke_width=1.5
        )
        badge_txt = Text("PART 04  •  DEMAND PAGING", font=FONT_MAIN, font_size=11, color=COLOR_RED, weight="BOLD").move_to(badge_box)
        badge = VGroup(badge_box, badge_txt).to_corner(UL, buff=0.45)
        
        title_txt = Text("Page Faults & Storage Swapping", font=FONT_MAIN, font_size=22, color=WHITE, weight="BOLD")
        title_txt.next_to(badge, RIGHT, buff=0.35)
        
        div_line = Line(LEFT * 6.8, RIGHT * 6.8, stroke_color="#1E293B", stroke_width=1.5)
        div_line.to_edge(UP, buff=0.95)
        
        header = VGroup(badge, title_txt, div_line)
        self.play(FadeIn(header, shift=DOWN * 0.15), run_time=0.8)
        self.wait(1.5) # Reach 2.3s

        # ----------------------------------------------------
        # Sentence 0 & 1: The 3-Tier Hierarchy & Present Bit = 0
        # (2.3s - 9.3s)
        # ----------------------------------------------------
        # Tier 1: Application PTE (Top, y = 1.7)
        pte_card = RoundedRectangle(corner_radius=0.12, width=11.6, height=1.05, color=COLOR_CYAN, fill_color=COLOR_DARK, fill_opacity=0.95, stroke_width=1.8).move_to(UP * 1.7)
        pte_title = Text("APPLICATION PROCESS  •  PAGE TABLE ENTRY FOR PAGE 42", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(pte_card.get_top() + DOWN * 0.22)
        
        f_vpn = Text("VPN: 42 (0x002A)", font=FONT_MAIN, font_size=10, color=WHITE).move_to(pte_card.get_left() + RIGHT * 1.6 + DOWN * 0.15)
        
        p_badge_box = RoundedRectangle(corner_radius=0.08, width=2.4, height=0.35, color=COLOR_RED, fill_color="#3B0D0D", fill_opacity=0.9, stroke_width=1.5).move_to(pte_card.get_left() + RIGHT * 4.6 + DOWN * 0.15)
        p_badge_txt = Text("PRESENT BIT: 0", font=FONT_MAIN, font_size=10, color=COLOR_RED, weight="BOLD").move_to(p_badge_box)
        p_badge = VGroup(p_badge_box, p_badge_txt)
        
        f_pfn = Text("PFN: [ Not in RAM ]", font=FONT_MAIN, font_size=10, color=COLOR_TEXT_MUTED).move_to(pte_card.get_left() + RIGHT * 7.4 + DOWN * 0.15)
        f_disk = Text("Disk Loc: Sector #8840", font=FONT_MAIN, font_size=10, color=COLOR_AMBER).move_to(pte_card.get_left() + RIGHT * 10.1 + DOWN * 0.15)
        
        pte_full = VGroup(pte_card, pte_title, f_vpn, p_badge, f_pfn, f_disk)

        # Tier 2: Physical RAM (Middle, y = 0.25)
        ram_card = RoundedRectangle(corner_radius=0.12, width=11.6, height=1.05, color=COLOR_GREEN, fill_color=COLOR_DARK, fill_opacity=0.95, stroke_width=1.8).move_to(UP * 0.25)
        ram_title = Text("PHYSICAL RAM (DRAM)", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(ram_card.get_top() + DOWN * 0.22)
        
        ram_frames = VGroup()
        r_slots = [
            ("Frame 0", "OS Kernel", "#334155"),
            ("Frame 1", "App Code", "#334155"),
            ("Frame 2", "App Data", "#334155"),
            ("Frame 3", "FREE FRAME", COLOR_CYAN)
        ]
        for f_label, f_state, col in r_slots:
            s_box = RoundedRectangle(corner_radius=0.06, width=2.6, height=0.42, color=col, fill_color="#0A182E" if col == COLOR_CYAN else "#1E293B", fill_opacity=0.8, stroke_width=1.2)
            s_t1 = Text(f_label, font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(s_box.get_left() + RIGHT * 0.6)
            s_t2 = Text(f_state, font=FONT_MAIN, font_size=8, color=col).move_to(s_box.get_right() + LEFT * 0.6)
            ram_frames.add(VGroup(s_box, s_t1, s_t2))
        ram_frames.arrange(RIGHT, buff=0.25).move_to(ram_card.get_center() + DOWN * 0.15)
        ram_full = VGroup(ram_card, ram_title, ram_frames)

        # Tier 3: Secondary Storage (Bottom, y = -1.2)
        ssd_card = RoundedRectangle(corner_radius=0.12, width=11.6, height=1.05, color=COLOR_AMBER, fill_color=COLOR_DARK, fill_opacity=0.95, stroke_width=1.8).move_to(DOWN * 1.2)
        ssd_title = Text("SECONDARY STORAGE (NVMe SSD / Swap Partition)", font=FONT_MAIN, font_size=11, color=COLOR_AMBER, weight="BOLD").move_to(ssd_card.get_top() + DOWN * 0.22)
        
        disk_block = RoundedRectangle(corner_radius=0.08, width=5.2, height=0.42, color=COLOR_AMBER, fill_color="#361D02", fill_opacity=0.9, stroke_width=1.5).move_to(ssd_card.get_center() + DOWN * 0.15)
        disk_block_txt = Text("Page 42 Data Block (4096 Bytes on NVMe)", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(disk_block)
        disk_group = VGroup(disk_block, disk_block_txt)
        ssd_full = VGroup(ssd_card, ssd_title, disk_group)

        self.play(FadeIn(pte_full, shift=DOWN * 0.2), run_time=1.8)
        self.play(FadeIn(ram_full), FadeIn(ssd_full, shift=UP * 0.2), run_time=2.0)
        self.wait(3.2) # Reach 9.3s (Sentence 1 ends at 9.30s)

        # ----------------------------------------------------
        # Sentence 2: The Hardware Page Fault Trap
        # (9.3s - 16.1s)
        # ----------------------------------------------------
        fault_badge = RoundedRectangle(corner_radius=0.1, width=8.8, height=0.52, color=COLOR_RED, fill_color="#420808", fill_opacity=0.95, stroke_width=2.5).move_to(UP * 0.98)
        fault_txt = Text("HARDWARE TRAP: PAGE FAULT EXCEPTION (INTERRUPT 14)", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(fault_badge)
        fault_group = VGroup(fault_badge, fault_txt)

        halt_tag = Text("Execution Halted  •  CR2 Register = 0x002A0000", font=FONT_MAIN, font_size=9, color=COLOR_RED).next_to(fault_badge, DOWN, buff=0.08)

        self.play(
            FadeIn(fault_group, scale=1.05),
            FadeIn(halt_tag),
            run_time=2.0
        )
        self.wait(4.8) # Reach 16.1s (Sentence 2 ends at 16.10s)

        # ----------------------------------------------------
        # Sentence 3: OS Kernel Takes Control
        # (16.1s - 19.6s)
        # ----------------------------------------------------
        self.play(FadeOut(fault_group), FadeOut(halt_tag), run_time=0.6)

        kernel_shield = RoundedRectangle(corner_radius=0.12, width=9.2, height=0.5, color=COLOR_PURPLE, fill_color="#2B0E44", fill_opacity=0.95, stroke_width=2).move_to(UP * 0.98)
        kernel_txt = Text("OS KERNEL PAGE FAULT HANDLER: TAKES FULL CONTROL", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(kernel_shield)
        kernel_group = VGroup(kernel_shield, kernel_txt)

        self.play(FadeIn(kernel_group, shift=DOWN * 0.1), run_time=1.4)
        self.wait(1.5) # Reach 19.6s (Sentence 3 ends at 19.58s)

        # ----------------------------------------------------
        # Sentence 4: Allocate, Stream from SSD, Update PTE, Restart
        # (19.6s - 31.1s)
        # ----------------------------------------------------
        self.play(FadeOut(kernel_group), run_time=0.6)

        # Free frame 3 lights up
        free_frame = ram_frames[3]
        alloc_aura = SurroundingRectangle(free_frame, color=COLOR_CYAN, buff=0.06, stroke_width=2.5)
        alloc_lbl = Text("Allocated!", font=FONT_MAIN, font_size=9, color=COLOR_CYAN, weight="BOLD").next_to(free_frame, UP, buff=0.06)

        self.play(Create(alloc_aura), FadeIn(alloc_lbl), run_time=1.5)

        # Stream missing 4KB block from SSD upward into RAM Frame 3
        dma_packet = RoundedRectangle(corner_radius=0.08, width=2.6, height=0.42, color=COLOR_GREEN, fill_color="#063E26", fill_opacity=0.95, stroke_width=2).move_to(disk_block.get_center())
        dma_txt = Text("Page 42 [4 KB]", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(dma_packet)
        dma_group = VGroup(dma_packet, dma_txt)

        stream_arrow = Arrow(start=ssd_card.get_top() + RIGHT * 2.8, end=free_frame.get_bottom(), color=COLOR_GREEN, stroke_width=3, tip_length=0.16)
        stream_tag = Text("High-Speed NVMe DMA Stream", font=FONT_MAIN, font_size=9, color=COLOR_GREEN).next_to(stream_arrow, RIGHT, buff=0.15)

        self.play(Create(stream_arrow), FadeIn(stream_tag), run_time=1.2)
        self.play(dma_group.animate.move_to(free_frame.get_center()), run_time=2.2)

        # Update Frame 3 text
        new_f3_txt = Text("Frame 3\nPage 42", font=FONT_MAIN, font_size=8, color=COLOR_GREEN, weight="BOLD").move_to(free_frame)
        self.play(Transform(free_frame, new_f3_txt), run_time=0.8)

        # Update PTE: Present Bit becomes 1 (Green), PFN becomes Frame 3
        p_badge_box_new = RoundedRectangle(corner_radius=0.08, width=2.4, height=0.35, color=COLOR_GREEN, fill_color="#063E26", fill_opacity=0.95, stroke_width=1.5).move_to(p_badge_box)
        p_badge_txt_new = Text("PRESENT BIT: 1", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(p_badge_box_new)
        p_badge_new = VGroup(p_badge_box_new, p_badge_txt_new)
        
        f_pfn_new = Text("PFN: Frame 3", font=FONT_MAIN, font_size=10, color=COLOR_GREEN, weight="BOLD").move_to(f_pfn)

        self.play(
            Transform(p_badge, p_badge_new),
            Transform(f_pfn, f_pfn_new),
            run_time=2.0
        )
        self.wait(3.2) # Reach 31.1s (Sentence 4 ends at 31.14s)

        # ----------------------------------------------------
        # Sentence 5: Seamless Instruction Restart
        # (31.1s - 35.099s)
        # ----------------------------------------------------
        self.play(
            FadeOut(alloc_aura), FadeOut(alloc_lbl),
            FadeOut(stream_arrow), FadeOut(stream_tag), FadeOut(dma_group),
            run_time=0.6
        )

        success_pill = RoundedRectangle(corner_radius=0.12, width=10.5, height=0.48, color=COLOR_GREEN, fill_color="#022818", fill_opacity=0.95, stroke_width=2).move_to(DOWN * 2.2)
        success_txt = Text("INSTRUCTION RESTARTS: 100% TRANSPARENT DEMAND PAGING SUCCESS!", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(success_pill)
        success_group = VGroup(success_pill, success_txt)

        self.play(FadeIn(success_group, scale=0.95), run_time=1.4)
        self.wait(1.999) # Exactly reaches 35.099s!
