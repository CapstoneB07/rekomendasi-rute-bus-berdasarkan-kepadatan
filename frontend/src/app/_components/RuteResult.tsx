'use client';

import {
  type BusRekomendasi,
  type NaikItem,
  type Rute,
  kepadatanKeWarna,
  labelKepadatan,
  normalisasiKepadatanDisplay,
} from '@/lib/route-utils';

const LABEL_TEKS = { sepi: 'Lega', sedang: 'Cukup ramai', padat: 'Padat' } as const;

// Warna label disinkronkan dengan RouteCard di halaman simulasi.
const BADGE_STYLE: Record<BusRekomendasi['label_kepadatan'], string> = {
  Sepi: 'bg-green-100 text-green-800',
  Sedang: 'bg-yellow-100 text-yellow-800',
  Padat: 'bg-red-100 text-red-800',
};

function KepadatanPill({ value }: { value: number }) {
  const v = normalisasiKepadatanDisplay(value);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-800">
      <span className="h-2 w-2 rounded-full" style={{ background: kepadatanKeWarna(v) }} />
      {LABEL_TEKS[labelKepadatan(v)]} · {Math.round(v * 100)}%
    </span>
  );
}

function BusNaik({ rek }: { rek: BusRekomendasi }) {
  const eta = rek.eta_menit <= 0 ? 'Sebentar lagi' : `${rek.eta_menit} menit lagi`;
  return (
    <div className="mt-2 flex items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2">
      <div>
        <div className="text-xs text-gray-500">Bus yang disarankan</div>
        <div className="text-sm font-semibold text-gray-900">
          Bus {rek.bus_id} · {eta}
        </div>
      </div>
      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${BADGE_STYLE[rek.label_kepadatan]}`}>
        {rek.label_kepadatan === 'Sepi' ? 'Lega' : rek.label_kepadatan}
      </span>
    </div>
  );
}

function LangkahNaik({ item }: { item: NaikItem }) {
  return (
    <li className="rounded-xl border-l-4 bg-white p-3 shadow-sm" style={{ borderColor: kepadatanKeWarna(item.kepadatan) }}>
      <div className="flex items-center gap-2">
        <span className="rounded bg-red-600 px-2 py-0.5 text-xs font-bold text-white">
          {item.koridor_id}
        </span>
        <span className="text-sm font-semibold text-gray-900">
          {item.nama_koridor ?? `Koridor ${item.koridor_id}`}
        </span>
      </div>
      <dl className="mt-2 space-y-0.5 text-sm text-gray-700">
        <div>
          <dt className="inline text-gray-500">Naik di </dt>
          <dd className="inline font-medium">{item.naik_di}</dd>
        </div>
        <div>
          <dt className="inline text-gray-500">Turun di </dt>
          <dd className="inline font-medium">{item.turun_di}</dd>
          <span className="text-gray-500"> · {item.waktu_menit} menit</span>
        </div>
      </dl>
      {item.bus_rekomendasi ? (
        <BusNaik rek={item.bus_rekomendasi} />
      ) : (
        <p className="mt-2 text-xs text-gray-500">Belum ada bus terjadwal yang bisa direkomendasikan.</p>
      )}
    </li>
  );
}

export function RuteResult({
  hasilRute,
  aktifIdx,
  setAktifIdx,
}: {
  hasilRute: Rute[];
  aktifIdx: number;
  setAktifIdx: (i: number) => void;
}) {
  const rute = hasilRute[aktifIdx];
  return (
    <section aria-label="Hasil rute">
      <div role="tablist" className="mb-3 flex gap-2 overflow-x-auto">
        {hasilRute.map((r, i) => (
          <button
            key={i}
            role="tab"
            aria-selected={i === aktifIdx}
            onClick={() => setAktifIdx(i)}
            className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
              i === aktifIdx
                ? 'border-red-600 bg-red-600 text-white'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div className="font-semibold">{i === 0 ? 'Paling lega' : `Alternatif ${i}`}</div>
            <div className="opacity-80">
              {r.estimasi_menit} menit · {r.jumlah_transit} transit
            </div>
          </button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-lg font-bold text-gray-900">~{rute.estimasi_menit} menit</span>
        <span className="text-sm text-gray-500">
          {rute.jumlah_transit === 0 ? 'Tanpa transit' : `${rute.jumlah_transit}× transit`}
        </span>
        <KepadatanPill value={rute.rata_kepadatan} />
      </div>

      <ol className="space-y-3">
        {rute.segmen.map((s, i) =>
          s.tipe === 'naik' ? (
            <LangkahNaik key={i} item={s} />
          ) : (
            <li key={i} className="rounded-xl bg-purple-50 px-3 py-2.5 text-sm">
              <div className="font-medium text-gray-900">Transit di {s.transit_di}</div>
              <div className="text-xs text-gray-600">
                Pindah dari Koridor {s.dari_koridor ?? '?'} ke Koridor {s.ke_koridor}
              </div>
            </li>
          ),
        )}
      </ol>
    </section>
  );
}
