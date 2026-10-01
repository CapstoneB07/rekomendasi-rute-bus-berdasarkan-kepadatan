"""Validasi paket CSV upload-ready terhadap SKEMA + DATA Supabase live.

Melengkapi `validate_upload_package.py` (yang hanya menguji topologi graf).
Validator ini menangkap kelas bug yang tidak terlihat oleh uji topologi:

  1. Nama kolom tidak cocok dengan tabel live  -> import gagal / data salah.
  2. Tipe kolom tidak cocok (int vs str)       -> PostgREST menolak.
  3. Nilai ridership berbeda dari baris live untuk (tanggal, koridor) yang
     sama -> UPSERT akan menimpa data benar dengan data salah.
  4. Cakupan koridor tidak konsisten antar file.

Kenapa ini ada: paket C501 pertama memakai header `grup_rute`/`jumlah_cabang`
(yang tidak ada di tabel live) dan menulis total mentah tanpa membagi jumlah
cabang, sehingga koridor 2/3/5 akan ter-upload 2-3x lipat. Uji topologi hijau
sepenuhnya karena ia tidak pernah membaca nama kolom atau nilai ridership.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/validate_upload_package_live.py --pkg "<dir>"
    ./venv/Scripts/python.exe scripts/validate_upload_package_live.py --pkg "<dir>" --offline
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Tabel + kolom kunci yang dibandingkan dengan Supabase.
LIVE_TABLES = {
    "koridor.csv": ("koridor", "koridor_id"),
    "halte.csv": ("halte", "halte_id"),
    "koridor_halte.csv": ("koridor_halte", "id"),
    "segmen.csv": ("segmen", "segmen_id"),
    "shapes.csv": ("shapes", "id"),
    "gtfs_trips.csv": ("gtfs_trips", "trip_id"),
    "gtfs_frequencies.csv": ("gtfs_frequencies", "trip_id"),
    "gtfs_stop_times.csv": ("gtfs_stop_times", "stop_sequence"),
    "ridership_harian_turunan.csv": ("ridership_harian_turunan", "koridor_id"),
}


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def live_columns(sb, table: str) -> tuple[list[str], dict]:
    """Ambil nama kolom + contoh tipe dari Supabase (1 baris)."""
    rows = sb.table(table).select("*").limit(1).execute().data
    if not rows:
        return [], {}
    types = {k: type(v).__name__ for k, v in rows[0].items()}
    return list(rows[0].keys()), types


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--offline", action="store_true", help="lewati pengecekan live")
    ap.add_argument("--live", action="store_true", help="cek nilai ridership vs DB")
    args = ap.parse_args()
    pkg = Path(args.pkg)

    errors: list[str] = []
    warnings: list[str] = []
    checks = 0

    # ---- 1. Struktur file
    for name in LIVE_TABLES:
        if not (pkg / name).exists():
            errors.append(f"FILE HILANG: {name}")

    # ---- 2. Kolom & tipe vs live
    sb = None
    if not args.offline:
        try:
            from services.supabase_client import get_client

            sb = get_client()
        except Exception as e:  # pragma: no cover
            warnings.append(f"tidak bisa konek Supabase ({e!r}); cek kolom dilewati")

    if sb is not None:
        print("== Cek kolom & tipe vs Supabase live ==")
        for fname, (table, _) in LIVE_TABLES.items():
            path = pkg / fname
            if not path.exists():
                continue
            header, _rows = read_csv(path)
            try:
                cols, types = live_columns(sb, table)
            except Exception as e:
                warnings.append(f"{fname}: tabel '{table}' tidak terbaca ({e!r})")
                continue
            if not cols:
                warnings.append(f"{fname}: tabel '{table}' kosong di live; cek dilewati")
                continue
            checks += 1
            missing_live = [c for c in cols if c not in header]
            extra = [c for c in header if c not in cols]
            status = "OK "
            if missing_live:
                status = "ERR"
                errors.append(
                    f"{fname}: kolom live tidak ada di CSV -> {missing_live}"
                )
            if extra:
                status = "ERR"
                errors.append(
                    f"{fname}: kolom CSV tidak ada di tabel live -> {extra}"
                )
            print(f"  [{status}] {fname:32s} vs {table:26s} tipe={ {k: types[k] for k in cols if k in types} }")

    # ---- 3. Konsistensi cakupan koridor antar file
    print("\n== Cek konsistensi cakupan koridor ==")
    try:
        k_head, k_rows = read_csv(pkg / "koridor.csv")
        koridor_csv = {str(r["koridor_id"]) for r in k_rows}
    except Exception as e:
        koridor_csv = set()
        errors.append(f"koridor.csv tidak terbaca: {e!r}")

    if (pkg / "ridership_harian_turunan.csv").exists():
        _h, r_rows = read_csv(pkg / "ridership_harian_turunan.csv")
        rid_kor = {str(r["koridor_id"]) for r in r_rows}
        checks += 1
        if koridor_csv and rid_kor != koridor_csv:
            missing = sorted(koridor_csv - rid_kor)
            extra_k = sorted(rid_kor - koridor_csv)
            errors.append(
                f"cakupan koridor beda: koridor.csv={sorted(koridor_csv)} "
                f"ridership={sorted(rid_kor)} (hilang={missing}, lebih={extra_k})"
            )
        print(f"  koridor.csv   : {sorted(koridor_csv)}")
        print(f"  ridership     : {sorted(rid_kor)}")
        print(f"  per koridor   : {_count_by(r_rows, 'koridor_id')}")

    # ---- 4. PK collision check
    # Untuk PK surrogate (`id`): id yang sama itu AMAN bila isi barisnya identik
    # (re-upload idempoten), dan BERBAHAYA bila isinya berbeda (menimpa data).
    # Untuk natural key (halte_id, segmen_id, trip_id): sama = UPSERT normal.
    if sb is not None:
        print("\n== Cek tabrakan primary key vs data live ==")
        for fname, (table, key) in LIVE_TABLES.items():
            path = pkg / fname
            if not path.exists():
                continue
            header, rows = read_csv(path)
            if key not in (header or []):
                continue
            try:
                live_by_key = _live_rows_by_key(sb, table, key)
            except Exception as e:
                warnings.append(f"{fname}: gagal ambil {key} live ({e!r})")
                continue
            if not live_by_key:
                continue
            checks += 1
            mine = {str(r[key]) for r in rows}
            collide = mine & set(live_by_key)
            if key != "id":
                if collide:
                    print(
                        f"  [OK ] {fname:32s} {len(collide)} {key} sama dgn live "
                        f"(natural key -> UPSERT)"
                    )
                else:
                    print(f"  [OK ] {fname:32s} tidak ada {key} yang menabrak")
                continue
            # PK surrogate: pisahkan tabrakan identik vs berbeda
            identical, differing = 0, []
            for r in rows:
                lv = live_by_key.get(str(r[key]))
                if lv is None:
                    continue
                if _row_identical(r, lv, header):
                    identical += 1
                else:
                    differing.append(str(r[key]))
            if differing:
                errors.append(
                    f"{fname}: {len(differing)} baris ber-id sama TAPI ISI BERBEDA "
                    f"dari live (contoh id {sorted(differing)[:5]}) -> akan menimpa "
                    f"data lama dengan nilai berbeda"
                )
            else:
                print(
                    f"  [OK ] {fname:32s} {identical} id sama & isi identik "
                    f"(re-upload idempoten, aman)"
                )

    # ---- 5. Nilai ridership vs live (yang menangkap bug pembagian cabang)
    if sb is not None and args.live and (pkg / "ridership_harian_turunan.csv").exists():
        print("\n== Cek nilai ridership vs Supabase live (UPSERT safety) ==")
        _h, r_rows = read_csv(pkg / "ridership_harian_turunan.csv")
        checked = mismatched = 0
        for row in r_rows:
            if str(row.get("koridor_id")) not in koridor_csv:
                continue
            try:
                live = (
                    sb.table("ridership_harian_turunan")
                    .select("jumlah_pelanggan_total,jumlah_cabang_pemodelan,jumlah_pelanggan_pemodelan")
                    .eq("tanggal", row["tanggal"])
                    .eq("koridor_id", str(row["koridor_id"]))
                    .limit(1)
                    .execute()
                    .data
                )
            except Exception as e:
                warnings.append(f"query live gagal: {e!r}")
                break
            if not live:
                continue
            checked += 1
            lv = live[0]
            if float(lv["jumlah_pelanggan_pemodelan"]) != float(row["jumlah_pelanggan_pemodelan"]):
                mismatched += 1
                if mismatched <= 5:
                    errors.append(
                        f"ridership BEDA ({row['tanggal']}, kor {row['koridor_id']}): "
                        f"live={lv['jumlah_pelanggan_pemodelan']} "
                        f"paket={row['jumlah_pelanggan_pemodelan']} "
                        f"(cabang live={lv['jumlah_cabang_pemodelan']}, "
                        f"paket={row['jumlah_cabang_pemodelan']})"
                    )
        print(f"  baris dibandingkan: {checked} | beda: {mismatched}")
        checks += 1

    # ---- Ringkasan
    print("\n" + "=" * 62)
    print(f"checks={checks}  errors={len(errors)}  warnings={len(warnings)}")
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    if errors:
        print("\nHASIL: TIDAK LAYAK UPLOAD — perbaiki error di atas.")
        return 2
    print("\nHASIL: OK — struktur & nilai konsisten dengan Supabase live.")
    return 0


def _live_rows_by_key(sb, table: str, key: str) -> dict[str, dict]:
    """Ambil baris live penuh, di-index per kolom kunci (paged)."""
    out: dict[str, dict] = {}
    offset = 0
    while True:
        chunk = sb.table(table).select("*").range(offset, offset + 999).execute().data
        if not chunk:
            break
        for r in chunk:
            if r.get(key) is not None:
                out[str(r[key])] = r
        if len(chunk) < 1000:
            break
        offset += 1000
    return out


def _norm(v) -> str:
    """Normalisasi nilai CSV (str) vs live (int/float/str) untuk perbandingan."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    s = str(v).strip()
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else repr(f)
    except (TypeError, ValueError):
        return s


def _row_identical(csv_row: dict, live_row: dict, header: list[str]) -> bool:
    """True bila semua kolom CSV (kecuali created_at) sama dengan nilai live."""
    for col in header:
        if col == "created_at":
            continue
        if col not in live_row:
            continue
        if _norm(csv_row.get(col)) != _norm(live_row.get(col)):
            return False
    return True


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[str(r[key])] = out.get(str(r[key]), 0) + 1
    return dict(sorted(out.items(), key=lambda x: (len(x[0]), x[0])))


if __name__ == "__main__":
    raise SystemExit(main())
