"""Show coordinator-owned stage progress and log elapsed time without client data."""

from __future__ import annotations

import logging
from time import perf_counter
from types import TracebackType
from typing import TextIO

logger = logging.getLogger(__name__)


class StageProgress:
    """Count incorporated outcomes; use a terminal bar or two plain stage summaries.

    A missing stream disables presentation while retaining stage timings in the
    run log. Output errors disable presentation without affecting notice work.
    """

    def __init__(
        self, label: str, total: int | None = None, *, stream: TextIO | None = None
    ) -> None:
        self.label = label
        self.total = total
        self.stream = stream
        self.completed = 0
        self.failed = 0
        self._started = 0.0
        self._last_refresh = 0.0
        self._width = 0
        self._terminal = False

    def __enter__(self) -> StageProgress:
        self._started = self._last_refresh = perf_counter()
        if self.stream is not None:
            try:
                self._terminal = self.stream.isatty()
            except (OSError, ValueError):
                self._disable_output()
        self._display("started")
        return self

    def advance(self, failed: bool = False) -> None:
        """Count one terminal outcome after the coordinator incorporates it."""
        self.completed += 1
        self.failed += int(failed)
        self.refresh()

    def refresh(self) -> None:
        """Refresh an active terminal at most four times per second."""
        now = perf_counter()
        if self._terminal and now - self._last_refresh >= 0.25:
            self._display("running")
            self._last_refresh = now

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        state = "finished" if exc_type is None else "stopped"
        elapsed = perf_counter() - self._started
        if self.total is None:
            logger.info("%s %s; elapsed %.3fs", self.label, state, elapsed)
        else:
            logger.info(
                "%s %s: %s/%s completed, %s failed; elapsed %.3fs",
                self.label,
                state,
                self.completed,
                self.total,
                self.failed,
                elapsed,
            )
        self._display(state)

    def _display(self, state: str) -> None:
        if self.stream is None:
            return
        elapsed = perf_counter() - self._started
        counts = ""
        if self.total is not None:
            counts = f": {self.completed}/{self.total} completed, {self.failed} failed"
            if self._terminal:
                filled = 20 * self.completed // self.total if self.total else 0
                counts = f" [{'=' * filled}{' ' * (20 - filled)}]" + counts
        message = f"{self.label} {state}{counts}; elapsed {elapsed:.1f}s"
        final = state in {"finished", "stopped"}
        if self._terminal:
            self._width = max(self._width, len(message))
            message = "\r" + message.ljust(self._width) + ("\n" if final else "")
        else:
            message += "\n"
        try:
            self.stream.write(message)
            self.stream.flush()
        except (OSError, ValueError):
            self._disable_output()

    def _disable_output(self) -> None:
        self.stream = None
        self._terminal = False
        logger.warning("Progress output is unavailable; continuing without it")
