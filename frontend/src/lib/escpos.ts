// Penyusun perintah ESC/POS untuk printer thermal 80 mm (RPP02N dkk). Padanan 1:1 dari
// backend/services/thermal_printer.py supaya cetak lewat BLE (browser) dan lewat backend
// menghasilkan byte yang sama.

import type { BarisCetak } from '@/lib/tiket';

export const KOLOM_TEKS = 48;
// Printer kecil punya buffer terbatas: raster dikirim per pita 64 baris.
const BARIS_PER_PITA = 64;

const RESET = [0x1b, 0x40];
const TOLAK_KERTAS = [0x0a, 0x0a, 0x0a, 0x0a]; // dorong kertas keluar dari kepala cetak

function ascii(teks: string): string {
  let out = '';
  for (const c of teks) {
    const k = c.codePointAt(0)!;
    out += k >= 32 && k < 127 ? c : '?';
  }
  return out;
}

function bytesAscii(teks: string): number[] {
  return Array.from(ascii(teks), (c) => c.charCodeAt(0));
}

// Pola pemisah kata textwrap.TextWrapper.wordsep_re (Python 3.13): spasi, tanda hubung di dalam kata
// ("kira-kira" -> "kira-", "kira"), dan em-dash. Teks sudah ASCII, jadi \w/\d cukup.
const WS = String.raw`[ \t\n\r\f\v]`;
const NWS = String.raw`[^ \t\n\r\f\v]`;
const LT = String.raw`[^\W\d]`;
const WP = String.raw`[\w!"'&.,?]`;
const PEMISAH_KATA = new RegExp(
  String.raw`(${WS}+|(?<=${WP})-{2,}(?=\w)|${NWS}+?(?:-(?:(?<=${LT}{2}-)|(?<=${LT}-${LT}-))(?=${LT}-?${LT})|(?=${WS}|$)|(?<=${WP})(?=-{2,}\w)))`,
);

// Padanan textwrap.wrap(teks, lebar): pembungkusan serakah, spasi di tepi baris dibuang,
// kata lebih panjang dari lebar dipotong.
export function bungkus(teks: string, lebar: number): string[] {
  const chunks = teks.replace(/\s/g, ' ').split(PEMISAH_KATA).filter((c) => c !== '').reverse();
  const baris: string[] = [];
  while (chunks.length) {
    const cur: string[] = [];
    let curLen = 0;
    if (chunks[chunks.length - 1].trim() === '' && baris.length) chunks.pop();
    while (chunks.length) {
      const l = chunks[chunks.length - 1].length;
      if (curLen + l <= lebar) {
        cur.push(chunks.pop()!);
        curLen += l;
      } else break;
    }
    if (chunks.length && chunks[chunks.length - 1].length > lebar) {
      const sisa = lebar - curLen;
      const c = chunks.pop()!;
      cur.push(c.slice(0, sisa));
      chunks.push(c.slice(sisa));
    }
    if (cur.length && cur[cur.length - 1].trim() === '') {
      curLen -= cur[cur.length - 1].length;
      cur.pop();
    }
    if (cur.length) baris.push(cur.join(''));
  }
  return baris;
}

// Padanan str.center + rstrip (Python menaruh spasi lebih di kiri bila selisihnya ganjil).
function tengahkan(x: string, lebar: number): string {
  const marg = lebar - x.length;
  if (marg <= 0) return x;
  const kiri = Math.floor(marg / 2) + (marg & lebar & 1);
  return (' '.repeat(kiri) + x).trimEnd();
}

function tataBaris(b: BarisCetak, kolom: number): string[] {
  if (b.garis) return ['-'.repeat(kolom)];
  const teks = ascii(b.teks ?? '');
  const kanan = ascii(b.kanan ?? '');
  if (kanan) {
    if (teks.length + 1 + kanan.length <= kolom) return [teks + ' '.repeat(kolom - teks.length - kanan.length) + kanan];
    // Terlalu panjang untuk satu baris: label dibungkus, nilai rata kanan di baris sendiri.
    const kiri = teks ? bungkus(teks, kolom) : [];
    return [...kiri, ...bungkus(kanan, kolom).map((x) => x.padStart(kolom))];
  }
  const hasil = bungkus(teks, kolom);
  const baris = hasil.length ? hasil : [''];
  return b.tengah ? baris.map((x) => tengahkan(x, kolom)) : baris;
}

// Struk teks: tiap baris ditata ke `kolom` karakter. Baris `besar` (judul) dua kali tinggi saja.
export function susunEscposTeks(baris: BarisCetak[], kolom = KOLOM_TEKS): Uint8Array {
  const out: number[] = [...RESET];
  for (const b of baris) {
    // ESC E n: tebal. GS ! n: ukuran karakter (0x01 = tinggi dua kali).
    const awal = [...(b.tebal ? [0x1b, 0x45, 0x01] : []), ...(b.besar ? [0x1d, 0x21, 0x01] : [])];
    const akhir = [...(b.besar ? [0x1d, 0x21, 0x00] : []), ...(b.tebal ? [0x1b, 0x45, 0x00] : [])];
    for (const t of tataBaris(b, kolom)) out.push(...awal, ...bytesAscii(t), ...akhir, 0x0a);
  }
  out.push(...TOLAK_KERTAS);
  return Uint8Array.from(out);
}

// Bitmap 1-bit (bit 1 = hitam, tiap baris dibulatkan ke byte) + keterangan teks di bawahnya.
export function susunEscposFoto(lebar: number, tinggi: number, bits: Uint8Array, baris: string[]): Uint8Array {
  const perBaris = lebar / 8;
  if (lebar % 8 || bits.length !== perBaris * tinggi) throw new Error('ukuran bitmap tidak cocok dengan lebar x tinggi');
  const out: number[] = [...RESET];
  for (let y = 0; y < tinggi; y += BARIS_PER_PITA) {
    const n = Math.min(BARIS_PER_PITA, tinggi - y);
    // GS v 0 m xL xH yL yH: raster bit image, m=0 skala normal.
    out.push(0x1d, 0x76, 0x30, 0x00, perBaris & 0xff, perBaris >> 8, n & 0xff, n >> 8);
    for (const b of bits.subarray(y * perBaris, (y + n) * perBaris)) out.push(b);
  }
  out.push(0x0a);
  for (const b of baris) out.push(...bytesAscii(b), 0x0a);
  out.push(...TOLAK_KERTAS);
  return Uint8Array.from(out);
}
