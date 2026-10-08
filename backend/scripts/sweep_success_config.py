"""Sweep konfigurasi bus-layer untuk mencapai win_rate_v1 >= 0.50.

Menjalankan scripts/eval_success_rate.py sebagai subprocess per kombinasi env
(konstanta config dibaca saat import, jadi env harus di-set sebelum proses
start). Urutan COMBOS = urutan intervensi paling ringan lebih dulu.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/sweep_success_config.py --limit 5 --combos base,wait30
    ./venv/Scripts/python.exe scripts/sweep_success_config.py
Output: results/success_config_sweep.csv
"""

import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve().parent / "eval_success_rate.py"
OUTPUT = ROOT / "results" / "success_config_sweep.csv"

COMBOS = [
    ("base", {}),
    ("wait30", {"BUS_MAX_EXTRA_WAIT_MENIT": "30"}),
    ("w095", {"BUS_SCORE_DENSITY_WEIGHT": "0.95"}),
    ("wait30_w095", {"BUS_MAX_EXTRA_WAIT_MENIT": "30", "BUS_SCORE_DENSITY_WEIGHT": "0.95"}),
    ("eta60", {"BUS_MAX_ETA_MENIT": "60"}),
    ("wait40", {"BUS_MAX_EXTRA_WAIT_MENIT": "40"}),
    ("wait30_eta60_w095", {
        "BUS_MAX_EXTRA_WAIT_MENIT": "30",
        "BUS_MAX_ETA_MENIT": "60",
        "BUS_SCORE_DENSITY_WEIGHT": "0.95",
    }),
]

SUMMARY_RE = re.compile(
    r"SUMMARY n=(\d+) win_rate_v1=([\d.]+) win_rate_v2=([\d.]+) "
    r"mean_extra_wait=([\d.]+) mean_delta_v1=([-\d.]+)"
)

FIELDNAMES = [
    "combo", "env", "n", "win_rate_v1", "win_rate_v2",
    "mean_extra_wait", "mean_delta_v1", "passes_50",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--combos", default="", help="daftar nama combo, mis. base,wait30")
    args = parser.parse_args()

    wanted = {name.strip() for name in args.combos.split(",") if name.strip()}
    combos = [(name, env) for name, env in COMBOS if not wanted or name in wanted]

    rows: list[dict] = []
    for name, overrides in combos:
        env = os.environ.copy()
        env.update(overrides)
        command = [sys.executable, str(SCRIPT), "--quiet"]
        if args.limit:
            command += ["--limit", str(args.limit)]
        print(f"=== combo={name} env={overrides if overrides else '{}'} ===")
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-500:], file=sys.stderr)
            print(f"  FAILED (exit {result.returncode})", file=sys.stderr)
            continue
        match = SUMMARY_RE.search(result.stdout)
        if not match:
            print("  FAILED: SUMMARY line tidak ditemukan", file=sys.stderr)
            continue
        n, rate1, rate2, wait, delta = match.groups()
        row = {
            "combo": name,
            "env": ";".join(f"{key}={value}" for key, value in overrides.items()),
            "n": int(n),
            "win_rate_v1": float(rate1),
            "win_rate_v2": float(rate2),
            "mean_extra_wait": float(wait),
            "mean_delta_v1": float(delta),
            "passes_50": float(rate1) >= 0.50,
        }
        rows.append(row)
        print(
            f"  win_rate_v1={row['win_rate_v1']} win_rate_v2={row['win_rate_v2']} "
            f"wait={row['mean_extra_wait']} passes_50={row['passes_50']}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved: {OUTPUT}")
    if rows:
        best = max(rows, key=lambda row: (row["passes_50"], row["win_rate_v1"]))
        print(
            f"BEST combo={best['combo']} win_rate_v1={best['win_rate_v1']} "
            f"passes_50={best['passes_50']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
