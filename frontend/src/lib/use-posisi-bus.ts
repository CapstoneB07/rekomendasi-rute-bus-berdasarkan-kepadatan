'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE } from '@/lib/api';
import type { PosisiBusAsliResponse, PosisiBusResponse } from '@/lib/route-utils';

// Posisi bus diminta tiap 5 detik simulasi, ditunda 300 ms setelah jam berhenti berubah.
const POSISI_BUCKET_DETIK = 5;
const POSISI_DEBOUNCE_MS = 300;
// Posisi bus asli (mode waktu nyata) diambil dari backend tiap 5 detik.
const BUS_ASLI_REFRESH_MS = 5_000;

// Posisi bus untuk peta: simulasi pada jam `simTime` bila tidak live, bus asli (MQTT) bila live.
export function usePosisiBus(simTime: number, isLive: boolean) {
  const [posisiWaktu, setPosisiWaktu] = useState<number | null>(null);
  useEffect(() => {
    const id = setTimeout(
      () => setPosisiWaktu(Math.floor(simTime / POSISI_BUCKET_DETIK) * POSISI_BUCKET_DETIK),
      POSISI_DEBOUNCE_MS,
    );
    return () => clearTimeout(id);
  }, [simTime]);

  const { data: posisiBus } = useQuery<PosisiBusResponse>({
    queryKey: ['posisi-bus', posisiWaktu],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/simulation/positions?sim_time=${posisiWaktu}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    enabled: !isLive && posisiWaktu !== null,
    placeholderData: (prev) => prev,
  });

  const { data: busAsli, isError: busAsliError } = useQuery<PosisiBusAsliResponse>({
    queryKey: ['posisi-bus-asli'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/live/positions`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    enabled: isLive,
    refetchInterval: BUS_ASLI_REFRESH_MS,
    placeholderData: (prev) => prev,
  });

  return { posisiBus, busAsli, busAsliError };
}
