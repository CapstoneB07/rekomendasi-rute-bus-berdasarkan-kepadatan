// Konfigurasi + helper waktu untuk halaman yang memanggil backend FastAPI.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
