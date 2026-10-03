"""Test env-override tunable lapisan bus (pola sama dengan SCOPED_KORIDOR).

Konstanta config dibaca sekali saat import, jadi override diuji lewat
subprocess — cara yang sama dengan scripts/sweep_success_config.py. Ini juga
kebal terhadap .env yang di-load pytest secara transitif (supabase_client),
yang akan membuat reload in-process tidak deterministik.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
BUS_ENV_NAMES = (
    "BUS_MAX_EXTRA_WAIT_MENIT",
    "BUS_MAX_ETA_MENIT",
    "BUS_SCORE_DENSITY_WEIGHT",
    "BUS_SAFE_NEXT_DENSITY_THRESHOLD",
)
PRINT_CODE = (
    "import services.config as c; "
    "print(c.MAX_EXTRA_WAIT_MENIT, c.MAX_ETA_MENIT, "
    "c.BUS_SCORE_DENSITY_WEIGHT, c.BUS_SCORE_WAIT_WEIGHT, "
    "c.BUS_SAFE_NEXT_DENSITY_THRESHOLD)"
)


def _run_config_print(overrides: dict[str, str]) -> str:
    env = {key: value for key, value in os.environ.items() if key not in BUS_ENV_NAMES}
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", PRINT_CODE],
        capture_output=True, text=True, env=env, cwd=BACKEND_DIR,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_bus_layer_defaults():
    assert _run_config_print({}) == "20 45 0.85 0.15 0.35"


def test_bus_layer_env_overrides():
    out = _run_config_print({
        "BUS_MAX_EXTRA_WAIT_MENIT": "30",
        "BUS_MAX_ETA_MENIT": "60",
        "BUS_SCORE_DENSITY_WEIGHT": "0.95",
        "BUS_SAFE_NEXT_DENSITY_THRESHOLD": "0.0",
    })
    assert out == "30 60 0.95 0.05 0.0"


def test_bus_layer_invalid_env_falls_back():
    out = _run_config_print({
        "BUS_MAX_EXTRA_WAIT_MENIT": "abc",
        "BUS_SCORE_DENSITY_WEIGHT": "1.5",  # di luar [0, 1]
    })
    assert out == "20 45 0.85 0.15 0.35"


def test_bus_selector_reexports_config_values():
    import services.bus_selector as selector
    import services.config as config

    assert selector.MAX_EXTRA_WAIT_MENIT_DEFAULT == config.MAX_EXTRA_WAIT_MENIT
    assert selector.MAX_ETA_MENIT_DEFAULT == config.MAX_ETA_MENIT
    assert selector.BUS_SCORE_DENSITY_WEIGHT == config.BUS_SCORE_DENSITY_WEIGHT
