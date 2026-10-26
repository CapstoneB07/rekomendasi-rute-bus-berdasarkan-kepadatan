'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useQuery } from '@tanstack/react-query';

import { PanelKamera } from '../_components/PanelKamera';
import { PanelKameraMqtt } from '../_components/PanelKameraMqtt';
import { PilihHalte } from '../_components/PilihHalte';
import { WaktuKontrol } from '../_components/WaktuKontrol';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { API_BASE } from '@/lib/api';
import { formatJam } from '@/lib/koridor';
import { statusBusAsli, type HalteOpsi } from '@/lib/route-utils';
import { usePosisiBus } from '@/lib/use-posisi-bus';
import { useRelayBusTj } from '@/lib/relay-bus-tj';
import { useWaktuOperator } from '@/lib/use-waktu-simulasi';

// MapLibre butuh `window`, jadi hanya dirender di browser.
const RuteMap = dynamic(() => import('../_components/RuteMap').then((m) => m.RuteMap), { ssr: false });

// Halaman operator: peta penuh dengan bus simulasi/asli, kontrol jam, pemilih lokasi halte, dan kamera bus.
export default function Operator() {
  const waktu = useWaktuOperator();
  const { simTime, isLive } = waktu;
  // Browser ini ikut meneruskan bus asli TJ ke backend (IP VPS diblokir broker).
  useRelayBusTj();
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
    <div className="flex h-dvh w-screen flex-col overflow-hidden bg-background">
      <header className="flex h-[3.6rem] shrink-0 items-center gap-[0.8rem] border-b px-[1.4rem]">
        {/* eslint-disable-next-line @next/next/no-img-element -- logo statis kecil, sama dengan header kiosk */}
        <img src="/logo-transjakarta.png" alt="TransJakarta" className="h-[2.2rem] w-auto" />
        <h1 className="border-l pl-[0.8rem] text-besar font-bold tracking-tight">Operator</h1>
        <Badge varian={isLive ? 'aktif' : 'peringatan'} className="font-bold">
          {isLive ? 'LIVE' : 'SIMULASI'}
        </Badge>
        <span className={`text-jam font-bold tabular-nums ${isLive ? 'text-primary' : 'text-tj-oranye'}`}>
          {formatJam(simTime)}
        </span>
        <Button varian="outline" onClick={() => setPemilihTerbuka(true)} disabled={!halteList} className="ml-auto text-kecil">
          Lokasi: {halte?.nama ?? 'Pilih halte'}
        </Button>
      </header>

      <div className="shrink-0 px-[1.4rem] pt-[0.6rem]">
        <WaktuKontrol waktu={waktu} />
      </div>

      <main className="relative m-[1.4rem] mt-[0.6rem] min-h-0 flex-1 overflow-hidden rounded-xl border bg-muted shadow-sm">
        <RuteMap rute={undefined} halteMap={halteMap} bus={bus} fokus={halte} />
        {/* Lebar dibatasi supaya tidak tertutup panel kamera (20rem) di kanan. */}
        <p
          role="status"
          className="absolute left-[0.6rem] top-[0.6rem] z-10 max-w-[calc(100%-22rem)] rounded-lg border bg-background/95 px-[0.6rem] py-[0.15rem] text-kecil shadow-sm"
        >
          {halteError ? 'Gagal memuat daftar halte. Pastikan server backend berjalan.' : status}
          {waktu.tersinkron === false && ' · Jam belum terkirim ke halaman user'}
        </p>
        <div className="absolute right-[0.6rem] top-[0.6rem] z-10 flex max-h-[calc(100%-1.2rem)] flex-col gap-[0.6rem] overflow-y-auto">
          <PanelKameraMqtt />
          <PanelKamera />
        </div>
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
