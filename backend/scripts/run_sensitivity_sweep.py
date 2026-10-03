"""Jalankan sensitivity sweep dari scenario catalog via endpoint MC.

Jalankan dari backend/ setelah server menyala:
    ./venv/Scripts/python.exe scripts/run_sensitivity_sweep.py
"""

import csv
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.sensitivity_plan import (
    build_sensitivity_requests,
    extract_summary_row,
    write_summary,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "results" / "scenario_catalog.csv"
OUTPUT = ROOT / "results" / "sensitivity_summary.csv"
RAW_DIR = ROOT / "backend" / "result"
ENDPOINT = "http://127.0.0.1:8000/api/rute/monte-carlo"


def _load_catalog() -> list[dict]:
    with CATALOG.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _post(request_body: dict) -> dict:
    payload = json.dumps(request_body).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=1800) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach {ENDPOINT}: {error.reason}") from error


def main() -> int:
    if not CATALOG.exists():
        print(f"FATAL: {CATALOG} tidak ada. Jalankan scripts/screen_scenarios.py dulu.",
              file=sys.stderr)
        return 2

    rows = _load_catalog()
    plans = build_sensitivity_requests(rows, replications=500)
    summaries: list[dict] = []
    for index, plan in enumerate(plans, 1):
        label = plan["label"]
        print(f"[{index}/{len(plans)}] {label}")
        try:
            result = _post(plan["request_body"])
        except RuntimeError as error:
            print(f"  FAILED: {error}", file=sys.stderr)
            continue
        raw_path = RAW_DIR / f"monte_carlo_raw_{label}.json"
        raw_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        summary = extract_summary_row(plan, result)
        summaries.append(summary)
        print(
            f"  divergence={summary['divergence_rate']} "
            f"mean_delta={summary['mean_density_delta']} "
            f"extra_min={summary['mean_extra_time_minutes']}"
        )

    write_summary(summaries, OUTPUT)
    print(f"\nSaved: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
