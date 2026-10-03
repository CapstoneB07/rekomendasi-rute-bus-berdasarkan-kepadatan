'use client';

import { useCallback, useEffect, useState } from 'react';

import { waktuWib } from '@/lib/api';

// Jam layanan yang bisa dipilih di slider.
export const JAM_MULAI = 5 * 3600;
export const JAM_SELESAI = 23 * 3600;
export const KECEPATAN = [1, 5, 10, 60] as const;

export type WaktuSimulasi = ReturnType<typeof useWaktuSimulasi>;

// Jam yang dipakai seluruh halaman: mengikuti jam nyata WIB (mode `live`) atau
// jam simulasi yang bisa digeser, dijeda, dan dipercepat.
export function useWaktuSimulasi() {
  const [isLive, setIsLive] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [kecepatan, setKecepatan] = useState<number>(1);
  // Nilai awal tetap (bukan jam nyata) supaya render server dan klien sama;
  // jam nyata masuk lewat tick pertama setelah mount.
  const [simTime, setSimTime] = useState(JAM_MULAI);

  useEffect(() => {
    if (!isLive && !isPlaying) return;
    const tick = () => {
      if (isLive) {
        setSimTime(waktuWib().detik);
      } else {
        setSimTime((t) => (t + kecepatan >= JAM_SELESAI ? JAM_MULAI : t + kecepatan));
      }
    };
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [isLive, isPlaying, kecepatan]);

  // Menggeser jam keluar dari mode live; jam berhenti/jalan sesuai state terakhir.
  const aturJam = useCallback((detik: number) => {
    setIsLive(false);
    setSimTime(detik);
  }, []);

  const togglePlay = useCallback(() => {
    if (isLive) {
      // Jeda saat live = bekukan jam di waktu sekarang sebagai simulasi.
      setIsLive(false);
      setIsPlaying(false);
    } else {
      setIsPlaying((p) => !p);
    }
  }, [isLive]);

  const aturKecepatan = useCallback((k: number) => {
    setIsLive(false);
    setIsPlaying(true);
    setKecepatan(k);
  }, []);

  const kembaliKeLive = useCallback(() => {
    setIsLive(true);
    setIsPlaying(true);
    setKecepatan(1);
  }, []);

  return { simTime, isLive, isPlaying, kecepatan, aturJam, togglePlay, aturKecepatan, kembaliKeLive };
}
