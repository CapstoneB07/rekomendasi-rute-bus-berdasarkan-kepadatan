'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useQuery } from '@tanstack/react-query';

import { PanelKameraMqtt } from '../_components/PanelKameraMqtt';
import { PilihHalte } from '../_components/PilihHalte';
import { WaktuKontrol } from '../_components/WaktuKontrol';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ambilRekomendasi, API_BASE } from '@/lib/api';
import { formatJam } from '@/lib/koridor';
import { statusBusAsli, type HalteOpsi, type Rute } from '@/lib/route-utils';
import { usePencarianKiosk } from '@/lib/use-pencarian';
import { usePosisiBus } from '@/lib/use-posisi-bus';
import { useRelayBusTj } from '@/lib/relay-bus-tj';
import { useWaktuOperator } from '@/lib/use-waktu-simulasi';

// MapLibre butuh `window`, jadi hanya dirender di browser.
const RuteMap = dynamic(() => import('../_components/RuteMap').then((m) => m.RuteMap), { ssr: false });

// Halaman operator: kamera realtime dan peta bus simulasi/asli masing-masing setengah layar penuh (ponsel: bertumpuk), kontrol jam, dan pemilih lokasi halte.
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

  // Rute yang sedang dicari di kiosk: dihitung ulang di sini (jam operator) lalu digambar bertahap di peta.
  const pencarian = usePencarianKiosk();
  const { data: hasilRute } = useQuery<Rute[]>({
    queryKey: ['rute-kiosk', pencarian?.halte_asal, pencarian?.halte_tujuan, isLive],
    queryFn: () => ambilRekomendasi<Rute[]>(pencarian!.halte_asal, pencarian!.halte_tujuan, simTime, isLive),
    enabled: pencarian !== null,
    retry: 1,
    // Cukup sekali per pasangan halte: ETA yang basi tidak berarti untuk animasi, dan refetch akan memutarnya ulang.
    staleTime: Infinity,
  });
  const ruteKiosk = pencarian ? hasilRute?.[Math.min(pencarian.aktif_idx, (hasilRute?.length ?? 1) - 1)] : undefined;
  const infoPencarian = pencarian
    ? `Kiosk mencari: ${halteMap.get(pencarian.halte_asal)?.nama ?? '…'} → ${halteMap.get(pencarian.halte_tujuan)?.nama ?? '…'}`
    : null;

  const bus = isLive ? busAsli : posisiBus;
  const status = isLive
    ? statusBusAsli(busAsli, busAsliError)
    : `${posisiBus?.features.length ?? 0} bus simulasi aktif pukul ${formatJam(simTime)}`;

  return (
    <div className="flex h-dvh w-screen flex-col overflow-hidden bg-background">
      <header className="flex h-[3.6rem] shrink-0 items-center gap-[0.8rem] border-b-[0.2rem] border-tj-merah bg-primary px-[1.4rem] text-primary-foreground hp:h-auto hp:flex-wrap hp:gap-x-[0.5rem] hp:gap-y-[0.4rem] hp:px-[1rem] hp:py-[0.5rem]">
        {/* eslint-disable-next-line @next/next/no-img-element -- logo statis kecil, sama dengan header kiosk */}
        <img src="/logo-transjakarta-putih.png" alt="TransJakarta" className="h-[1.9rem] w-auto hp:h-[1.5rem]" />
        <h1 className="border-l border-white/40 pl-[0.8rem] text-besar font-bold tracking-tight hp:pl-[0.5rem] hp:text-isi">Operator</h1>
        <Badge varian={isLive ? 'aktif' : 'peringatan'} className={isLive ? 'border-transparent bg-background font-bold' : 'font-bold'}>
          {isLive ? 'LIVE' : 'SIMULASI'}
        </Badge>
        <span className="text-jam font-bold tabular-nums hp:ml-auto hp:text-judul">
          {formatJam(simTime)}
        </span>
        <Button varian="outline" onClick={() => setPemilihTerbuka(true)} disabled={!halteList} className="ml-auto border-white/50 bg-transparent text-kecil text-white hover:bg-white/15 hover:text-white hp:ml-0 hp:w-full">
          Lokasi: {halte?.nama ?? 'Pilih halte'}
        </Button>
      </header>

      <div className="shrink-0 px-[1.4rem] py-[0.6rem] hp:px-[0.6rem]">
        <WaktuKontrol waktu={waktu} />
      </div>

      {/* Sama dengan halaman user: ponsel peta di atas panel, selebihnya kamera dan peta masing-masing setengah layar penuh. */}
      <main className="grid min-h-0 flex-1 border-t grid-cols-2 grid-rows-[minmax(0,1fr)] hp:grid-cols-1 hp:grid-rows-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="relative col-start-2 row-start-1 min-h-0 min-w-0 overflow-hidden border-l bg-muted hp:col-start-1 hp:border-b hp:border-l-0">
          <RuteMap rute={ruteKiosk} halteMap={halteMap} bus={bus} fokus={halte} animasi={pencarian?.ts} putarKeNaik />
          <p
            role="status"
            className="absolute left-[0.6rem] top-[0.6rem] z-10 max-w-[calc(100%-1.2rem)] rounded-lg border bg-background/95 px-[0.6rem] py-[0.15rem] text-kecil shadow-sm"
          >
            {halteError ? 'Gagal memuat daftar halte. Pastikan server backend berjalan.' : (infoPencarian ?? status)}
            {waktu.tersinkron === false && ' · Jam belum terkirim ke halaman user'}
          </p>
        </div>

        <PanelKameraMqtt />
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
