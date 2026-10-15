import { describe, expect, it } from 'vitest';

import type { NaikItem, Rute, TransitItem } from './route-utils';
import { buatTiket, jamLeg, nomorTiket } from './tiket';

const naik = (
  koridor_id: number,
  naik_di: string,
  turun_di: string,
  waktu_menit: number,
  rek: { bus_id: string; eta_menit: number; leg_clock_detik?: number } | null,
): NaikItem =>
  ({
    tipe: 'naik',
    koridor_id,
    naik_di,
    turun_di,
    waktu_menit,
    bus_rekomendasi: rek,
  }) as unknown as NaikItem;

const transit = (transit_di: string, ke_koridor: number): TransitItem =>
  ({ tipe: 'transit', transit_di, ke_koridor }) as TransitItem;

const rute = (segmen: Rute['segmen'], estimasi_menit = 40): Rute =>
  ({ estimasi_menit, segmen }) as unknown as Rute;

// 15 Okt 2026 08.05.09 WIB.
const DICETAK = new Date('2026-10-15T01:05:09Z');
const JAM_8 = 8 * 3600;

describe('nomorTiket', () => {
  it('memakai waktu cetak WIB dan akhiran acak', () => {
    expect(nomorTiket(DICETAK, () => 'AB12')).toBe('TJ-261015-080509-AB12');
  });

  it('akhiran acak bawaan berupa 4 heksadesimal sehingga nomor berbeda', () => {
    const a = nomorTiket(DICETAK);
    expect(a).toMatch(/^TJ-261015-080509-[0-9A-F]{4}$/);
    const banyak = new Set(Array.from({ length: 20 }, () => nomorTiket(DICETAK)));
    expect(banyak.size).toBeGreaterThan(1);
  });
});

describe('jamLeg', () => {
  it('naik = jam tiba di halte + ETA, turun = naik + waktu tempuh', () => {
    expect(jamLeg(naik(1, 'A', 'B', 10, { bus_id: 'X', eta_menit: 5, leg_clock_detik: JAM_8 }), 0)).toEqual({
      naik: JAM_8 + 300,
      turun: JAM_8 + 900,
    });
  });

  it('memakai jam simulasi bila leg_clock_detik kosong', () => {
    expect(jamLeg(naik(1, 'A', 'B', 10, { bus_id: 'X', eta_menit: 0 }), JAM_8).naik).toBe(JAM_8);
  });

  it('tanpa bus rekomendasi jamnya tidak diketahui', () => {
    expect(jamLeg(naik(1, 'A', 'B', 10, null), JAM_8)).toEqual({ naik: null, turun: null });
  });
});

describe('buatTiket', () => {
  const opsi = { asal: 'Harmoni', tujuan: 'Blok M', simTime: JAM_8, dicetak: DICETAK, acak: () => '0F0F' };

  it('membentuk tiket dengan transit: berangkat dari leg pertama, tiba dari leg terakhir', () => {
    const t = buatTiket(
      rute([
        naik(1, 'Harmoni', 'Monas', 6, { bus_id: 'TJ-101', eta_menit: 4, leg_clock_detik: JAM_8 }),
        transit('Monas', 13),
        naik(13, 'Monas', 'Blok M', 20, { bus_id: 'TJ-213', eta_menit: 3, leg_clock_detik: JAM_8 + 600 }),
      ]),
      opsi,
    );
    expect(t).toEqual({
      nomor: 'TJ-261015-080509-0F0F',
      dicetak: '15/10/26 08.05',
      asal: 'Harmoni',
      tujuan: 'Blok M',
      berangkat: '08.04',
      tiba: '08.33',
      estimasiMenit: 40,
      jumlahTransit: 1,
      langkah: [
        { tipe: 'naik', koridor: 1, bus: 'TJ-101', naikDi: 'Harmoni', turunDi: 'Monas', jamNaik: '08.04', jamTurun: '08.10' },
        { tipe: 'transit', di: 'Monas', keKoridor: 13 },
        { tipe: 'naik', koridor: 13, bus: 'TJ-213', naikDi: 'Monas', turunDi: 'Blok M', jamNaik: '08.13', jamTurun: '08.33' },
      ],
    });
  });

  it('jam ditandai — bila bus belum terjadwal', () => {
    const t = buatTiket(rute([naik(1, 'Harmoni', 'Blok M', 20, null)]), opsi);
    expect(t.berangkat).toBe('—');
    expect(t.tiba).toBe('—');
    expect(t.langkah[0]).toMatchObject({ bus: null, jamNaik: '—', jamTurun: '—' });
    expect(t.jumlahTransit).toBe(0);
  });
});
