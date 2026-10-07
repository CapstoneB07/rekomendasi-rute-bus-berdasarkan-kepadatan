import type { HalteOpsi } from './route-utils';

// Kelompok pertama: halte transit (dilayani >= 2 koridor), yang paling sering dituju.
export const KELOMPOK_UTAMA = '★';

const urut = (a: HalteOpsi, b: HalteOpsi) => a.nama.localeCompare(b.nama, 'id');

// Dua peron bernama sama (mis. dua "Gunung Sahari") satu tempat bagi penumpang; backend menganggapnya
// satu titik, jadi grid cukup menampilkan satu. Yang dipertahankan: id terkecil, supaya hasil stabil.
function unikPerNama(list: HalteOpsi[]): HalteOpsi[] {
  const per = new Map<string, HalteOpsi>();
  for (const h of [...list].sort((a, b) => a.halte_id.localeCompare(b.halte_id))) {
    const kunci = h.nama.trim().toLowerCase();
    if (!per.has(kunci)) per.set(kunci, h);
  }
  return [...per.values()];
}

export function halteUtama(list: HalteOpsi[]): HalteOpsi[] {
  return unikPerNama(list.filter((h) => h.koridor_list.length >= 2)).sort(urut);
}

// Kelompok yang punya isi: "★" (bila ada halte transit) lalu huruf awal nama yang ada, terurut.
export function daftarKelompok(list: HalteOpsi[]): string[] {
  const huruf = [...new Set(list.map((h) => h.nama.trim().charAt(0).toUpperCase()))].sort();
  return halteUtama(list).length > 0 ? [KELOMPOK_UTAMA, ...huruf] : huruf;
}

export function filterKelompok(list: HalteOpsi[], kelompok: string): HalteOpsi[] {
  if (kelompok === KELOMPOK_UTAMA) return halteUtama(list);
  return unikPerNama(list.filter((h) => h.nama.trim().charAt(0).toUpperCase() === kelompok)).sort(urut);
}

// Potong ke satu halaman; indeks di luar rentang dijepit supaya tidak pernah menghasilkan halaman kosong.
export function halaman<T>(items: T[], indeks: number, perHalaman: number) {
  const jumlah = Math.max(1, Math.ceil(items.length / perHalaman));
  const idx = Math.min(Math.max(indeks, 0), jumlah - 1);
  return { items: items.slice(idx * perHalaman, (idx + 1) * perHalaman), idx, jumlah };
}
