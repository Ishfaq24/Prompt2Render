from manim import *
import numpy as np

class Scene01(Scene):
    def construct(self):
        # ----------------------------------------------------
        # Visual Styling & Palette (1920x1080 16:9)
        # ----------------------------------------------------
        self.camera.background_color = "#0A0F1D"
        
        FONT_MAIN = "Segoe UI"
        COLOR_CYAN = "#00F0FF"
        COLOR_MAGENTA = "#EC4899"
        COLOR_AMBER = "#F59E0B"
        COLOR_GREEN = "#10B981"
        COLOR_RED = "#EF4444"
        COLOR_BLUE = "#3B82F6"
        COLOR_PURPLE = "#8B5CF6"
        COLOR_DARK = "#111C33"
        COLOR_BORDER = "#1E2E4A"
        COLOR_TEXT_MUTED = "#94A3B8"
        
        # ----------------------------------------------------
        # Universal Header (stays top, clear of everything)
        # ----------------------------------------------------
        badge_box = RoundedRectangle(
            corner_radius=0.1, width=2.8, height=0.42,
            color=COLOR_CYAN, fill_color=COLOR_CYAN, fill_opacity=0.15, stroke_width=1.5
        )
        badge_txt = Text("PART 01  •  THE ILLUSION", font=FONT_MAIN, font_size=11, color=COLOR_CYAN, weight="BOLD").move_to(badge_box)
        badge = VGroup(badge_box, badge_txt).to_corner(UL, buff=0.45)
        
        title_txt = Text("The Illusion of Contiguous Memory", font=FONT_MAIN, font_size=22, color=WHITE, weight="BOLD")
        title_txt.next_to(badge, RIGHT, buff=0.35)
        
        div_line = Line(LEFT * 6.8, RIGHT * 6.8, stroke_color="#1E293B", stroke_width=1.5)
        div_line.to_edge(UP, buff=0.95)
        
        header = VGroup(badge, title_txt, div_line)
        self.play(FadeIn(header, shift=DOWN * 0.15), run_time=0.8)

        # ----------------------------------------------------
        # Sentence 0 & 1: Two Isolated Process Universes
        # (0.8s - 13.2s)
        # ----------------------------------------------------
        def create_process_card(name, pid, accent_color, segments, x_pos):
            card = RoundedRectangle(
                corner_radius=0.14, width=5.7, height=2.1,
                color=accent_color, fill_color=COLOR_DARK, fill_opacity=0.92, stroke_width=2
            )
            top_bar = RoundedRectangle(
                corner_radius=0.14, width=5.7, height=0.5,
                color=accent_color, fill_color=accent_color, fill_opacity=0.25, stroke_width=0
            ).move_to(card.get_top() + DOWN * 0.25)
            
            p_name = Text(name, font=FONT_MAIN, font_size=12, color=WHITE, weight="BOLD").move_to(top_bar.get_left() + RIGHT * 1.5)
            p_pid = Text(f"PID: {pid}", font=FONT_MAIN, font_size=11, color=accent_color, weight="BOLD").move_to(top_bar.get_right() + LEFT * 0.8)
            
            addr_label = Text("Virtual Memory: 0x0000_0000 -> 0xFFFF_FFFF (4 GB)", font=FONT_MAIN, font_size=10, color=COLOR_TEXT_MUTED)
            addr_label.next_to(top_bar, DOWN, buff=0.18)
            
            # Contiguous memory bar
            bar_bg = Rectangle(width=5.1, height=0.5, color="#1E2E4A", fill_color="#0A1120", fill_opacity=1, stroke_width=1.5)
            bar_bg.next_to(addr_label, DOWN, buff=0.15)
            
            seg_group = VGroup()
            w_total = 5.1
            x_cursor = bar_bg.get_left()[0]
            
            for seg_title, frac, seg_col in segments:
                w = w_total * frac
                s_box = Rectangle(width=w, height=0.5, color=seg_col, fill_color=seg_col, fill_opacity=0.45, stroke_width=1.2)
                s_box.move_to(np.array([x_cursor + w/2, bar_bg.get_center()[1], 0]))
                s_txt = Text(seg_title, font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(s_box)
                seg_group.add(VGroup(s_box, s_txt))
                x_cursor += w
                
            full_card = VGroup(card, top_bar, p_name, p_pid, addr_label, bar_bg, seg_group)
            full_card.move_to(np.array([x_pos, 1.25, 0]))
            return full_card

        proc_a = create_process_card(
            "Process A: Text Editor", 1042, COLOR_CYAN,
            [("Code: 0x0040", 0.30, COLOR_CYAN), ("Heap: Dynamic", 0.40, COLOR_BLUE), ("Stack: Top", 0.30, "#38BDF8")],
            -3.5
        )
        
        proc_b = create_process_card(
            "Process B: 3D Game", 4890, COLOR_MAGENTA,
            [("Code: 0x0040", 0.30, COLOR_MAGENTA), ("Textures & Mesh", 0.45, COLOR_PURPLE), ("Physics Stack", 0.25, "#F43F5E")],
            3.5
        )

        self.play(FadeIn(proc_a, shift=RIGHT * 0.4), run_time=2.2)
        self.play(FadeIn(proc_b, shift=LEFT * 0.4), run_time=2.2)
        
        # Center illusion callout
        illusion_pill = RoundedRectangle(
            corner_radius=0.1, width=6.2, height=0.48,
            color=COLOR_AMBER, fill_color="#271802", fill_opacity=0.9, stroke_width=1.5
        ).move_to(np.array([0, -0.6, 0]))
        illusion_txt = Text("Linear, Clean, Contiguous 0 -> 4 GB Virtual Space", font=FONT_MAIN, font_size=12, color=COLOR_AMBER, weight="BOLD").move_to(illusion_pill)
        illusion_group = VGroup(illusion_pill, illusion_txt)
        
        self.play(FadeIn(illusion_group, scale=0.9), run_time=1.4)
        self.wait(5.8) # Reach ~12.4s (Sentence 1 ends at 13.18s)
        self.play(FadeOut(illusion_group), run_time=0.8) # 13.2s

        # ----------------------------------------------------
        # Sentence 2: Physical RAM Reality (Deeply Fragmented)
        # (13.2s - 19.7s)
        # ----------------------------------------------------
        # Move Process cards up slightly to make room
        self.play(
            proc_a.animate.scale(0.85).move_to(np.array([-3.5, 1.65, 0])),
            proc_b.animate.scale(0.85).move_to(np.array([3.5, 1.65, 0])),
            run_time=1.0
        )
        
        # Physical DRAM Board at bottom (centered at y = -1.6)
        ram_frame = RoundedRectangle(
            corner_radius=0.15, width=12.2, height=1.55,
            color="#334155", fill_color="#080F1E", fill_opacity=0.95, stroke_width=2
        ).move_to(np.array([0, -1.6, 0]))
        
        ram_header_bar = RoundedRectangle(
            corner_radius=0.1, width=12.2, height=0.38,
            color="#334155", fill_color="#1E293B", fill_opacity=0.7, stroke_width=0
        ).move_to(ram_frame.get_top() + DOWN * 0.19)
        
        ram_title = Text("PHYSICAL RAM HARDWARE (8 GB DDR5 DRAM)", font=FONT_MAIN, font_size=10, color=COLOR_AMBER, weight="BOLD").move_to(ram_header_bar.get_left() + RIGHT * 2.8)
        ram_badge = Text("Brutally Finite & Heavily Shared", font=FONT_MAIN, font_size=9, color=COLOR_TEXT_MUTED).move_to(ram_header_bar.get_right() + LEFT * 2.0)
        
        # 8 Physical Frame slots
        frames_group = VGroup()
        frame_status = [
            ("Frame 0", "OS Kernel", "#334155", WHITE),
            ("Frame 1", "Sys Services", "#334155", COLOR_TEXT_MUTED),
            ("Frame 2", "Empty Slot", "#0F1A2E", "#64748B"),
            ("Frame 3", "Web Browser", "#334155", COLOR_TEXT_MUTED),
            ("Frame 4", "Empty Slot", "#0F1A2E", "#64748B"),
            ("Frame 5", "Empty Slot", "#0F1A2E", "#64748B"),
            ("Frame 6", "Audio Daemon", "#334155", COLOR_TEXT_MUTED),
            ("Frame 7", "Empty Slot", "#0F1A2E", "#64748B")
        ]
        
        slot_w = 1.35
        for i, (f_num, f_owner, col_fill, col_txt) in enumerate(frame_status):
            slot_box = RoundedRectangle(
                corner_radius=0.08, width=slot_w, height=0.85,
                color="#293952", fill_color=col_fill, fill_opacity=0.9, stroke_width=1.2
            )
            slot_t1 = Text(f_num, font=FONT_MAIN, font_size=9, color=COLOR_AMBER, weight="BOLD").move_to(slot_box.get_top() + DOWN * 0.2)
            slot_t2 = Text(f_owner, font=FONT_MAIN, font_size=8, color=col_txt).move_to(slot_box.get_bottom() + UP * 0.22)
            f_group = VGroup(slot_box, slot_t1, slot_t2)
            frames_group.add(f_group)
            
        frames_group.arrange(RIGHT, buff=0.12).move_to(ram_frame.get_center() + DOWN * 0.14)
        ram_full = VGroup(ram_frame, ram_header_bar, ram_title, ram_badge, frames_group)

        self.play(FadeIn(ram_full, shift=UP * 0.3), run_time=2.2)
        self.wait(3.3) # Reach 19.7s (Sentence 2 ends at 19.69s)

        # ----------------------------------------------------
        # Sentence 3: Direct Addressing Disaster (Data Collision)
        # (19.7s - 27.3s)
        # ----------------------------------------------------
        slot_2 = frames_group[2]
        target_pt = slot_2.get_top()
        
        p1_label = Text("Write: 0x0040", font=FONT_MAIN, font_size=10, color=COLOR_CYAN, weight="BOLD").next_to(proc_a, DOWN, buff=0.15)
        p2_label = Text("Write: 0x0040", font=FONT_MAIN, font_size=10, color=COLOR_MAGENTA, weight="BOLD").next_to(proc_b, DOWN, buff=0.15)
        
        line1 = Arrow(start=p1_label.get_bottom(), end=target_pt + LEFT * 0.15, color=COLOR_CYAN, stroke_width=2.5, tip_length=0.16)
        line2 = Arrow(start=p2_label.get_bottom(), end=target_pt + RIGHT * 0.15, color=COLOR_MAGENTA, stroke_width=2.5, tip_length=0.16)
        
        self.play(
            FadeIn(p1_label), FadeIn(p2_label),
            Create(line1), Create(line2),
            run_time=2.0
        )
        
        # Explosion / Collision at Slot 2
        collision_box = SurroundingRectangle(slot_2, color=COLOR_RED, buff=0.06, stroke_width=3.0)
        collision_txt = Text("COLLISION!", font=FONT_MAIN, font_size=9, color=COLOR_RED, weight="BOLD").next_to(slot_2, UP, buff=0.08)
        
        self.play(
            Create(collision_box),
            FadeIn(collision_txt, scale=1.2),
            run_time=1.2
        )
        
        warning_banner = RoundedRectangle(
            corner_radius=0.1, width=8.8, height=0.45,
            color=COLOR_RED, fill_color="#3B0D0D", fill_opacity=0.95, stroke_width=2
        ).move_to(np.array([0, 0.05, 0]))
        warning_txt = Text("DIRECT ACCESS DISASTER: TWO PROCESSES CORRUPT SAME RAM BYTES!", font=FONT_MAIN, font_size=10, color=WHITE, weight="BOLD").move_to(warning_banner)
        warning_group = VGroup(warning_banner, warning_txt)
        
        self.play(FadeIn(warning_group, shift=DOWN * 0.1), run_time=1.0)
        self.wait(3.4) # Reach 27.3s (Sentence 3 ends at 27.31s)

        # ----------------------------------------------------
        # Sentence 4: The Virtual Memory Abstraction Solution
        # (27.3s - 34.76s)
        # ----------------------------------------------------
        self.play(
            FadeOut(line1), FadeOut(line2),
            FadeOut(p1_label), FadeOut(p2_label),
            FadeOut(collision_box), FadeOut(collision_txt),
            FadeOut(warning_group),
            run_time=0.8
        )
        
        # Introduce Virtual Memory Layer in middle (y = 0.05)
        vm_layer = RoundedRectangle(
            corner_radius=0.12, width=12.2, height=0.58,
            color=COLOR_GREEN, fill_color="#062E20", fill_opacity=0.92, stroke_width=2
        ).move_to(np.array([0, 0.05, 0]))
        vm_txt = Text("VIRTUAL MEMORY ABSTRACTION (Hardware MMU + OS Page Tables)", font=FONT_MAIN, font_size=11, color=COLOR_GREEN, weight="BOLD").move_to(vm_layer)
        vm_group = VGroup(vm_layer, vm_txt)
        
        self.play(FadeIn(vm_group, scale=0.95), run_time=1.4)
        
        # New safe routed arrows
        slot_5 = frames_group[5]
        
        safe_arrow_a = Arrow(
            start=proc_a.get_bottom() + DOWN * 0.05,
            end=slot_2.get_top(),
            color=COLOR_CYAN, stroke_width=3, tip_length=0.16
        )
        safe_arrow_b = Arrow(
            start=proc_b.get_bottom() + DOWN * 0.05,
            end=slot_5.get_top(),
            color=COLOR_MAGENTA, stroke_width=3, tip_length=0.16
        )
        
        # Update slot 2 and slot 5
        slot_2_new = RoundedRectangle(
            corner_radius=0.08, width=slot_w, height=0.85,
            color=COLOR_CYAN, fill_color="#0A2C42", fill_opacity=0.95, stroke_width=2
        ).move_to(slot_2)
        slot_2_txt = Text("Process A\nFrame 2", font=FONT_MAIN, font_size=8, color=COLOR_CYAN, weight="BOLD").move_to(slot_2_new)
        slot_2_group = VGroup(slot_2_new, slot_2_txt)
        
        slot_5_new = RoundedRectangle(
            corner_radius=0.08, width=slot_w, height=0.85,
            color=COLOR_MAGENTA, fill_color="#3E0E2C", fill_opacity=0.95, stroke_width=2
        ).move_to(slot_5)
        slot_5_txt = Text("Process B\nFrame 5", font=FONT_MAIN, font_size=8, color=COLOR_MAGENTA, weight="BOLD").move_to(slot_5_new)
        slot_5_group = VGroup(slot_5_new, slot_5_txt)
        
        self.play(
            Create(safe_arrow_a),
            Create(safe_arrow_b),
            Transform(slot_2, slot_2_group),
            Transform(slot_5, slot_5_group),
            run_time=2.2
        )
        
        # Success Badge placed directly below VM layer at y = -0.5 (above RAM frame at y = -0.825)
        success_badge = RoundedRectangle(
            corner_radius=0.08, width=9.2, height=0.38,
            color=COLOR_GREEN, fill_color="#022115", fill_opacity=0.95, stroke_width=1.5
        ).move_to(np.array([0, -0.48, 0]))
        success_txt = Text("COMPLETE ISOLATION: Same Virtual Address 0x0040 -> Separate Physical Frames!", font=FONT_MAIN, font_size=9, color=WHITE, weight="BOLD").move_to(success_badge)
        success_group = VGroup(success_badge, success_txt)
        
        self.play(FadeIn(success_group, shift=UP * 0.08), run_time=1.0)
        self.wait(2.06) # Exactly reaches 34.762s!
