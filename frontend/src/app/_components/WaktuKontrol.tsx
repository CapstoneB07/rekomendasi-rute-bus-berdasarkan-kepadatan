'use client';

import {
  JAM_MULAI,
  JAM_SELESAI,
  KECEPATAN,
  type WaktuSimulasi,
} from '@/lib/use-waktu-simulasi';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { IkonJeda, IkonMain } from './ikon';

// Bar kontrol simulasi untuk demo, memanjang di bawah baris atas header. Jam besar ada di header.
export function WaktuKontrol({ waktu }: { waktu: WaktuSimulasi }) {
  const { simTime, isLive, isPlaying, kecepatan, aturJam, togglePlay, aturKecepatan, kembaliKeLive } = waktu;
  const berjalan = isLive || isPlaying;

  return (
    <section
      aria-label="Mode simulasi"
      className="flex h-[2.6rem] items-center gap-[0.6rem] rounded-xl border bg-card px-[0.7rem] shadow-sm"
    >
      <span className="whitespace-nowrap text-kecil font-bold text-tj-oranye">Mode simulasi</span>

      <Button
        ukuran="icon"
        onClick={togglePlay}
        className="rounded-full bg-tj-oranye hover:bg-tj-oranye/90"
        aria-label={berjalan ? 'Jeda jam' : 'Jalankan jam'}
      >
        {berjalan ? <IkonJeda className="h-[1rem] w-[1rem]" /> : <IkonMain className="h-[1rem] w-[1rem]" />}
      </Button>

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

      {/* Grup toggle ala shadcn/ui. */}
      <div className="flex shrink-0 items-center gap-[0.15rem] rounded-lg bg-muted p-[0.15rem]">
        {KECEPATAN.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => aturKecepatan(k)}
            aria-pressed={!isLive && kecepatan === k}
            className={cn(
              'h-[1.8rem] min-w-[2.1rem] rounded-md px-[0.3rem] text-kecil font-medium leading-none text-muted-foreground',
              !isLive && kecepatan === k && 'bg-background font-bold text-tj-oranye shadow-sm',
            )}
          >
            {k}×
          </button>
        ))}
      </div>

      <Button
        ukuran="sm"
        varian={isLive ? 'default' : 'outline'}
        onClick={kembaliKeLive}
        disabled={isLive}
        aria-pressed={isLive}
        className={cn('font-bold', isLive && 'bg-tj-sepi disabled:opacity-100')}
      >
        {isLive ? '● Waktu nyata' : 'Waktu nyata'}
      </Button>
    </section>
  );
}
