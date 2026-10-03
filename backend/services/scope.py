"""Kompatibilitas: cakupan koridor kini hidup di `services/config.py`.

Modul ini dulu berisi definisi `SCOPED_KORIDOR`. Sekarang hanya meneruskan
dari `config.py` supaya import lama (`from services.scope import ...`) tidak
putus. Kode baru sebaiknya mengimpor dari `services.config`.
"""

from __future__ import annotations

from services.config import (  # noqa: F401
    DEFAULT_SCOPED_KORIDOR,
    SCOPED_KORIDOR,
    describe,
    is_scoped,
    normalize_koridor_id,
    scoped_sorted,
)

__all__ = [
    "DEFAULT_SCOPED_KORIDOR",
    "SCOPED_KORIDOR",
    "describe",
    "is_scoped",
    "normalize_koridor_id",
    "scoped_sorted",
]

