import { formatJam } from './koridor';
import { jumlahTransit } from './rencana';
import type { NaikItem, Rute } from './route-utils';

// Jam (detik) naik dan turun satu leg. leg_clock_detik = jam tiba di halte naik (sudah
// memperhitungkan transit sebelumnya); tanpa bus rekomendasi jamnya tidak diketahui.
export function jamLeg(item: NaikItem, simTime: number): { naik: number | null; turun: number | null } {
  const rek = item.bus_rekomendasi;
  if (!rek) return { naik: null, turun: null };
  const naik = (rek.leg_clock_detik ?? simTime) + rek.eta_menit * 60;
  return { naik, turun: naik + item.waktu_menit * 60 };
}

export type LangkahTiket =
  | {
      tipe: 'naik';
      koridor: number;
      bus: string | null;
      naikDi: string;
      turunDi: string;
      jamNaik: string;
      jamTurun: string;
    }
  | { tipe: 'transit'; di: string; keKoridor: number };

export type Tiket = {
  nomor: string;
  dicetak: string;
  asal: string;
  tujuan: string;
  berangkat: string;
  tiba: string;
  estimasiMenit: number;
  jumlahTransit: number;
  langkah: LangkahTiket[];
};

const WIB = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Jakarta',
  year: '2-digit',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

function bagianWib(date: Date) {
  const p = Object.fromEntries(WIB.formatToParts(date).map((x) => [x.type, x.value]));
  return p as Record<'year' | 'month' | 'day' | 'hour' | 'minute' | 'second', string>;
}

function acakHex(): string {
  const b = crypto.getRandomValues(new Uint8Array(2));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('').toUpperCase();
}

// Nomor tiket: waktu cetak WIB sampai detik + 4 heksadesimal acak, supaya dua kiosk yang
// mencetak pada detik yang sama tetap berbeda.
export function nomorTiket(date: Date, acak: () => string = acakHex): string {
  const p = bagianWib(date);
  return `TJ-${p.year}${p.month}${p.day}-${p.hour}${p.minute}${p.second}-${acak()}`;
}

export function buatTiket(
  rute: Rute,
  opsi: { asal: string; tujuan: string; simTime: number; dicetak: Date; acak?: () => string },
): Tiket {
  const langkah: LangkahTiket[] = rute.segmen.map((s) => {
    if (s.tipe === 'transit') return { tipe: 'transit', di: s.transit_di, keKoridor: s.ke_koridor };
    const jam = jamLeg(s, opsi.simTime);
    return {
      tipe: 'naik',
      koridor: s.koridor_id,
      bus: s.bus_rekomendasi?.bus_id ?? null,
      naikDi: s.naik_di,
      turunDi: s.turun_di,
      jamNaik: jam.naik !== null ? formatJam(jam.naik) : '—',
      jamTurun: jam.turun !== null ? formatJam(jam.turun) : '—',
    };
  });
  const naik = langkah.filter((l) => l.tipe === 'naik');
  const p = bagianWib(opsi.dicetak);

  return {
    nomor: nomorTiket(opsi.dicetak, opsi.acak),
    dicetak: `${p.day}/${p.month}/${p.year} ${p.hour}.${p.minute}`,
    asal: opsi.asal,
    tujuan: opsi.tujuan,
    berangkat: naik[0]?.jamNaik ?? '—',
    tiba: naik.at(-1)?.jamTurun ?? '—',
    estimasiMenit: rute.estimasi_menit,
    jumlahTransit: jumlahTransit(rute),
    langkah,
  };
}
