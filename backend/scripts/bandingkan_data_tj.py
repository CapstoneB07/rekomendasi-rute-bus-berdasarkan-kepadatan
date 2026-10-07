"""Bandingkan data halte dan rute statis (Supabase) dengan data live MQTT TransJakarta.

Sumber live: payload MQTT anonim `/mobile_armada/#` (tiap pesan memuat daftar halte
beserta koordinat). Hanya laporan; tidak ada data yang diubah.

Output (folder --out, default laporan_tj/):
- laporan.md            ringkasan
- halte_mapping.csv     halte_id statis -> stop_id / parent_stop_id MQTT + selisih koordinat
- halte_hanya_statis.csv, rute_banding.csv

Jalankan dari folder backend/:
    ./venv/Scripts/python.exe scripts/bandingkan_data_tj.py --detik 90
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.geo import distance_meters

MQTT_HOST = "mqtt.tj.co.id"
MQTT_PORT = 8084
MQTT_TOPIC = "/mobile_armada/#"
# Selisih koordinat di atas ini dianggap tidak cocok (meter).
AMBANG_KOORDINAT_METER = 50.0


def kumpulkan_mqtt(detik: int) -> list[dict]:
    """Subscribe MQTT `detik` detik; kembalikan payload JSON terakhir per bus_body_no."""
    import paho.mqtt.client as mqtt

    terakhir: dict[str, dict] = {}

    def on_connect(client, _u, _f, rc, _p=None):
        client.subscribe(MQTT_TOPIC)

    def on_message(_c, _u, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        if isinstance(data, dict) and data.get("bus_body_no"):
            terakhir[data["bus_body_no"]] = data

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, transport="websockets", protocol=mqtt.MQTTv311
    )
    client.ws_set_options(path="/mqtt")
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    time.sleep(detik)
    client.loop_stop()
    client.disconnect()
    return list(terakhir.values())


def indeks_mqtt(payloads: list[dict]) -> tuple[dict[str, dict], dict[str, dict], dict[str, set[str]]]:
    """Return (stop_by_id, stop_by_parent, ids_per_route).

    stop_by_id: stop_id -> {name, lat, lng, parent}
    stop_by_parent: parent_stop_id -> info (stop pertama yang ditemui)
    ids_per_route: route_code -> himpunan stop_id dan parent_stop_id yang dilayani
    """
    by_id: dict[str, dict] = {}
    by_parent: dict[str, dict] = {}
    per_route: dict[str, set[str]] = defaultdict(set)
    for p in payloads:
        route = p.get("route_code") or ""
        for s in p.get("stops") or []:
            sid, parent = s.get("stop_id"), s.get("parent_stop_id")
            info = {
                "name": s.get("name") or "",
                "lat": s.get("latitude"),
                "lng": s.get("longitude"),
                "parent": parent,
            }
            if sid:
                by_id.setdefault(sid, info)
                per_route[route].add(sid)
            if parent:
                by_parent.setdefault(parent, {**info, "name": s.get("parent_stop_name") or info["name"]})
                per_route[route].add(parent)
    return by_id, by_parent, per_route


def cocokkan_halte(halte: list[dict], by_id: dict[str, dict], by_parent: dict[str, dict]) -> list[dict]:
    """Cocokkan tiap halte statis ke stop MQTT lewat stop_id, lalu parent_stop_id."""
    hasil = []
    for h in halte:
        hid = h["halte_id"]
        if hid in by_id:
            jenis, info = "stop_id", by_id[hid]
        elif hid in by_parent:
            jenis, info = "parent_stop_id", by_parent[hid]
        else:
            hasil.append({"halte_id": hid, "nama_statis": h["nama"], "cocok": "tidak_ada"})
            continue
        try:
            selisih = distance_meters(h["lat"], h["lng"], info["lat"], info["lng"])
        except (TypeError, ValueError):
            selisih = None
        hasil.append({
            "halte_id": hid,
            "nama_statis": h["nama"],
            "cocok": jenis,
            "nama_mqtt": info["name"],
            "selisih_meter": None if selisih is None else round(selisih, 1),
            "koordinat_jauh": selisih is not None and selisih > AMBANG_KOORDINAT_METER,
            "nama_beda": " ".join(h["nama"].lower().split()) != " ".join(info["name"].lower().split()),
        })
    return hasil


def banding_rute(
    koridor: list[dict], koridor_halte: list[dict], per_route: dict[str, set[str]]
) -> list[dict]:
    """Bandingkan himpunan halte tiap koridor statis dengan route_code yang sama di MQTT."""
    halte_statis: dict[int, set[str]] = defaultdict(set)
    for kh in koridor_halte:
        halte_statis[kh["koridor_id"]].add(kh["halte_id"])

    hasil = []
    for k in koridor:
        kode = str(k["nama_pendek"])
        statis = halte_statis.get(k["koridor_id"], set())
        live = per_route.get(kode)
        if live is None:
            hasil.append({
                "koridor_id": k["koridor_id"], "route_code": kode, "ada_di_mqtt": False,
                "halte_statis": len(statis),
            })
            continue
        irisan = statis & live
        hasil.append({
            "koridor_id": k["koridor_id"],
            "route_code": kode,
            "ada_di_mqtt": True,
            "halte_statis": len(statis),
            "halte_mqtt": len(live),
            "irisan": len(irisan),
            "hanya_statis": len(statis - live),
            "hanya_mqtt": len(live - statis),
            "persen_statis_terlayani": round(100 * len(irisan) / len(statis), 1) if statis else None,
        })
    return hasil


def tulis_csv(path: Path, rows: list[dict]) -> None:
    kolom: list[str] = []
    for r in rows:
        kolom.extend(k for k in r if k not in kolom)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kolom)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--detik", type=int, default=90, help="lama subscribe MQTT")
    ap.add_argument("--out", default="laporan_tj")
    args = ap.parse_args()

    from services.supabase_client import get_client

    sb = get_client()
    halte = sb.table("halte").select("halte_id, nama, lat, lng").execute().data
    koridor = sb.table("koridor").select("koridor_id, nama_pendek").execute().data
    koridor_halte = sb.table("koridor_halte").select("koridor_id, halte_id").limit(10000).execute().data

    print(f"Subscribe MQTT {args.detik} detik...")
    payloads = kumpulkan_mqtt(args.detik)
    by_id, by_parent, per_route = indeks_mqtt(payloads)

    mapping = cocokkan_halte(halte, by_id, by_parent)
    rute = banding_rute(koridor, koridor_halte, per_route)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tulis_csv(out / "halte_mapping.csv", mapping)
    tulis_csv(out / "halte_hanya_statis.csv", [m for m in mapping if m["cocok"] == "tidak_ada"])
    tulis_csv(out / "rute_banding.csv", rute)

    n = len(mapping)
    cocok_id = sum(m["cocok"] == "stop_id" for m in mapping)
    cocok_parent = sum(m["cocok"] == "parent_stop_id" for m in mapping)
    hilang = sum(m["cocok"] == "tidak_ada" for m in mapping)
    jauh = [m for m in mapping if m.get("koordinat_jauh")]
    nama_beda = sum(bool(m.get("nama_beda")) for m in mapping)
    ada = [r for r in rute if r["ada_di_mqtt"]]
    ps_kosong = all(not p.get("passengers_status") for p in payloads)
    laporan = [
        "# Perbandingan data statis vs MQTT TransJakarta",
        f"- Bus unik dari MQTT: {len(payloads)}; route_code: {len(per_route)}; stop_id: {len(by_id)}; parent_stop_id: {len(by_parent)}",
        f"- Halte statis: {n}. Cocok via stop_id: {cocok_id}; via parent_stop_id: {cocok_parent}; tidak ditemukan: {hilang}",
        f"- Koordinat selisih > {AMBANG_KOORDINAT_METER:.0f} m: {len(jauh)}; nama berbeda (normalisasi huruf/spasi): {nama_beda}",
        f"- Koridor statis: {len(rute)}. Ada di MQTT: {len(ada)}; tidak ada: {len(rute) - len(ada)}",
        f"- passengers_status kosong di semua bus: {ps_kosong}",
        "",
        "Catatan: halte yang 'tidak ditemukan' belum tentu salah; bisa karena tidak ada bus yang sedang melayani rutenya saat sampling.",
    ]
    (out / "laporan.md").write_text("\n".join(laporan) + "\n", encoding="utf-8")
    print("\n".join(laporan))


if __name__ == "__main__":
    main()
