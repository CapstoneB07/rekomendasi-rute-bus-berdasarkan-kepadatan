'use client';

import { formatJam } from '@/lib/koridor';
import { warnaLabelKepadatan, type NaikItem, type Rute } from '@/lib/route-utils';

import { LencanaKoridor } from './DaftarRencana';
import { IkonCetak, IkonPanahKiri } from './ikon';

function KartuNaik({ item, simTime }: { item: NaikItem; simTime: number }) {
  const rek = item.bus_rekomendasi;
  // leg_clock_detik = jam saat penumpang tiba di halte naik (sudah memperhitungkan transit sebelumnya).
  const dasar = rek?.leg_clock_detik ?? simTime;
  const naik = rek ? dasar + rek.eta_menit * 60 : null;
  const turun = naik !== null ? naik + item.waktu_menit * 60 : null;
  const label = rek?.label_kepadatan;

  return (
    <div className="shrink-0 overflow-hidden rounded-2xl border-[3px] border-tj-garis bg-white">
      <div className="flex flex-wrap items-center gap-x-[0.5rem] gap-y-[0.1rem] border-b-[3px] border-tj-garis px-[0.7rem] py-[0.2rem]">
        <LencanaKoridor koridorId={item.koridor_id} />
        {rek ? (
          <>
            <span className="whitespace-nowrap rounded-md bg-tj-teks px-[0.5rem] text-kecil font-bold leading-[1.7rem] text-white">
              {rek.bus_id}
            </span>
            <span className="ml-auto whitespace-nowrap text-kecil">
              {rek.eta_menit <= 0 ? 'Segera' : `${rek.eta_menit} menit lagi`}
            </span>
            {label && (
              <span
                className="flex items-center gap-[0.3rem] whitespace-nowrap text-kecil font-bold"
                style={{ color: warnaLabelKepadatan(label) }}
              >
                <span className="h-[0.7rem] w-[0.7rem] rounded-full" style={{ background: warnaLabelKepadatan(label) }} />
                {label}
              </span>
            )}
          </>
        ) : (
          <span className="ml-auto text-kecil text-gray-600">Belum ada bus terjadwal</span>
        )}
      </div>
      <dl className="space-y-[0.2rem] px-[0.8rem] py-[0.4rem] text-isi leading-tight">
        <div className="flex items-baseline justify-between gap-[0.6rem]">
          <dt className="min-w-0">
            Naik di <b>{item.naik_di}</b>
          </dt>
          <dd className="whitespace-nowrap text-kecil text-gray-600 tabular-nums">{naik !== null ? formatJam(naik) : '—'}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-[0.6rem]">
          <dt className="min-w-0">
            Turun di <b>{item.turun_di}</b>
          </dt>
          <dd className="whitespace-nowrap text-kecil text-gray-600 tabular-nums">
            ({item.waktu_menit} menit) {turun !== null ? formatJam(turun) : '—'}
          </dd>
        </div>
      </dl>
    </div>
  );
}

type Props = {
  rute: Rute;
  tujuan: string;
  simTime: number;
  onKembali: () => void;
};

export function DetailRencana({ rute, tujuan, simTime, onKembali }: Props) {
  return (
    <div className="layar-masuk flex h-full min-h-0 flex-col gap-[0.5rem] pb-[0.4rem]">
      <div className="flex items-center gap-[0.8rem]">
        <button
          type="button"
          onClick={onKembali}
          className="flex h-[2.4rem] shrink-0 items-center gap-[0.5rem] rounded-xl border-2 border-tj-biru px-[0.9rem] text-isi font-bold text-tj-biru"
        >
          <IkonPanahKiri className="h-[1.2rem] w-[1.2rem]" />
          Kembali
        </button>
        <span className="min-w-0 truncate text-besar font-bold">Ke {tujuan}</span>
      </div>

      {/* Rute dengan banyak bus tidak dipadatkan; daftar bergulir bila tidak muat. */}
      <div className="flex min-h-0 flex-1 flex-col gap-[0.5rem] overflow-y-auto">
        {rute.segmen.map((s, i) =>
          s.tipe === 'naik' ? (
            <KartuNaik key={i} item={s} simTime={simTime} />
          ) : (
            <div key={i} className="shrink-0 rounded-xl bg-orange-50 px-[0.8rem] py-[0.25rem] text-kecil leading-snug">
              Pindah bus di <b>{s.transit_di}</b> ke koridor {s.ke_koridor}
            </div>
          ),
        )}
      </div>

      {/* Isi cetak belum ditentukan, jadi tombol dinonaktifkan dulu. */}
      <button
        type="button"
        disabled
        title="Belum tersedia"
        className="flex h-[2.8rem] w-full shrink-0 items-center justify-center gap-[0.6rem] rounded-xl bg-tj-biru text-isi font-bold text-white opacity-50"
      >
        <IkonCetak className="h-[1.4rem] w-[1.4rem]" />
        Cetak Informasi
      </button>
    </div>
  );
}
