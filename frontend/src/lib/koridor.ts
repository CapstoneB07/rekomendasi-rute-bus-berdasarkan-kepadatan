// Warna resmi koridor TransJakarta (route_color / route_text_color di payload MQTT).
export const WARNA_KORIDOR: Record<string, { bg: string; teks: string }> = {
  '1': { bg: '#D62126', teks: '#FFFFFF' },
  '2': { bg: '#2F489C', teks: '#FFFFFF' },
  '3': { bg: '#FDCB1C', teks: '#000000' },
  '4': { bg: '#512C62', teks: '#FFFFFF' },
  '5': { bg: '#D46425', teks: '#000000' },
  '8': { bg: '#DD3393', teks: '#FFFFFF' },
  '9': { bg: '#45A49E', teks: '#FFFFFF' },
  '12': { bg: '#7ABF7C', teks: '#000000' },
};
const WARNA_KORIDOR_LAIN = { bg: '#6B7280', teks: '#FFFFFF' };

export function warnaKoridor(id: number | string | null | undefined): { bg: string; teks: string } {
  return WARNA_KORIDOR[String(id)] ?? WARNA_KORIDOR_LAIN;
}

// Ekspresi MapLibre `match` dari koridor_id (angka atau string) ke warna latar koridor.
export function ekspresiWarnaKoridor(): unknown[] {
  return [
    'match',
    ['to-string', ['get', 'koridor_id']],
    ...Object.entries(WARNA_KORIDOR).flatMap(([id, w]) => [id, w.bg]),
    WARNA_KORIDOR_LAIN.bg,
  ];
}

// Tarif flat TransJakarta; transit antar koridor di dalam halte tidak menambah tarif.
export const TARIF_RP = 3500;

export function formatRupiah(n: number): string {
  return `Rp${String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;
}

// Detik sejak tengah malam -> "14.07" (format jam desain kiosk).
export function formatJam(detik: number): string {
  const total = Math.floor(detik / 60) % (24 * 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}.${String(m).padStart(2, '0')}`;
}

export function formatTanggal(date: Date): string {
  return new Intl.DateTimeFormat('id-ID', {
    timeZone: 'Asia/Jakarta',
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date);
}

export function formatKm(meter: number | undefined): string | null {
  return meter === undefined ? null : `${(meter / 1000).toFixed(1)} km`;
}
