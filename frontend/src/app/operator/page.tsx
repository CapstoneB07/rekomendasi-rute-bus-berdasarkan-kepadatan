'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useQuery } from '@tanstack/react-query';

import { PilihHalte } from '../_components/PilihHalte';
import { WaktuKontrol } from '../_components/WaktuKontrol';
import { API_BASE } from '@/lib/api';
import { formatJam } from '@/lib/koridor';
import { statusBusAsli, type HalteOpsi } from '@/lib/route-utils';
import { usePosisiBus } from '@/lib/use-posisi-bus';
import { useWaktuOperator } from '@/lib/use-waktu-simulasi';

// MapLibre butuh `window`, jadi hanya dirender di browser.
const RuteMap = dynamic(() => import('../_components/RuteMap').then((m) => m.RuteMap), { ssr: false });

// Halaman operator: peta penuh dengan bus simulasi/asli, kontrol jam, dan pemilih lokasi halte.
export default function Operator() {
  const waktu = useWaktuOperator();
  const { simTime, isLive } = waktu;
  const { posisiBus, busAsli, busAsliError } = usePosisiBus(simTime, isLive);
  const [pemilihTerbuka, setPemilihTerbuka] = useState(false);
  const [halteId, setHalteId] = useState<string | null>(null);

  const { data: halteList, isError: halteError } = useQuery<HalteOpsi[]>({
    queryKey: ['halte-user'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/rute/halte`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 10 * 60_000,
  });
  const halteMap = useMemo(() => new Map((halteList ?? []).map((h) => [h.halte_id, h])), [halteList]);
  const halte = halteId ? halteMap.get(halteId) : undefined;

  const bus = isLive ? busAsli : posisiBus;
  const status = isLive
    ? statusBusAsli(busAsli, busAsliError)
    : `${posisiBus?.features.length ?? 0} bus simulasi aktif pukul ${formatJam(simTime)}`;

  return (
    <div className="flex h-dvh w-screen flex-col overflow-hidden bg-white">
      <header className="flex shrink-0 flex-wrap items-center gap-[0.8rem] px-[1.4rem] py-[0.5rem]">
        <h1 className="text-besar font-bold text-tj-biru">Operator</h1>
        <span
          className={`rounded-lg px-[0.6rem] py-[0.1rem] text-kecil font-bold text-white ${
            isLive ? 'bg-tj-sepi' : 'bg-tj-oranye'
          }`}
        >
          {isLive ? 'LIVE' : 'SIMULASI'}
        </span>
        <span className="text-jam font-medium tabular-nums text-tj-biru">{formatJam(simTime)}</span>
        <button
          type="button"
          onClick={() => setPemilihTerbuka(true)}
          disabled={!halteList}
          className="ml-auto h-[2.4rem] rounded-xl border-2 border-tj-biru px-[0.9rem] text-kecil font-bold text-tj-biru disabled:opacity-50"
        >
          Lokasi: {halte?.nama ?? 'Pilih halte'}
        </button>
      </header>

      <div className="shrink-0 px-[1.4rem]">
        <WaktuKontrol waktu={waktu} />
      </div>

      <main className="relative m-[1.4rem] mt-[0.5rem] min-h-0 flex-1 overflow-hidden rounded-2xl bg-gray-100">
        <RuteMap rute={undefined} halteMap={halteMap} bus={bus} fokus={halte} />
        <p
          role="status"
          className="absolute left-[0.6rem] top-[0.6rem] z-10 rounded-lg border border-tj-garis bg-white/95 px-[0.6rem] py-[0.15rem] text-kecil text-tj-teks shadow"
        >
          {halteError ? 'Gagal memuat daftar halte. Pastikan server backend berjalan.' : status}
          {waktu.tersinkron === false && ' · Jam belum terkirim ke halaman user'}
        </p>
      </main>

      {pemilihTerbuka && halteList && (
        <PilihHalte
          judul="Pilih lokasi halte"
          halteList={halteList}
          terpilihId={halteId}
          onPilih={(id) => {
            setHalteId(id);
            setPemilihTerbuka(false);
          }}
          onTutup={() => setPemilihTerbuka(false)}
        />
      )}
    </div>
  );
}
