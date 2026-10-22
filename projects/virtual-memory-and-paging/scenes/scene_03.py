from manim import *
import numpy as np

class Scene03(Scene):
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
            color=COLOR_GREEN, fill_color=COLOR_GREEN, fill_opacity=0.15, stroke_width=1.5
        )
        badge_txt = Text("PART 03  •  HARDWARE SPEED", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(badge_box)
        badge = VGroup(badge_box, badge_txt).to_corner(UL, buff=0.45)
        
        title_txt = Text("The Translation Lookaside Buffer (TLB)", font=FONT_MAIN, font_size=22, color=WHITE, weight="BOLD")
        title_txt.next_to(badge, RIGHT, buff=0.35)
        
        div_line = Line(LEFT * 6.8, RIGHT * 6.8, stroke_color="#1E293B", stroke_width=1.5)
        div_line.to_edge(UP, buff=0.95)
        
        header = VGroup(badge, title_txt, div_line)
        self.play(FadeIn(header, shift=DOWN * 0.15), run_time=0.8)
        self.wait(1.0) # Reach 1.8s (Sentence 0 ends at 1.62s)

        # ----------------------------------------------------
        # Sentence 1 & 2: The Bottleneck (Two Round Trips to RAM)
        # (1.8s - 13.4s)
        # ----------------------------------------------------
        # Left station: CPU Core
        cpu_box = RoundedRectangle(corner_radius=0.15, width=4.0, height=2.8, color=COLOR_CYAN, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=2).move_to(LEFT * 4.3 + UP * 0.4)
        cpu_header = Text("CPU CORE SILICON", font=FONT_MAIN, font_size=12, color=COLOR_CYAN, weight="BOLD").move_to(cpu_box.get_top() + DOWN * 0.3)
        cpu_instr = Text("LOAD [0x004031A4]", font=FONT_MAIN, font_size=11, color=WHITE, weight="BOLD").next_to(cpu_header, DOWN, buff=0.3)
        cpu_badge = Text("Requests Memory Byte", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).next_to(cpu_instr, DOWN, buff=0.2)
        cpu_station = VGroup(cpu_box, cpu_header, cpu_instr, cpu_badge)

        # Right station: Physical DRAM
        dram_box = RoundedRectangle(corner_radius=0.15, width=4.0, height=2.8, color=COLOR_AMBER, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=2).move_to(RIGHT * 4.3 + UP * 0.4)
        dram_header = Text("MAIN MEMORY (DRAM)", font=FONT_MAIN, font_size=12, color=COLOR_AMBER, weight="BOLD").move_to(dram_box.get_top() + DOWN * 0.3)
        
        dram_pt = RoundedRectangle(corner_radius=0.08, width=3.4, height=0.55, color="#475569", fill_color="#1E293B", fill_opacity=0.8, stroke_width=1.2).next_to(dram_header, DOWN, buff=0.2)
        dram_pt_txt = Text("Page Table (Translation)", font=FONT_MAIN, font_size=9, color=COLOR_CYAN).move_to(dram_pt)
        dram_pt_group = VGroup(dram_pt, dram_pt_txt)
        
        dram_dt = RoundedRectangle(corner_radius=0.08, width=3.4, height=0.55, color="#475569", fill_color="#1E293B", fill_opacity=0.8, stroke_width=1.2).next_to(dram_pt, DOWN, buff=0.15)
        dram_dt_txt = Text("Actual Data Byte (Target)", font=FONT_MAIN, font_size=9, color=COLOR_GREEN).move_to(dram_dt)
        dram_dt_group = VGroup(dram_dt, dram_dt_txt)
        
        dram_station = VGroup(dram_box, dram_header, dram_pt_group, dram_dt_group)

        self.play(FadeIn(cpu_station, shift=RIGHT * 0.3), FadeIn(dram_station, shift=LEFT * 0.3), run_time=1.8)

        # Access 1: Trip to Page Table
        trip1_line = Arrow(start=cpu_box.get_right() + UP * 0.3, end=dram_pt.get_left(), color=COLOR_RED, stroke_width=2.5, tip_length=0.15)
        trip1_lbl = Text("Trip 1: Read Page Table in DRAM (~100 ns)", font=FONT_MAIN, font_size=10, color=COLOR_RED).move_to(UP * 1.3)
        
        self.play(Create(trip1_line), FadeIn(trip1_lbl), run_time=1.8)
        self.wait(1.5) # Reach 6.9s (Sentence 1 ends at 6.63s)

        # Access 2: Trip to Data
        trip2_line = Arrow(start=cpu_box.get_right() + DOWN * 0.3, end=dram_dt.get_left(), color=COLOR_RED, stroke_width=2.5, tip_length=0.15)
        trip2_lbl = Text("Trip 2: Read Actual Data in DRAM (~100 ns)", font=FONT_MAIN, font_size=10, color=COLOR_RED).move_to(UP * 0.05)
        
        self.play(Create(trip2_line), FadeIn(trip2_lbl), run_time=1.8)
        
        # Stall Penalty Warning Banner
        stall_card = RoundedRectangle(corner_radius=0.1, width=8.8, height=0.45, color=COLOR_RED, fill_color="#360808", fill_opacity=0.95, stroke_width=1.5).move_to(DOWN * 1.3)
        stall_txt = Text("2X DRAM ACCESS LATENCY: 200 ns TOTAL — CUTS PERFORMANCE IN HALF!", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(stall_card)
        stall_group = VGroup(stall_card, stall_txt)
        
        self.play(FadeIn(stall_group, shift=UP * 0.1), run_time=1.2)
        self.wait(3.5) # Reach 13.4s (Sentence 2 ends at 13.38s)

        # ----------------------------------------------------
        # Sentence 3: The MMU & The TLB Cache (On-Chip Silicon)
        # (13.4s - 22.5s)
        # ----------------------------------------------------
        self.play(
            FadeOut(trip1_line), FadeOut(trip1_lbl),
            FadeOut(trip2_line), FadeOut(trip2_lbl),
            FadeOut(stall_group),
            cpu_station.animate.scale(0.85).move_to(LEFT * 5.0 + UP * 0.4),
            dram_station.animate.scale(0.85).move_to(RIGHT * 5.0 + UP * 0.4),
            run_time=1.2
        )

        # Central On-Chip MMU + TLB Container
        mmu_box = RoundedRectangle(corner_radius=0.15, width=5.8, height=3.4, color=COLOR_CYAN, fill_color="#091426", fill_opacity=0.95, stroke_width=2).move_to(UP * 0.3)
        mmu_header = RoundedRectangle(corner_radius=0.1, width=5.8, height=0.45, color=COLOR_CYAN, fill_color="#0369A1", fill_opacity=0.4, stroke_width=0).move_to(mmu_box.get_top() + DOWN * 0.225)
        mmu_title = Text("ON-CHIP MMU  •  TLB CACHE", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(mmu_header)
        
        # High speed SRAM TLB Table rows
        tlb_rows = VGroup()
        tlb_data = [
            ("VPN: 0x0040", "PFN: 0x0007E", "VALID", COLOR_GREEN),
            ("VPN: 0x0012", "PFN: 0x00045", "VALID", COLOR_GREEN),
            ("VPN: 0x008A", "PFN: 0x00091", "VALID", COLOR_GREEN),
            ("VPN: 0x0005", "PFN: 0x0001B", "VALID", COLOR_GREEN)
        ]
        
        for vpn, pfn, val, col in tlb_data:
            r_box = RoundedRectangle(corner_radius=0.06, width=5.2, height=0.42, color="#25354F", fill_color="#0C1B33", fill_opacity=0.85, stroke_width=1)
            t_vpn = Text(vpn, font=FONT_MAIN, font_size=10, color=COLOR_CYAN, weight="BOLD").move_to(r_box.get_left() + RIGHT * 0.8)
            t_pfn = Text(pfn, font=FONT_MAIN, font_size=10, color=col, weight="BOLD").move_to(r_box.get_center())
            t_val = Text(val, font=FONT_MAIN, font_size=9, color=col).move_to(r_box.get_right() + LEFT * 0.6)
            tlb_rows.add(VGroup(r_box, t_vpn, t_pfn, t_val))
            
        tlb_rows.arrange(DOWN, buff=0.08).next_to(mmu_header, DOWN, buff=0.18)
        
        speed_badge = Text("Dedicated Silicon Cache: < 1.0 Nanosecond Access!", font=FONT_MAIN, font_size=10, color=COLOR_AMBER).next_to(tlb_rows, DOWN, buff=0.18)
        mmu_full = VGroup(mmu_box, mmu_header, mmu_title, tlb_rows, speed_badge)

        self.play(FadeIn(mmu_full, scale=0.92), run_time=2.2)
        self.wait(5.7) # Reach 22.5s (Sentence 3 ends at 22.53s)

        # ----------------------------------------------------
        # Sentence 4: Sub-Nanosecond TLB Hit (Bypassing Page Table)
        # (22.5s - 32.8s)
        # ----------------------------------------------------
        hit_arrow = Arrow(start=cpu_station.get_right(), end=mmu_box.get_left(), color=COLOR_CYAN, stroke_width=3, tip_length=0.16)
        
        target_row = tlb_rows[0]
        hit_aura = SurroundingRectangle(target_row, color=COLOR_GREEN, buff=0.05, stroke_width=2.5)
        hit_tag = RoundedRectangle(corner_radius=0.08, width=2.4, height=0.35, color=COLOR_GREEN, fill_color="#063E26", fill_opacity=0.95, stroke_width=1.5).next_to(target_row, RIGHT, buff=0.3)
        hit_tag_txt = Text("TLB HIT: 0.8 ns!", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(hit_tag)
        hit_tag_group = VGroup(hit_tag, hit_tag_txt)

        self.play(Create(hit_arrow), run_time=1.0)
        self.play(
            Create(hit_aura),
            FadeIn(hit_tag_group),
            run_time=1.5
        )
        
        # Bypass arrow straight to data, skipping DRAM page table!
        direct_data_arrow = Arrow(
            start=mmu_box.get_right() + DOWN * 0.4,
            end=dram_station.get_left() + DOWN * 0.4,
            color=COLOR_GREEN, stroke_width=3.5, tip_length=0.18
        )
        bypass_tag = Text("Direct Data Fetch (Page Table Bypassed)", font=FONT_MAIN, font_size=9, color=COLOR_GREEN, weight="BOLD").next_to(direct_data_arrow, DOWN, buff=0.12)

        self.play(Create(direct_data_arrow), FadeIn(bypass_tag), run_time=1.8)

        # Latency Comparison Bars at Bottom (y = -1.8)
        comp_card = RoundedRectangle(corner_radius=0.12, width=11.2, height=1.05, color="#334155", fill_color="#0A1120", fill_opacity=0.95, stroke_width=1.5).move_to(DOWN * 1.8)
        
        bar_no_tlb = Rectangle(width=6.0, height=0.2, color=COLOR_RED, fill_color=COLOR_RED, fill_opacity=0.8, stroke_width=0).move_to(DOWN * 1.6 + LEFT * 0.5)
        lbl_no_tlb = Text("Without TLB: 200 ns (2 RAM Trips)", font=FONT_MAIN, font_size=9, color=COLOR_RED).next_to(bar_no_tlb, LEFT, buff=0.2)
        
        bar_with_tlb = Rectangle(width=3.0, height=0.2, color=COLOR_GREEN, fill_color=COLOR_GREEN, fill_opacity=0.8, stroke_width=0).move_to(DOWN * 2.0 + LEFT * 2.0)
        lbl_with_tlb = Text("With TLB: 100.8 ns (1 RAM Trip)", font=FONT_MAIN, font_size=9, color=COLOR_GREEN, weight="BOLD").next_to(bar_with_tlb, LEFT, buff=0.2)
        
        hit_rate_badge = Text("99%+ Hit Rate", font=FONT_MAIN, font_size=12, color=COLOR_AMBER, weight="BOLD").move_to(DOWN * 1.8 + RIGHT * 4.2)
        
        comp_full = VGroup(comp_card, bar_no_tlb, lbl_no_tlb, bar_with_tlb, lbl_with_tlb, hit_rate_badge)

        self.play(FadeIn(comp_full, shift=UP * 0.15), run_time=2.0)
        self.wait(3.0) # Reach 32.8s (Sentence 4 ends at 32.79s)

        # ----------------------------------------------------
        # Sentence 5: Rare TLB Miss Walk
        # (32.8s - 38.325s)
        # ----------------------------------------------------
        miss_note = RoundedRectangle(corner_radius=0.1, width=10.0, height=0.4, color=COLOR_AMBER, fill_color="#2D1903", fill_opacity=0.95, stroke_width=1.5).move_to(DOWN * 0.8)
        miss_txt = Text("On Rare TLB Miss: Hardware Page Table Walker reads DRAM, then populates TLB.", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(miss_note)
        miss_group = VGroup(miss_note, miss_txt)

        self.play(FadeIn(miss_group, scale=0.95), run_time=1.4)
        self.wait(4.125) # Exactly reaches 38.325s!
