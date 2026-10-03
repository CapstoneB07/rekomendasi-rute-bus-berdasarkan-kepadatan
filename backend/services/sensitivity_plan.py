"""Builder request MC per tipe skenario × bobot density."""

from __future__ import annotations

import csv
from pathlib import Path

WEIGHT_SWEEPS = [
    {"label": "w020", "weights": {"time": 0.35, "distance": 0.25, "transfer": 0.20, "density": 0.20}},
    {"label": "w040", "weights": {"time": 0.30, "distance": 0.20, "transfer": 0.10, "density": 0.40}},
    {"label": "w060", "weights": {"time": 0.25, "distance": 0.10, "transfer": 0.05, "density": 0.60}},
    {"label": "w080", "weights": {"time": 0.15, "distance": 0.05, "transfer": 0.00, "density": 0.80}},
]

SCENARIO_TYPE_ORDER = ["A", "B", "C", "D"]

SUMMARY_FIELDNAMES = [
    "weight_label", "scenario_type", "origin", "destination", "time_period",
    "replications", "divergence_rate", "route_change_rate",
    "mean_density_delta", "median_density_delta",
    "p05_density_delta", "p95_density_delta",
    "mean_extra_time_minutes", "improvement_rate",
    "baseline_density_mean", "recommended_density_mean",
]


def _as_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_sensitivity_requests(catalog_rows: list[dict], replications: int = 500) -> list[dict]:
    """Pilih max 2 OD per tipe skenario (prioritas delta terbesar) dan buat request MC."""
    selected: dict[str, list[dict]] = {}
    for row in catalog_rows:
        scenario_type = row.get("scenario_type")
        if scenario_type not in SCENARIO_TYPE_ORDER:
            continue
        bucket = selected.setdefault(scenario_type, [])
        if len(bucket) < 2:
            bucket.append(row)
        elif _as_float(row.get("density_delta")) > _as_float(bucket[-1].get("density_delta")):
            bucket[-1] = row
        bucket.sort(key=lambda r: -_as_float(r.get("density_delta")))

    requests: list[dict] = []
    for scenario_type in SCENARIO_TYPE_ORDER:
        for row in selected.get(scenario_type, []):
            hour = int(str(row.get("time_period", "08h00")).split("h")[0])
            for sweep in WEIGHT_SWEEPS:
                requests.append({
                    "request_body": {
                        "tanggal": row.get("tanggal", "2026-02-28"),
                        "jam": hour,
                        "hari_tipe": "weekday",
                        "sim_time": hour * 3600,
                        "master_seed": 12345,
                        "replications": replications,
                        "weights": sweep["weights"],
                        "routing_scenarios": [{
                            "name": f"{scenario_type}-{row['origin']}-{row['destination']}",
                            "halte_asal": row["origin"],
                            "halte_tujuan": row["destination"],
                        }],
                    },
                    "label": f"{row.get('time_period')}_{scenario_type}_{row['origin']}_{row['destination']}_{sweep['label']}",
                    "weight_label": sweep["label"],
                    "scenario_type": scenario_type,
                    "origin": row["origin"],
                    "destination": row["destination"],
                    "time_period": row.get("time_period"),
                })
    return requests


def extract_summary_row(plan: dict, result: dict) -> dict:
    """Ambil ringkasan satu run MC menjadi satu baris CSV."""
    scenario = (result.get("routing_sensitivity") or {}).get("scenarios", [{}])[0]
    paired = scenario.get("paired_comparison") or {}
    mean_extra = paired.get("mean_extra_time_seconds")
    return {
        "weight_label": plan["weight_label"],
        "scenario_type": plan["scenario_type"],
        "origin": plan["origin"],
        "destination": plan["destination"],
        "time_period": plan["time_period"],
        "replications": len(scenario.get("replications", [])),
        "divergence_rate": paired.get("route_change_rate"),
        "route_change_rate": paired.get("route_change_rate"),
        "mean_density_delta": paired.get("mean_density_delta"),
        "median_density_delta": paired.get("median_density_delta"),
        "p05_density_delta": paired.get("p05_density_delta"),
        "p95_density_delta": paired.get("p95_density_delta"),
        "mean_extra_time_minutes": (
            round(mean_extra / 60.0, 3) if mean_extra is not None else None
        ),
        "improvement_rate": paired.get("improvement_rate"),
        "baseline_density_mean": scenario.get("baseline_density_mean"),
        "recommended_density_mean": scenario.get("recommended_density_mean"),
    }


def write_summary(rows: list[dict], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SUMMARY_FIELDNAMES})
