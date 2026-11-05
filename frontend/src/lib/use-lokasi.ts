'use client';

import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { API_BASE } from '@/lib/api';
import type { HalteOpsi } from '@/lib/route-utils';

// Halte lokasi kiosk yang dipilih operator, dibagikan lewat backend (/api/lokasi) antar perangkat.
// Operator adalah satu-satunya penulis; operator dan kiosk sama-sama membaca nilai dari backend,
// jadi keduanya tidak bisa menampilkan halte yang berbeda.
const POLLING_LOKASI_MS = 2000;
const KUNCI_LOKASI = ['lokasi-operator'] as const;

// Halte asal bawaan desain, dipakai operator dan kiosk selama operator belum memilih.
const HALTE_LOKASI_DEFAULT = 'Harmoni';

export function halteLokasiDefault(halteList: HalteOpsi[] | undefined): HalteOpsi | undefined {
  return halteList?.find((h) => h.nama === HALTE_LOKASI_DEFAULT) ?? halteList?.[0];
}

// Halte lokasi pilihan operator, null bila belum ada.
export function useLokasiOperator(): string | null {
  const { data } = useQuery({
    queryKey: KUNCI_LOKASI,
    queryFn: async (): Promise<string | null> => {
      const r = await fetch(`${API_BASE}/api/lokasi`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()).lokasi?.halte_id ?? null;
    },
    refetchInterval: POLLING_LOKASI_MS,
  });
  return data ?? null;
}

// Operator: pilih halte lokasi. Tampil langsung, lalu disamakan ulang dengan backend;
// bila kirim gagal, tampilan kembali ke nilai backend (yang juga dilihat kiosk).
export function useAturLokasi(): (halteId: string) => Promise<void> {
  const qc = useQueryClient();
  return useCallback(
    async (halteId) => {
      // Polling yang sedang berjalan membawa nilai lama; batalkan supaya tidak menimpa pilihan ini.
      await qc.cancelQueries({ queryKey: KUNCI_LOKASI });
      qc.setQueryData(KUNCI_LOKASI, halteId);
      try {
        await fetch(`${API_BASE}/api/lokasi`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ halte_id: halteId }),
        });
      } catch {
        // Gagal kirim: invalidasi di bawah mengembalikan tampilan ke nilai backend.
      }
      await qc.invalidateQueries({ queryKey: KUNCI_LOKASI });
    },
    [qc],
  );
}
