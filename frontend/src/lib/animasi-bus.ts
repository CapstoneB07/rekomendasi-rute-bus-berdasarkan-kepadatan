import type { PosisiBusResponse } from './route-utils';

// Bus asli hanya mengirim posisi ±30 detik sekali. Tiap posisi baru ditempuh mulus dari posisi
// yang sedang tampil selama kira-kira selisih waktu dua pembaruan, dibatasi rentang ini (ms).
export const DURASI_MIN_MS = 5_000;
export const DURASI_MAKS_MS = 35_000;
// Bus simulasi diperbarui tiap 1-5 detik (tergantung kecepatan jam), jadi rentangnya lebih pendek.
export const DURASI_SIMULASI_MIN_MS = 300;
export const DURASI_SIMULASI_MAKS_MS = 6_000;
// Perpindahan lebih jauh dari ini (derajat, ±2 km) dianggap lompatan nyata (geser jam, ganti trip,
// GPS loncat), bukan jalan: bus langsung ditaruh di tujuan tanpa meluncur melintasi peta.
export const LOMPAT_MAKS_DERAJAT = 0.02;

export type OpsiAnimasi = { durasiMinMs: number; durasiMaksMs: number };

export const OPSI_BUS_ASLI: OpsiAnimasi = { durasiMinMs: DURASI_MIN_MS, durasiMaksMs: DURASI_MAKS_MS };
export const OPSI_BUS_SIMULASI: OpsiAnimasi = {
  durasiMinMs: DURASI_SIMULASI_MIN_MS,
  durasiMaksMs: DURASI_SIMULASI_MAKS_MS,
};

type Lintasan = {
  dari: [number, number];
  ke: [number, number];
  mulai: number;
  durasi: number;
  // Waktu posisi target terakhir berubah; jadi dasar durasi lintasan berikutnya.
  berubahPada: number;
  // Arah gerak (derajat dari utara) dari lintasan terakhir; null bila belum pernah bergerak.
  arah: number | null;
  fitur: PosisiBusResponse['features'][number];
};

// Arah dari titik a ke b dalam derajat dari utara (0-359); null bila praktis tidak bergerak.
export function arahDerajat(a: [number, number], b: [number, number]): number | null {
  const dx = (b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180));
  const dy = b[1] - a[1];
  if (Math.hypot(dx, dy) < 1e-6) return null;
  return (Math.round((Math.atan2(dx, dy) * 180) / Math.PI) + 360) % 360;
}

function posisiSaatIni(l: Lintasan, sekarang: number): [number, number] {
  const t = Math.min(Math.max((sekarang - l.mulai) / l.durasi, 0), 1);
  return [l.dari[0] + (l.ke[0] - l.dari[0]) * t, l.dari[1] + (l.ke[1] - l.dari[1]) * t];
}

// Memegang lintasan tiap bus (kunci bus_id). Waktu selalu diberikan pemanggil supaya mudah diuji.
export class PenganimasiBus {
  private lintasan = new Map<string, Lintasan>();

  constructor(private readonly opsi: OpsiAnimasi = OPSI_BUS_ASLI) {}

  // Pasang data terbaru dari server: bus baru muncul di tempatnya, bus lama bergerak ke posisi baru.
  perbarui(data: PosisiBusResponse, sekarang: number): void {
    const ada = new Set<string>();
    for (const fitur of data.features) {
      const id = fitur.properties.bus_id;
      const ke = fitur.geometry.coordinates as [number, number];
      ada.add(id);

      const lama = this.lintasan.get(id);
      if (!lama) {
        this.lintasan.set(id, { dari: ke, ke, mulai: sekarang, durasi: 1, berubahPada: sekarang, arah: null, fitur });
        continue;
      }
      lama.fitur = fitur;
      if (ke[0] === lama.ke[0] && ke[1] === lama.ke[1]) continue;

      const sekarangDi = posisiSaatIni(lama, sekarang);
      const lompat = Math.hypot(ke[0] - sekarangDi[0], ke[1] - sekarangDi[1]) > LOMPAT_MAKS_DERAJAT;
      if (!lompat) lama.arah = arahDerajat(sekarangDi, ke) ?? lama.arah;
      lama.dari = lompat ? ke : sekarangDi;
      lama.ke = ke;
      lama.mulai = sekarang;
      lama.durasi = lompat
        ? 1
        : Math.min(Math.max(sekarang - lama.berubahPada, this.opsi.durasiMinMs), this.opsi.durasiMaksMs);
      lama.berubahPada = sekarang;
    }
    for (const id of this.lintasan.keys()) if (!ada.has(id)) this.lintasan.delete(id);
  }

  // Masih ada bus yang sedang bergerak pada waktu `sekarang`; bila tidak, frame tidak perlu digambar ulang.
  bergerak(sekarang: number): boolean {
    for (const l of this.lintasan.values()) if (sekarang < l.mulai + l.durasi) return true;
    return false;
  }

  // Posisi tiap bus pada waktu `sekarang`, dalam bentuk GeoJSON yang sama dengan respons server.
  frame(sekarang: number): PosisiBusResponse {
    return {
      type: 'FeatureCollection',
      features: [...this.lintasan.values()].map((l) => ({
        ...l.fitur,
        geometry: { type: 'Point', coordinates: posisiSaatIni(l, sekarang) },
        // Panah mengikuti arah gerak yang sebenarnya; bearing dari server hanya cadangan.
        properties: { ...l.fitur.properties, bearing: l.arah ?? l.fitur.properties.bearing },
      })),
    };
  }

  reset(): void {
    this.lintasan.clear();
  }
}
