"""Centralised logging setup.

Each entry point (daemon, CLI, settings GUI) calls :func:`configure`
once at startup. When run under systemd the journald handler picks up
structured priorities automatically; otherwise we fall back to plain
stderr.
"""

from __future__ import annotations

import logging
import os
import sys


def configure(level: str = "INFO", *, component: str = "mx4") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    fmt = "%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = []

    # Prefer journald when available + running under systemd
    if os.environ.get("JOURNAL_STREAM") or os.environ.get("INVOCATION_ID"):
        try:
            from systemd.journal import JournalHandler  # type: ignore[import-not-found]
            handlers.append(
                JournalHandler(SYSLOG_IDENTIFIER=component)
            )
        except ImportError:
            pass

    if not handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        handlers.append(h)

    logging.basicConfig(
        level=log_level, handlers=handlers, force=True,
    )

    # Less-noisy defaults for chatty third-party loggers
    logging.getLogger("PIL").setLevel(logging.WARNING)
