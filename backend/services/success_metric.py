"""Metrik sukses skenario sistem (target 50%, c251 Eq 4.24-4.25 + Eq 4.15).

Definisi (dikunci SEBELUM pengukuran, 2026-10-03):
  D_base V1 (headline) = rata-rata load factor bus TERCEPAT pada tiap blok
      naik rute baseline (shortest path k=1, crowding-unaware). Pembacaan
      literal "tanpa pemeringkatan": tidak memakai kepadatan sama sekali.
  D_base V2 (konservatif) = baseline memakai pemilihan bus density-aware
      (memisahkan efek pemeringkatan rute saja). Dilaporkan berdampingan.
  D_rec = rata-rata load factor bus yang direkomendasikan sistem pada rute
      hasil k=5 + re-ranking (definisi Eq 4.15: rata-rata LF layanan yang
      akan dinaiki).
  menang = D_base - D_rec > DENSITY_IMPROVEMENT_TOLERANCE (0.01).

Hanya memakai API publik; tidak mengubah perilaku produksi.
"""

from __future__ import annotations

from statistics import mean

from services.bus_selector import (
    apply_selected_bus_density,
    collect_bus_candidates,
    rerank_routes,
    select_bus_per_segmen,
)
from services.dijkstra import KANDIDAT_RUTE_DEFAULT, build_graph, dijkstra, format_rute
from services.monte_carlo import (
    DENSITY_IMPROVEMENT_TOLERANCE,
    build_recommendation_crowding_snapshot,
)


def _blocks(formatted: dict) -> list[dict]:
    return [s for s in formatted.get("segmen", []) if s.get("tipe") == "naik"]


def _formatted_signature(formatted: dict) -> tuple:
    return tuple(
        (s.get("tipe"), s.get("naik_di_id"), s.get("turun_di_id"), s.get("koridor_id"))
        for s in formatted.get("segmen", [])
    )


def _earliest_bus_density(
    formatted: dict,
    jadwal: dict,
    realtime: dict,
    sim_time: int,
) -> tuple[float, int, int]:
    """V1: bus tercepat per blok naik.

    Return (rata-rata LF, jumlah blok, jumlah blok tanpa kandidat). Blok tanpa
    kandidat memakai kepadatan edge (nilai sebelum mutasi pemilihan bus).
    """
    densities: list[float] = []
    no_candidates = 0
    for blok in _blocks(formatted):
        kandidat = collect_bus_candidates(
            jadwal,
            realtime,
            blok["koridor_id"],
            blok["naik_di_id"],
            reference_time=sim_time,
        )
        if not kandidat:
            no_candidates += 1
            densities.append(float(blok.get("kepadatan", 0.0)))
            continue
        earliest = min(kandidat, key=lambda b: (b["eta_menit"], b["bus_id"]))
        densities.append(float(earliest["kepadatan"]))
    rata = sum(densities) / len(densities) if densities else 0.0
    return rata, len(densities), no_candidates


def _empty_result(origin: str, destination: str, reason: str) -> dict:
    return {
        "origin": origin,
        "destination": destination,
        "candidate_count": 0,
        "blocks": 0,
        "blocks_without_candidates": 0,
        "d_base_v1": None,
        "d_base_v2": None,
        "d_rec": None,
        "delta_v1": None,
        "delta_v2": None,
        "win_v1": False,
        "win_v2": False,
        "route_changed": False,
        "mean_extra_wait_menit": None,
        "reason": reason,
    }


def evaluate_scenario_success(
    ctx,
    graph_data: dict,
    origin: str,
    destination: str,
    jam: int,
    hari_tipe: str,
    sim_time: int,
    tanggal: str | None = None,
    tolerance: float = DENSITY_IMPROVEMENT_TOLERANCE,
) -> dict:
    snapshot = build_recommendation_crowding_snapshot(
        ctx,
        tanggal=tanggal,
        sim_time=sim_time,
        request_seed_parts=(origin, destination, jam, hari_tipe),
    )
    realtime = snapshot["realtime_kepadatan"]

    # --- Baseline: shortest path k=1, crowding-unaware.
    baseline_graph = build_graph(graph_data, jam=jam, hari_tipe=hari_tipe)
    baseline_routes = dijkstra(baseline_graph, origin, destination, k=1)
    if not baseline_routes:
        return _empty_result(origin, destination, "baseline route tidak ditemukan")
    baseline_formatted = format_rute(baseline_routes[0], graph_data)

    # V1 dihitung SEBELUM mutasi kepadatan oleh pemilihan bus.
    d_base_v1, n_blocks, n_no_candidates = _earliest_bus_density(
        baseline_formatted, ctx.jadwal, realtime, sim_time
    )
    # V2: baseline dengan pemilihan bus density-aware (konservatif).
    select_bus_per_segmen(baseline_formatted["segmen"], sim_time, ctx.jadwal, realtime)
    apply_selected_bus_density(baseline_formatted)
    d_base_v2 = float(baseline_formatted.get("rata_kepadatan", 0.0))

    # --- Rekomendasi: pipeline produksi (k=5 + re-ranking + bus density-aware).
    graph = build_graph(
        graph_data,
        jam=jam,
        hari_tipe=hari_tipe,
        segment_crowding=snapshot["segment_crowding"],
        daily_mean_by_koridor=snapshot["daily_mean_by_koridor"],
    )
    routes = dijkstra(graph, origin, destination, k=KANDIDAT_RUTE_DEFAULT)
    if not routes:
        return _empty_result(origin, destination, "rute rekomendasi tidak ditemukan")

    hasil: list[dict] = []
    for route in routes:
        formatted = format_rute(route, graph_data)
        select_bus_per_segmen(formatted["segmen"], sim_time, ctx.jadwal, realtime)
        hasil.append(apply_selected_bus_density(formatted))
    hasil = rerank_routes(hasil)
    top = hasil[0]

    d_rec = float(top.get("rata_kepadatan", 0.0))
    delta_v1 = round(d_base_v1 - d_rec, 4)
    delta_v2 = round(d_base_v2 - d_rec, 4)
    waits = [
        float(blok["bus_rekomendasi"]["extra_wait_menit"])
        for blok in _blocks(top)
        if blok.get("bus_rekomendasi")
    ]
    return {
        "origin": origin,
        "destination": destination,
        "candidate_count": len(routes),
        "blocks": n_blocks,
        "blocks_without_candidates": n_no_candidates,
        "d_base_v1": round(d_base_v1, 4),
        "d_base_v2": round(d_base_v2, 4),
        "d_rec": round(d_rec, 4),
        "delta_v1": delta_v1,
        "delta_v2": delta_v2,
        "win_v1": delta_v1 > tolerance,
        "win_v2": delta_v2 > tolerance,
        "route_changed": (
            _formatted_signature(baseline_formatted) != _formatted_signature(top)
        ),
        "mean_extra_wait_menit": round(mean(waits), 3) if waits else None,
    }


def summarize_success(
    rows: list[dict], tolerance: float = DENSITY_IMPROVEMENT_TOLERANCE
) -> dict:
    n = len(rows)
    wins_v1 = sum(1 for row in rows if row.get("win_v1"))
    wins_v2 = sum(1 for row in rows if row.get("win_v2"))
    deltas = [row["delta_v1"] for row in rows if row.get("delta_v1") is not None]
    waits = [
        row["mean_extra_wait_menit"]
        for row in rows
        if row.get("mean_extra_wait_menit") is not None
    ]
    win_waits = [
        row["mean_extra_wait_menit"]
        for row in rows
        if row.get("win_v1") and row.get("mean_extra_wait_menit") is not None
    ]
    return {
        "n": n,
        "tolerance": tolerance,
        "wins_v1": wins_v1,
        "win_rate_v1": round(wins_v1 / n, 4) if n else 0.0,
        "wins_v2": wins_v2,
        "win_rate_v2": round(wins_v2 / n, 4) if n else 0.0,
        "mean_delta_v1": round(mean(deltas), 4) if deltas else 0.0,
        "mean_extra_wait_menit": round(mean(waits), 3) if waits else 0.0,
        "mean_extra_wait_wins_v1": round(mean(win_waits), 3) if win_waits else 0.0,
    }
