'use client';

import {
  JAM_MULAI,
  JAM_SELESAI,
  KECEPATAN,
  type WaktuSimulasi,
} from '@/lib/use-waktu-simulasi';

import { IkonJeda, IkonMain } from './ikon';

// Bar kontrol simulasi untuk demo, memanjang di bawah baris atas header. Jam besar ada di header.
export function WaktuKontrol({ waktu }: { waktu: WaktuSimulasi }) {
  const { simTime, isLive, isPlaying, kecepatan, aturJam, togglePlay, aturKecepatan, kembaliKeLive } = waktu;
  const berjalan = isLive || isPlaying;

  return (
    <section
      aria-label="Mode simulasi"
      className="flex h-[2.5rem] items-center gap-[0.6rem] rounded-2xl border-2 border-tj-oranye bg-orange-50 px-[0.7rem]"
    >
      <span className="whitespace-nowrap text-kecil font-bold text-tj-oranye">Mode simulasi</span>

      <button
        type="button"
        onClick={togglePlay}
        className="flex h-[2rem] w-[2rem] shrink-0 items-center justify-center rounded-full bg-tj-oranye text-white"
        aria-label={berjalan ? 'Jeda jam' : 'Jalankan jam'}
      >
        {berjalan ? <IkonJeda className="h-[1rem] w-[1rem]" /> : <IkonMain className="h-[1rem] w-[1rem]" />}
      </button>

      <input
        type="range"
        min={JAM_MULAI}
        max={JAM_SELESAI}
        step={60}
        value={Math.min(Math.max(simTime, JAM_MULAI), JAM_SELESAI)}
        onChange={(e) => aturJam(Number(e.target.value))}
        className="slider-jam h-[2rem] min-w-0 flex-1"
        aria-label="Geser jam simulasi"
      />

      <div className="flex shrink-0 items-center gap-[0.3rem]">
        {KECEPATAN.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => aturKecepatan(k)}
            aria-pressed={!isLive && kecepatan === k}
            className={`h-[2rem] min-w-[2.1rem] rounded-lg border-2 border-tj-oranye px-[0.3rem] text-kecil font-bold leading-none ${
              !isLive && kecepatan === k ? 'bg-tj-oranye text-white' : 'bg-white text-tj-oranye'
            }`}
          >
            {k}×
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={kembaliKeLive}
        disabled={isLive}
        aria-pressed={isLive}
        className={`h-[2rem] shrink-0 whitespace-nowrap rounded-lg px-[0.7rem] text-kecil font-bold leading-none ${
          isLive ? 'bg-tj-sepi text-white' : 'bg-tj-biru text-white'
        }`}
      >
        {isLive ? '● Waktu nyata' : 'Waktu nyata'}
      </button>
    </section>
  );
}
