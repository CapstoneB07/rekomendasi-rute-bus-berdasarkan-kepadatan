'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE } from '@/lib/api';

// Pencarian rute kiosk yang dibagikan ke operator lewat backend (/api/pencarian), antar perangkat.
export type PencarianKiosk = { halte_asal: string; halte_tujuan: string; aktif_idx: number; ts: number };

const POLLING_PENCARIAN_MS = 2000;

// Kiosk: laporkan pencarian aktif (atau hapus saat kembali ke beranda). Gagal kirim tidak mengganggu kiosk.
export function useBagikanPencarian(pencarian: { asal: string; tujuan: string } | null, aktifIdx: number) {
  const asal = pencarian?.asal;
  const tujuan = pencarian?.tujuan;
  useEffect(() => {
    const ac = new AbortController();
    const kirim = asal && tujuan
      ? fetch(`${API_BASE}/api/pencarian`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ halte_asal: asal, halte_tujuan: tujuan, aktif_idx: aktifIdx }),
          signal: ac.signal,
        })
      : fetch(`${API_BASE}/api/pencarian`, { method: 'DELETE', signal: ac.signal });
    kirim.catch(() => {});
    return () => ac.abort();
  }, [asal, tujuan, aktifIdx]);
}

// Operator: pencarian terakhir kiosk, null bila kiosk sedang di beranda.
export function usePencarianKiosk(): PencarianKiosk | null {
  const { data } = useQuery({
    queryKey: ['pencarian-kiosk'],
    queryFn: async (): Promise<PencarianKiosk | null> => {
      const r = await fetch(`${API_BASE}/api/pencarian`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()).pencarian;
    },
    refetchInterval: POLLING_PENCARIAN_MS,
  });
  return data ?? null;
}
