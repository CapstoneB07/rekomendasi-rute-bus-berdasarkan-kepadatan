'use client';

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';

import { waktuWib } from '@/lib/api';

// Jam layanan yang bisa dipilih di slider.
export const JAM_MULAI = 5 * 3600;
export const JAM_SELESAI = 23 * 3600;
export const KECEPATAN = [1, 5, 10, 60] as const;

// Keadaan jam yang dibagikan operator ke halaman kiosk lewat localStorage (satu browser, beberapa tab).
// Berupa jangkar (simTime pada saat `ts`), bukan hitungan per detik, supaya tab yang tertahan di latar
// belakang tetap akurat: jam sekarang selalu dihitung dari waktu dinding.
export type KeadaanWaktu = {
  isLive: boolean;
  isPlaying: boolean;
  kecepatan: number;
  simTime: number;
  ts: number;
};

const KUNCI_WAKTU = 'tj-waktu-simulasi';
const LIVE_AWAL: KeadaanWaktu = { isLive: true, isPlaying: true, kecepatan: 1, simTime: JAM_MULAI, ts: 0 };

export function hitungSimTime(k: KeadaanWaktu, sekarang: number): number {
  if (k.isLive) return waktuWib(new Date(sekarang)).detik;
  if (!k.isPlaying) return k.simTime;
  const rentang = JAM_SELESAI - JAM_MULAI;
  const maju = Math.floor(((sekarang - k.ts) / 1000) * k.kecepatan);
  const dalamRentang = Math.min(Math.max(k.simTime, JAM_MULAI), JAM_SELESAI) - JAM_MULAI;
  return JAM_MULAI + ((((dalamRentang + maju) % rentang) + rentang) % rentang);
}

export function bacaKeadaanWaktu(mentah: string | null): KeadaanWaktu {
  try {
    const k = mentah ? JSON.parse(mentah) : null;
    if (
      typeof k?.isLive === 'boolean' &&
      typeof k.isPlaying === 'boolean' &&
      Number.isFinite(k.kecepatan) &&
      Number.isFinite(k.simTime) &&
      Number.isFinite(k.ts)
    ) {
      return k;
    }
  } catch {
    // JSON rusak: jatuh ke live.
  }
  return LIVE_AWAL;
}

// Jam yang dihitung ulang tiap detik dari jangkar. Nilai awal tetap supaya render server dan klien sama.
function useJam(keadaan: KeadaanWaktu) {
  const [simTime, setSimTime] = useState(JAM_MULAI);
  useEffect(() => {
    const tick = () => setSimTime(hitungSimTime(keadaan, Date.now()));
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [keadaan]);
  return simTime;
}

export type WaktuSimulasi = ReturnType<typeof useWaktuOperator>;
export type JamHalaman = Pick<WaktuSimulasi, 'simTime' | 'isLive'>;

// Jam milik operator: bisa digeser, dijeda, dipercepat; setiap perubahan dipublikasikan untuk halaman kiosk.
export function useWaktuOperator() {
  const [keadaan, setKeadaan] = useState<KeadaanWaktu>(LIVE_AWAL);
  const simTime = useJam(keadaan);

  useEffect(() => {
    try {
      localStorage.setItem(KUNCI_WAKTU, JSON.stringify(keadaan));
    } catch {
      // Penyimpanan diblokir: operator tetap jalan, kiosk tidak bisa mengikuti.
    }
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
    aturJam,
    togglePlay,
    aturKecepatan,
    kembaliKeLive,
  };
}

function langganan(onUbah: () => void) {
  const saatStorage = (e: StorageEvent) => {
    if (e.key === KUNCI_WAKTU || e.key === null) onUbah();
  };
  window.addEventListener('storage', saatStorage);
  return () => window.removeEventListener('storage', saatStorage);
}

function bacaMentah(): string | null {
  try {
    return localStorage.getItem(KUNCI_WAKTU);
  } catch {
    return null;
  }
}

// Jam halaman kiosk: mengikuti operator di tab lain; tanpa operator, jam nyata WIB (live).
export function useWaktuIkut(): JamHalaman {
  const mentah = useSyncExternalStore(langganan, bacaMentah, () => null);
  const keadaan = useMemo(() => bacaKeadaanWaktu(mentah), [mentah]);
  return { simTime: useJam(keadaan), isLive: keadaan.isLive };
}
