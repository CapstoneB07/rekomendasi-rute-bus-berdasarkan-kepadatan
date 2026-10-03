'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';

import { HaltePicker, type HalteOpsi } from './_components/HaltePicker';
import { RuteResult } from './_components/RuteResult';
import { API_BASE, waktuWib } from '@/lib/api';
import type { Halte, Rute } from '@/lib/route-utils';

// MapLibre butuh `window`, jadi hanya dirender di browser.
const RuteMap = dynamic(() => import('./_components/RuteMap').then((m) => m.RuteMap), {
  ssr: false,
});

const REFRESH_MS = 30_000;

type Pencarian = { asal: string; tujuan: string };

export default function Home() {
  const [asal, setAsal] = useState<string | null>(null);
  const [tujuan, setTujuan] = useState<string | null>(null);
  const [pencarian, setPencarian] = useState<Pencarian | null>(null);
  const [aktifIdx, setAktifIdx] = useState(0);

  const { data: halteList, isError: halteError, isPending: halteLoading } = useQuery<HalteOpsi[]>({
    queryKey: ['halte-user'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/rute/halte`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 10 * 60_000,
  });

  const {
    data: hasilRute,
    isFetching,
    isError: ruteError,
    error,
    dataUpdatedAt,
  } = useQuery<Rute[]>({
    queryKey: ['rute-user', pencarian?.asal, pencarian?.tujuan],
    queryFn: async () => {
      // Waktu dihitung saat fetch (bukan saat render) supaya ETA bus ikut
      // segar pada tiap refetch otomatis.
      const { jam, detik, hariTipe } = waktuWib();
      const r = await fetch(`${API_BASE}/api/rute/rekomendasi`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          halte_asal: pencarian!.asal,
          halte_tujuan: pencarian!.tujuan,
          jam,
          hari_tipe: hariTipe,
          sim_time: detik,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${r.status}`);
      }
      return r.json();
    },
    enabled: pencarian !== null,
    refetchInterval: REFRESH_MS,
    retry: 1,
  });

  const halteMap = useMemo(
    () => new Map<string, Halte>((halteList ?? []).map((h) => [h.halte_id, h])),
    [halteList],
  );
  const ruteAktif =
    pencarian && hasilRute && hasilRute.length > 0
      ? hasilRute[Math.min(aktifIdx, hasilRute.length - 1)]
      : undefined;

  const samaHalte = asal !== null && asal === tujuan;
  const bisaCari = asal !== null && tujuan !== null && !samaHalte;

  const cari = (e: React.FormEvent) => {
    e.preventDefault();
    if (!bisaCari) return;
    setAktifIdx(0);
    setPencarian({ asal, tujuan });
  };

  const tukar = () => {
    setAsal(tujuan);
    setTujuan(asal);
    setPencarian(null);
  };

  return (
    <div className="flex-1 bg-gray-50 text-gray-900">
      <header className="bg-red-600 px-4 pb-10 pt-6 text-white">
        <div className="mx-auto max-w-md lg:max-w-6xl">
          <h1 className="text-xl font-bold">TransJakarta Lega</h1>
          <p className="mt-1 text-sm text-red-100">
            Pilih rute dan bus yang paling lega, berdasarkan kepadatan bus saat ini.
          </p>
        </div>
      </header>

      <main className="mx-auto -mt-6 max-w-md px-4 pb-10 lg:grid lg:max-w-6xl lg:grid-cols-[1fr_26rem] lg:items-start lg:gap-6">
        <div className="mb-4 h-64 overflow-hidden rounded-2xl bg-gray-200 shadow-md lg:sticky lg:top-4 lg:mb-0 lg:h-[calc(100vh-2rem)]">
          <RuteMap rute={ruteAktif} halteMap={halteMap} />
        </div>

        <div className="space-y-4">
        <form onSubmit={cari} className="space-y-3 rounded-2xl bg-white p-4 shadow-md">
          <HaltePicker
            label="Dari halte"
            placeholder="Cari halte asal"
            halteList={halteList ?? []}
            value={asal}
            onChange={(id) => {
              setAsal(id);
              setPencarian(null);
            }}
            disabled={!halteList}
          />
          <div className="flex justify-center">
            <button
              type="button"
              onClick={tukar}
              className="rounded-full border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
              aria-label="Tukar halte asal dan tujuan"
            >
              ⇅ Tukar
            </button>
          </div>
          <HaltePicker
            label="Ke halte"
            placeholder="Cari halte tujuan"
            halteList={halteList ?? []}
            value={tujuan}
            onChange={(id) => {
              setTujuan(id);
              setPencarian(null);
            }}
            disabled={!halteList}
          />

          {samaHalte && (
            <p role="alert" className="text-xs text-red-700">
              Halte asal dan tujuan tidak boleh sama.
            </p>
          )}
          {halteError && (
            <p role="alert" className="text-xs text-red-700">
              Gagal memuat daftar halte. Pastikan server backend berjalan.
            </p>
          )}

          <button
            type="submit"
            disabled={!bisaCari || isFetching}
            className="w-full rounded-lg bg-red-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            {halteLoading ? 'Memuat halte…' : isFetching && !hasilRute ? 'Mencari…' : 'Cari rute'}
          </button>
        </form>

        {pencarian && ruteError && (
          <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <div className="font-semibold">Rute tidak ditemukan</div>
            <div className="mt-1 text-xs">
              {error instanceof Error ? error.message : 'Terjadi kesalahan saat mencari rute.'}
            </div>
          </div>
        )}

        {pencarian && isFetching && !hasilRute && !ruteError && (
          <div className="animate-pulse space-y-3" aria-hidden>
            <div className="h-10 rounded-lg bg-gray-200" />
            <div className="h-24 rounded-xl bg-gray-200" />
            <div className="h-24 rounded-xl bg-gray-200" />
          </div>
        )}

        {pencarian && hasilRute && hasilRute.length > 0 && (
          <>
            <RuteResult
              hasilRute={hasilRute}
              aktifIdx={Math.min(aktifIdx, hasilRute.length - 1)}
              setAktifIdx={setAktifIdx}
            />
            <p className="text-center text-xs text-gray-500">
              Diperbarui otomatis tiap {REFRESH_MS / 1000} detik
              {dataUpdatedAt ? ` · terakhir ${waktuWib(new Date(dataUpdatedAt)).label} WIB` : ''}
            </p>
          </>
        )}

        <p className="pt-2 text-center text-xs text-gray-400">
          <Link href="/simulation" className="underline hover:text-gray-600">
            Lihat simulasi
          </Link>
        </p>
        </div>
      </main>
    </div>
  );
}
