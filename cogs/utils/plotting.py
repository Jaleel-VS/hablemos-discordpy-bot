"""Shared matplotlib/seaborn setup helpers.

This module intentionally does **not** import ``matplotlib`` at module
level so that merely importing it at bot startup costs nothing. Callers
(chart helper modules) call :func:`configure_backend` once inside their
render function, then lazy-import ``matplotlib.pyplot`` and ``seaborn``.

Keeping backend selection in one place prevents the common footgun where
two independent helpers each try to ``matplotlib.use(...)`` — the second
call becomes a no-op on some backends and you get obscure "Cannot load
backend" errors in containers without a display.
"""
from __future__ import annotations

_BACKEND_CONFIGURED = False


def configure_backend() -> None:
    """Force the non-interactive Agg backend exactly once per process.

    Must run **before** ``matplotlib.pyplot`` is imported anywhere.
    Idempotent: subsequent calls are no-ops.
    """
    global _BACKEND_CONFIGURED
    if _BACKEND_CONFIGURED:
        return
    import matplotlib
    matplotlib.use("Agg", force=True)
    _BACKEND_CONFIGURED = True
