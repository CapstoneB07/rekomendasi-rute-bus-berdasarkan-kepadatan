// Konfigurasi + helper waktu untuk halaman yang memanggil backend FastAPI.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// Kontrol demo (jam simulasi, ganti halte asal) hanya tampil bila diaktifkan; kiosk publik tidak memilikinya.
export const MODE_DEMO = process.env.NEXT_PUBLIC_MODE_DEMO === 'true';

const WIB_FORMAT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Jakarta',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  weekday: 'short',
  hourCycle: 'h23',
});

// Waktu nyata dalam WIB, dalam bentuk yang diminta POST /api/rute/rekomendasi.
export function waktuWib(date: Date = new Date()) {
  const parts = Object.fromEntries(
    WIB_FORMAT.formatToParts(date).map((p) => [p.type, p.value]),
  );
  const jam = Number(parts.hour);
  const detik = jam * 3600 + Number(parts.minute) * 60 + Number(parts.second);
  const hariTipe: 'weekday' | 'weekend' =
    parts.weekday === 'Sat' || parts.weekday === 'Sun' ? 'weekend' : 'weekday';
  return { jam, detik, hariTipe, label: `${parts.hour}:${parts.minute}` };
}

// Galat HTTP dari backend; `message` berisi `detail` FastAPI bila berupa teks.
export class GalatApi extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export type GalatTampil = { judul: string; pesan: string; bisaCoba: boolean };

// 400/404 = permintaan valid tapi tidak ada rute (pesan backend sudah berbahasa Indonesia).
// Selain itu (jaringan putus, 5xx) sifatnya sementara, jadi pengguna ditawari mencoba lagi.
export function galatRute(error: unknown): GalatTampil {
  if (error instanceof GalatApi && (error.status === 400 || error.status === 404)) {
    return {
      judul: 'Rute tidak ditemukan',
      pesan: error.message || 'Tidak ada rute untuk perjalanan ini.',
      bisaCoba: false,
    };
  }
  return {
    judul: 'Layanan sedang bermasalah',
    pesan: 'Rute belum dapat dimuat. Periksa koneksi, lalu coba lagi.',
    bisaCoba: true,
  };
}
