'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE } from '@/lib/api';

// Halte lokasi kiosk yang dipilih operator, dibagikan ke beranda lewat backend (/api/lokasi), antar perangkat.
const POLLING_LOKASI_MS = 2000;

// Operator: publikasikan halte terpilih. Gagal kirim tidak mengganggu operator.
export function useBagikanLokasi(halteId: string | null) {
  useEffect(() => {
    if (!halteId) return;
    const ac = new AbortController();
    fetch(`${API_BASE}/api/lokasi`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ halte_id: halteId }),
      signal: ac.signal,
    }).catch(() => {});
    return () => ac.abort();
  }, [halteId]);
}

// Kiosk: halte lokasi pilihan operator, null bila belum ada.
export function useLokasiOperator(): string | null {
  const { data } = useQuery({
    queryKey: ['lokasi-operator'],
    queryFn: async (): Promise<string | null> => {
      const r = await fetch(`${API_BASE}/api/lokasi`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()).lokasi?.halte_id ?? null;
    },
    refetchInterval: POLLING_LOKASI_MS,
  });
  return data ?? null;
}
