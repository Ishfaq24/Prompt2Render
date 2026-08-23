"""Terminal progress UI for the Prompt2Render Harness.

Consumes the canonical EventBus events:

    stage.started
    stage.failed
    check.failed
    repair.triggered

The UI is observational only. It never changes SceneContext or pipeline
control flow and is safe to disable automatically when stdout is not a TTY.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from typing import Any

from .events import Event, EventBus


class HarnessProgressUI:
    """Live terminal progress display for a harness execution."""

    SPINNER = (
        "⠋",
        "⠙",
        "⠹",
        "⠸",
        "⠼",
        "⠴",
        "⠦",
        "⠧",
        "⠇",
        "⠏",
    )

    def __init__(
        self,
        total_stages: int,
    ) -> None:
        self.total_stages = max(
            0,
            int(total_stages),
        )

        self.current_stage_idx = 0
        self.current_stage_name = "initializing"
        self.current_detail = ""

        self.active_repairs = 0
        self.total_repairs = 0

        self.start_time = time.monotonic()
        self.spinner_idx = 0

        self._lock = threading.RLock()
        self._running = False
        self._attached = False
        self._thread: threading.Thread | None = None

        # Do not emit ANSI/control sequences when output is redirected.
        self._interactive = bool(
            sys.stdout.isatty()
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach(
        self,
        bus: EventBus,
    ) -> None:
        """Subscribe to harness events and start the refresh thread."""

        if self._attached:
            return

        self._attached = True

        bus.subscribe(
            "stage.started",
            self._on_stage_started,
        )

        bus.subscribe(
            "stage.failed",
            self._on_stage_failed,
        )

        bus.subscribe(
            "check.failed",
            self._on_check_failed,
        )

        bus.subscribe(
            "repair.triggered",
            self._on_repair_triggered,
        )

        if not self._interactive:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._render_loop,
            name="prompt2render-progress",
            daemon=True,
        )

        self._thread.start()

    def stop(
        self,
    ) -> None:
        """Stop the progress renderer and clear the terminal line."""

        self._running = False

        thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(
                timeout=1.0
            )

        self._thread = None

        if self._interactive:
            self._clear_line()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_stage_started(
        self,
        event: Event,
    ) -> None:
        with self._lock:
            self.current_stage_idx += 1

            self.current_stage_name = str(
                event.payload.get(
                    "plugin",
                    "unknown",
                )
            )

            self.current_detail = ""

            self._draw()

    def _on_stage_failed(
        self,
        event: Event,
    ) -> None:
        with self._lock:
            plugin = str(
                event.payload.get(
                    "plugin",
                    self.current_stage_name,
                )
            )

            diagnostic = self._payload_text(
                event.payload,
                "diagnostics",
                "error",
                "detail",
            )

            self.current_stage_name = (
                f"{plugin} FAILED"
            )

            self.current_detail = (
                diagnostic
                or "stage failed"
            )

            self._draw()

    def _on_check_failed(
        self,
        event: Event,
    ) -> None:
        with self._lock:
            self.active_repairs += 1

            self.current_detail = (
                self._payload_text(
                    event.payload,
                    "diagnostic_message",
                    "detail",
                    "message",
                )
                or "finding detected"
            )

            self._draw()

    def _on_repair_triggered(
        self,
        event: Event,
    ) -> None:
        with self._lock:
            self.total_repairs += 1

            # The repair is now active. The counter represents currently
            # unresolved repair work rather than cumulative repair attempts.
            self.active_repairs = max(
                1,
                self.active_repairs,
            )

            scene = str(
                event.payload.get(
                    "scene_id",
                    "all",
                )
            )

            cycle = event.payload.get(
                "cycle",
                "?",
            )

            max_cycles = event.payload.get(
                "max_cycles",
                "?",
            )

            routed = event.payload.get(
                "routed_to",
                [],
            )

            if isinstance(
                routed,
                (list, tuple),
            ):
                target = ", ".join(
                    str(x)
                    for x in routed
                )
            else:
                target = str(
                    routed
                )

            self.current_stage_name = (
                f"repair Scene {scene}"
            )

            detail = (
                f"cycle {cycle}/{max_cycles}"
            )

            if target:
                detail += (
                    f" → {target}"
                )

            self.current_detail = detail

            self._draw()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_loop(
        self,
    ) -> None:
        while self._running:
            with self._lock:
                self._draw()

            # 10 FPS is sufficient for a terminal spinner and avoids
            # unnecessary CPU usage during long LLM/Manim calls.
            time.sleep(
                0.1
            )

    def _draw(
        self,
    ) -> None:
        if not self._interactive:
            return

        elapsed = max(
            0,
            int(
                time.monotonic()
                - self.start_time
            ),
        )

        minutes, seconds = divmod(
            elapsed,
            60,
        )

        hours, minutes = divmod(
            minutes,
            60,
        )

        if hours:
            time_str = (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )
        else:
            time_str = (
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        spinner = self.SPINNER[
            self.spinner_idx
            % len(self.SPINNER)
        ]

        self.spinner_idx += 1

        stage_str = (
            f"[{self.current_stage_idx:2d}/"
            f"{self.total_stages:2d}] "
            f"{spinner} "
            f"{self.current_stage_name}"
        )

        repair_str = ""

        if self.total_repairs:
            repair_str = (
                f" "
                f"\033[93m"
                f"({self.total_repairs} repairs)"
                f"\033[0m"
            )

        detail_str = ""

        if self.current_detail:
            detail_str = (
                f" | {self.current_detail}"
            )

        terminal_width = shutil.get_terminal_size(
            fallback=(120, 20)
        ).columns

        # Keep the line within the terminal width. This prevents wrapping,
        # which otherwise makes a live progress bar visually messy.
        available = max(
            20,
            terminal_width - 1,
        )

        line = (
            f"[{self.current_stage_idx:2d}/"
            f"{self.total_stages:2d}] "
            f"{spinner} "
            f"{self.current_stage_name}"
            f"{repair_str}"
            f" | {time_str}"
            f"{detail_str}"
        )

        # ANSI escape codes count toward len(), so truncate the logical
        # message before adding the clear-line control sequence.
        if len(line) > available:
            line = (
                line[: max(0, available - 1)]
                + "…"
            )

        sys.stdout.write(
            "\r\033[K"
            + line
        )

        sys.stdout.flush()

    def _clear_line(
        self,
    ) -> None:
        try:
            width = shutil.get_terminal_size(
                fallback=(120, 20)
            ).columns
        except Exception:
            width = 120

        sys.stdout.write(
            "\r"
            + (" " * max(1, width - 1))
            + "\r"
        )

        sys.stdout.flush()

    @staticmethod
    def _payload_text(
        payload: dict[str, Any],
        *keys: str,
    ) -> str:
        for key in keys:
            value = payload.get(
                key
            )

            if value is None:
                continue

            text = str(
                value
            ).strip()

            if text:
                return text

        return ""


__all__ = [
    "HarnessProgressUI",
]