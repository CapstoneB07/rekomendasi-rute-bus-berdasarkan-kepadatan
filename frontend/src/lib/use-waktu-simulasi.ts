'use client';

import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE, waktuWib } from '@/lib/api';

// Jam layanan yang bisa dipilih di slider.
export const JAM_MULAI = 5 * 3600;
export const JAM_SELESAI = 23 * 3600;
export const KECEPATAN = [1, 5, 10, 60] as const;

// Keadaan jam yang dibagikan operator ke kiosk lewat backend (/api/waktu), antar perangkat.
// Berupa jangkar (simTime pada saat `ts`), bukan hitungan per detik, supaya perangkat yang
// tertahan di latar belakang tetap akurat: jam sekarang selalu dihitung dari waktu dinding.
export type KeadaanWaktu = {
  isLive: boolean;
  isPlaying: boolean;
  kecepatan: number;
  simTime: number;
  ts: number;
};

// Polling kiosk; jam berjalan sendiri di antara polling, jadi ini hanya latensi perubahan dari operator.
const POLLING_WAKTU_MS = 2_000;
const LIVE_AWAL: KeadaanWaktu = { isLive: true, isPlaying: true, kecepatan: 1, simTime: JAM_MULAI, ts: 0 };

export function hitungSimTime(k: KeadaanWaktu, sekarang: number): number {
  if (k.isLive) return waktuWib(new Date(sekarang)).detik;
  if (!k.isPlaying) return k.simTime;
  const rentang = JAM_SELESAI - JAM_MULAI;
  const maju = Math.floor(((sekarang - k.ts) / 1000) * k.kecepatan);
  const dalamRentang = Math.min(Math.max(k.simTime, JAM_MULAI), JAM_SELESAI) - JAM_MULAI;
  return JAM_MULAI + ((((dalamRentang + maju) % rentang) + rentang) % rentang);
}

// Jam yang dihitung ulang tiap detik dari jangkar. Nilai awal tetap supaya render server dan klien sama.
function useJam(keadaan: KeadaanWaktu, selisihMs = 0) {
  const [simTime, setSimTime] = useState(JAM_MULAI);
  useEffect(() => {
    const tick = () => setSimTime(hitungSimTime(keadaan, Date.now() + selisihMs));
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [keadaan, selisihMs]);
  return simTime;
}

export type WaktuSimulasi = ReturnType<typeof useWaktuOperator>;
export type JamHalaman = Pick<WaktuSimulasi, 'simTime' | 'isLive'>;

// Jam milik operator: bisa digeser, dijeda, dipercepat; setiap perubahan dipublikasikan untuk halaman kiosk.
export function useWaktuOperator() {
  const [keadaan, setKeadaan] = useState<KeadaanWaktu>(LIVE_AWAL);
  const simTime = useJam(keadaan);

  // Publikasikan tiap perubahan ke backend; false = kiosk tidak menerima jam operator.
  const [tersinkron, setTersinkron] = useState<boolean | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    kirimKeadaan(keadaan, abort.signal)
      .then(() => setTersinkron(true))
      .catch(() => !abort.signal.aborted && setTersinkron(false));
    return () => abort.abort();
  }, [keadaan]);

  // Jangkar baru dimulai dari jam saat ini.
  const ubah = useCallback((f: (k: KeadaanWaktu, sekarangSim: number) => Partial<KeadaanWaktu>) => {
    setKeadaan((k) => {
      const sekarang = Date.now();
      return { ...k, ...f(k, hitungSimTime(k, sekarang)), ts: sekarang };
    });
  }, []);

  // Menggeser jam keluar dari mode live; jam berhenti/jalan sesuai state terakhir.
  const aturJam = useCallback((detik: number) => ubah(() => ({ isLive: false, simTime: detik })), [ubah]);

  // Jeda saat live = bekukan jam di waktu sekarang sebagai simulasi.
  const togglePlay = useCallback(
    () =>
      ubah((k, sim) =>
        k.isLive ? { isLive: false, isPlaying: false, simTime: sim } : { isPlaying: !k.isPlaying, simTime: sim },
      ),
    [ubah],
  );

  const aturKecepatan = useCallback(
    (kecepatan: number) => ubah((_, sim) => ({ isLive: false, isPlaying: true, kecepatan, simTime: sim })),
    [ubah],
  );

  const kembaliKeLive = useCallback(() => ubah(() => ({ isLive: true, isPlaying: true, kecepatan: 1 })), [ubah]);

  return {
    simTime,
    isLive: keadaan.isLive,
    isPlaying: keadaan.isPlaying,
    kecepatan: keadaan.kecepatan,
    tersinkron,
    aturJam,
    togglePlay,
    aturKecepatan,
    kembaliKeLive,
  };
}

type KeadaanApi = { is_live: boolean; is_playing: boolean; kecepatan: number; sim_time: number; ts: number };
type ResponsWaktu = { keadaan: KeadaanApi; server_now: number };

function dariApi(k: KeadaanApi): KeadaanWaktu {
  return { isLive: k.is_live, isPlaying: k.is_playing, kecepatan: k.kecepatan, simTime: k.sim_time, ts: k.ts };
}

async function kirimKeadaan(k: KeadaanWaktu, signal: AbortSignal) {
  const r = await fetch(`${API_BASE}/api/waktu`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_live: k.isLive, is_playing: k.isPlaying, kecepatan: k.kecepatan, sim_time: k.simTime }),
    signal,
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

// Jam halaman kiosk: mengikuti operator di perangkat mana pun lewat backend; tanpa operator, jam nyata WIB (live).
export function useWaktuIkut(): JamHalaman {
  const { data } = useQuery({
    queryKey: ['waktu-bersama'],
    queryFn: async () => {
      const t0 = Date.now();
      const r = await fetch(`${API_BASE}/api/waktu`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const { keadaan, server_now }: ResponsWaktu = await r.json();
      // Selisih jam perangkat ini terhadap server, dengan menganggap latensi simetris.
      return { keadaan: dariApi(keadaan), selisihMs: server_now - (t0 + Date.now()) / 2 };
    },
    refetchInterval: POLLING_WAKTU_MS,
  });
  const keadaan = data?.keadaan ?? LIVE_AWAL;
  return { simTime: useJam(keadaan, data?.selisihMs ?? 0), isLive: keadaan.isLive };
}
