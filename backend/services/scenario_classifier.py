"""Scenario typing untuk routing sensitivity.

OD pairs diklasifikasikan menjadi empat tipe konflik sehingga Monte Carlo
tidak lagi "semua skenario ternyata no-alt". Tipe mengikuti dokumen evaluasi:

    A = congruent   : kandidat hanya 1 koridor unik, atau perbedaan kepadatan
                      antar kandidat kecil (kedua metode sepakat).
    B = mild conflict: >= 2 urutan koridor unik, kepadatan alternatif lebih
                      rendah 0.10-0.30 dari rute terbaik fase 1.
    C = severe conflict: >= 2 urutan koridor unik, kepadatan alternatif lebih
                      rendah > 0.30 dari rute terbaik fase 1.
    D = no-alt      : tidak ada alternatif yang valid (kandidat < 2).

Klasifikasi dihitung dari hasil dijkstra(k=5) pada satu snapshot deterministik.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from services.dijkstra import KANDIDAT_RUTE_DEFAULT, build_graph, dijkstra

DENSITY_DELTA_MILD = 0.10
DENSITY_DELTA_SEVERE = 0.30

FIELDNAMES = [
    "scenario_type", "origin", "destination", "time_period",
    "candidate_count", "unique_corridor_sequences",
    "best_density", "best_alternative_density", "density_delta",
    "best_time_minutes", "best_alternative_time_minutes",
    "time_penalty_minutes", "best_route", "alternative_route",
]


def _koridor_sequences(routes: list[dict]) -> list[tuple]:
    sequences: list[tuple] = []
    for route in routes:
        seq = tuple(
            edge.get("koridor_id")
            for edge in route.get("path", [])
            if edge.get("tipe") == "segmen"
        )
        if seq and seq not in sequences:
            sequences.append(seq)
    return sequences


def _route_text(route: dict | None) -> str:
    if not route or not route.get("path"):
        return ""
    nodes = [str(route["path"][0].get("asal"))]
    nodes.extend(str(edge.get("tujuan")) for edge in route["path"])
    return " -> ".join(nodes)


def _seq_for_route(route: dict) -> tuple:
    return tuple(
        edge.get("koridor_id")
        for edge in route.get("path", [])
        if edge.get("tipe") == "segmen"
    )


def classify_routes(routes: list[dict]) -> dict:
    """Klasifikasi satu set kandidat rute (hasil dijkstra k=5)."""
    if len(routes) < 2:
        return {
            "scenario_type": "D",
            "reason": "no alternative candidate",
            "unique_corridor_sequences": len(_koridor_sequences(routes)),
        }

    sequences = _koridor_sequences(routes)
    if len(sequences) < 2:
        return {
            "scenario_type": "A",
            "reason": "only one unique corridor sequence",
            "unique_corridor_sequences": len(sequences),
        }

    best = routes[0]
    best_seq = _seq_for_route(best)
    alternatives = [r for r in routes[1:] if _seq_for_route(r) != best_seq]
    if not alternatives:
        return {
            "scenario_type": "A",
            "reason": "no structurally different alternative",
            "unique_corridor_sequences": len(sequences),
        }

    best_density = float(best.get("rata_kepadatan", 0.0))
    best_alt = min(alternatives, key=lambda r: float(r.get("rata_kepadatan", 0.0)))
    best_alt_density = float(best_alt.get("rata_kepadatan", 0.0))
    delta = best_density - best_alt_density

    if delta > DENSITY_DELTA_SEVERE:
        scenario_type = "C"
    elif delta >= DENSITY_DELTA_MILD:
        scenario_type = "B"
    else:
        scenario_type = "A"

    return {
        "scenario_type": scenario_type,
        "reason": f"density_delta={delta:.3f}",
        "unique_corridor_sequences": len(sequences),
        "best_density": best_density,
        "best_alternative_density": best_alt_density,
        "density_delta": delta,
        "best_time_minutes": round(float(best.get("total_waktu_detik", 0.0)) / 60, 3),
        "best_alternative_time_minutes": round(float(best_alt.get("total_waktu_detik", 0.0)) / 60, 3),
        "time_penalty_minutes": round(
            (float(best_alt.get("total_waktu_detik", 0.0)) - float(best.get("total_waktu_detik", 0.0))) / 60,
            3,
        ),
        "best_route": _route_text(best),
        "alternative_route": _route_text(best_alt),
    }


def classify_od_pair(
    graph_data: dict[str, Any],
    origin: str,
    destination: str,
    jam: int,
    hari_tipe: str,
) -> dict:
    """Bangun graph untuk (jam, hari_tipe), jalankan dijkstra(k=5), klasifikasi."""
    graph = build_graph(graph_data, jam=jam, hari_tipe=hari_tipe)
    routes = dijkstra(
        graph,
        origin,
        destination,
        k=KANDIDAT_RUTE_DEFAULT,
    )
    result = classify_routes(routes)
    result["candidate_count"] = len(routes)
    result["origin"] = origin
    result["destination"] = destination
    result["time_period"] = f"{jam:02d}h00"
    return result


def build_screening_pairs(graph_data: dict[str, Any]) -> list[dict]:
    """Bangun daftar pasangan OD kandidat dari koridor scope 1-5.

    Untuk menjaga waktu screening tetap terkendali, tiap koridor diambil
    maksimal 16 halte (stride). Pairs = kombinasi dalam koridor yang sama,
    dibatasi sampai 12 pasangan per koridor.
    """
    members: dict[str, list[str]] = defaultdict(list)
    for row in graph_data.get("koridor_halte", []):
        kid = str(row.get("koridor_id"))
        if kid in {"1", "2", "3", "4", "5"}:
            members[kid].append(str(row.get("halte_id")))

    pairs: list[dict] = []
    for kid in sorted(members):
        unique = list(dict.fromkeys(members[kid]))
        if len(unique) < 3:
            continue
        sampled = unique[:: max(1, len(unique) // 16)]
        count = 0
        for left_index in range(0, len(sampled) - 2):
            for right_index in range(left_index + 2, len(sampled)):
                pairs.append({"origin": sampled[left_index], "destination": sampled[right_index]})
                count += 1
                if count >= 12:
                    break
            if count >= 12:
                break
    return pairs


def write_catalog(rows: list[dict], path: str | Path) -> None:
    """Tulis catalog skenario ke CSV (overwrite)."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


# ----------------------------------------------------------------------
# Bus-level scenario classification (Part B / masalah #6)
# ----------------------------------------------------------------------

BUS_CROWDED_THRESHOLD = 0.80   # padat (c251 §4.2: 0.80 <= LF < 1.00)
BUS_EMPTY_THRESHOLD = 0.35     # sepi (c251 §4.2: LF < 0.50; threshold aman repo)
BUS_DELTA_SIMILAR = 0.15       # |Δρ| di bawah ini dianggap "semua mirip"


def classify_bus_level(bus_candidates: list[dict]) -> dict:
    """Klasifikasi konflik di level bus untuk satu blok 'naik'.

    bus_candidates: list berisi dict {bus_id, eta_menit, kepadatan} hasil
    penyaringan jendela tunggu oleh bus_selector (kandidat_layak).

    Return:
        scenario_type: "B'" (bus-conflict), "C'" (bus-severe), atau "D'"
            (no-bus-alt / negative control).
        reason + metrik pendukung.
    """
    if len(bus_candidates) < 2:
        return {"scenario_type": "D'", "reason": "kurang dari 2 kandidat bus"}

    earliest = min(bus_candidates, key=lambda b: b["eta_menit"])
    earliest_density = float(earliest["kepadatan"])
    others = [b for b in bus_candidates if b is not earliest]

    later_emptier = [
        b for b in others
        if float(b["kepadatan"]) <= BUS_EMPTY_THRESHOLD
        and float(b["kepadatan"]) < earliest_density
    ]

    if earliest_density >= BUS_CROWDED_THRESHOLD and later_emptier:
        best_alt = min(later_emptier, key=lambda b: float(b["kepadatan"]))
        best_alt_density = float(best_alt["kepadatan"])
        delta = round(earliest_density - best_alt_density, 3)
        severe = earliest_density >= BUS_CROWDED_THRESHOLD and delta >= 0.50
        return {
            "scenario_type": "C'" if severe else "B'",
            "reason": (
                f"bus tercepat padat ({earliest_density:.2f}), "
                f"alternatif sepi ({best_alt_density:.2f}) dalam jendela"
            ),
            "earliest_bus_density": earliest_density,
            "later_bus_density": best_alt_density,
            "density_delta": delta,
            "earliest_eta_menit": earliest["eta_menit"],
            "later_eta_menit": best_alt["eta_menit"],
            "wait_menit": best_alt["eta_menit"] - earliest["eta_menit"],
        }

    all_densities = [float(b["kepadatan"]) for b in bus_candidates]
    spread = round(max(all_densities) - min(all_densities), 3)
    if spread < BUS_DELTA_SIMILAR:
        return {
            "scenario_type": "D'",
            "reason": f"semua kandidat bus mirip (spread={spread:.3f})",
            "spread_density": spread,
        }

    return {
        "scenario_type": "D'",
        "reason": "tidak ada konflik bus tercepat-padat vs bus-sepi dalam jendela",
        "earliest_bus_density": earliest_density,
        "spread_density": spread,
    }
