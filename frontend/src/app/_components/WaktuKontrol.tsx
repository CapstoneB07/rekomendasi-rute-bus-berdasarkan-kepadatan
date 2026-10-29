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
      className="flex h-[2.6rem] items-center gap-[0.6rem] rounded-xl border bg-card px-[0.7rem] shadow-sm hp:h-auto hp:flex-wrap hp:py-[0.4rem]"
    >
      <span className={cn('whitespace-nowrap text-kecil font-bold', isLive ? 'text-muted-foreground' : 'text-tj-oranye')}>
        {isLive ? 'Simulasi' : 'Mode simulasi'}
      </span>

      <Button
        ukuran="icon"
        varian={isLive ? 'outline' : 'default'}
        onClick={togglePlay}
        className={cn(!isLive && 'bg-tj-oranye hover:bg-tj-oranye/90')}
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
        className={cn('slider-jam h-[2rem] min-w-0 flex-1 hp:order-last hp:basis-full', isLive && 'slider-jam-live')}
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
              'h-[2rem] min-w-[2.2rem] rounded-md px-[0.3rem] text-kecil font-medium leading-none text-muted-foreground',
              !isLive && kecepatan === k && 'bg-background font-bold text-tj-oranye shadow-sm',
            )}
          >
            {k}×
          </button>
        ))}
      </div>

      <Button
        ukuran="sm"
        varian="outline"
        onClick={kembaliKeLive}
        disabled={isLive}
        aria-pressed={isLive}
        className={cn('font-bold', isLive && 'disabled:opacity-100')}
      >
        {isLive && <span aria-hidden className="size-[0.5rem] rounded-full bg-tj-sepi" />}
        Waktu nyata
      </Button>
    </section>
  );
}
