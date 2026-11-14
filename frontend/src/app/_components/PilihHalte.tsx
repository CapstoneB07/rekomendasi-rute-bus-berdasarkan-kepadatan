'use client';

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import { daftarKelompok, filterKelompok, halaman, KELOMPOK_UTAMA } from '@/lib/pilih-halte';
import type { HalteOpsi } from '@/lib/route-utils';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { IkonChevronKanan, IkonPanahKiri } from './ikon';

const PER_HALAMAN = 12; // 4 kolom x 3 baris

type Props = {
  judul: string;
  halteList: HalteOpsi[];
  // Nama halte yang tidak boleh dipilih (halte lawan: asal tidak boleh sama dengan tujuan).
  nonaktifNama?: string | null;
  // Alasan halte nonaktif, ditampilkan di kartunya (mis. "Halte asal").
  nonaktifAlasan?: string;
  terpilihId?: string | null;
  onPilih: (halteId: string) => void;
  onTutup: () => void;
};

// Layar penuh pemilih halte untuk jari: kelompok huruf + grid kartu besar + halaman, tanpa papan ketik/scroll.
export function PilihHalte({ judul, halteList, nonaktifNama, nonaktifAlasan, terpilihId, onPilih, onTutup }: Props) {
  const kelompokAda = useMemo(() => daftarKelompok(halteList), [halteList]);
  const [kelompok, setKelompok] = useState(kelompokAda[0] ?? KELOMPOK_UTAMA);
  const [idx, setIdx] = useState(0);

  const { items, idx: idxAman, jumlah } = halaman(filterKelompok(halteList, kelompok), idx, PER_HALAMAN);

  // Dialog modal: fokus masuk saat dibuka dan kembali ke pemicu saat ditutup; Tab tidak keluar; Escape menutup.
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const pemicu = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => pemicu?.focus?.();
  }, []);
  const saatTombol = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onTutup();
      return;
    }
    if (e.key !== 'Tab') return;
    const fokus = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled)');
    if (!fokus?.length) return;
    const awal = fokus[0];
    const akhir = fokus[fokus.length - 1];
    const aktif = document.activeElement;
    if (e.shiftKey && (aktif === awal || aktif === dialogRef.current)) {
      e.preventDefault();
      akhir.focus();
    } else if (!e.shiftKey && aktif === akhir) {
      e.preventDefault();
      awal.focus();
    }
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={judul}
      tabIndex={-1}
      onKeyDown={saatTombol}
      className="layar-masuk fixed inset-0 z-50 flex flex-col gap-[0.7rem] bg-background px-[1.6rem] pb-[1rem] pt-[0.8rem] outline-none hp:px-[1rem]"
    >
      <div className="flex items-center gap-[1rem]">
        <Button varian="outline" ukuran="lg" onClick={onTutup}>
          <IkonPanahKiri className="h-[1.3rem] w-[1.3rem]" />
          Kembali
        </Button>
        <h2 className="text-judul font-bold tracking-tight hp:text-besar">{judul}</h2>
      </div>

      {/* Tab ala shadcn/ui: wadah abu-abu, tab aktif terangkat putih. */}
      <div
        role="tablist"
        aria-label="Kelompok halte"
        className="flex flex-wrap gap-[0.2rem] self-start rounded-xl bg-muted p-[0.25rem]"
      >
        {kelompokAda.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={k === kelompok}
            onClick={() => {
              setKelompok(k);
              setIdx(0);
            }}
            className={cn(
              'h-[2.3rem] min-w-[2.3rem] rounded-lg px-[0.6rem] text-isi font-medium text-muted-foreground',
              k === kelompok && 'bg-background font-bold text-foreground shadow-sm',
            )}
          >
            {k === KELOMPOK_UTAMA ? '★ Utama' : k}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-4 grid-rows-3 gap-[0.6rem] hp:grid-cols-2 hp:grid-rows-6">
        {items.map((h) => {
          const nonaktif = h.nama === nonaktifNama;
          const terpilih = h.halte_id === terpilihId;
          return (
            <button
              key={h.halte_id}
              type="button"
              disabled={nonaktif}
              onClick={() => onPilih(h.halte_id)}
              className={cn(
                'flex min-h-0 flex-col items-center justify-center rounded-xl border px-[0.6rem] text-center text-isi font-bold leading-tight shadow-xs',
                nonaktif
                  ? 'border-dashed bg-muted text-muted-foreground shadow-none'
                  : terpilih
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'bg-card hover:bg-accent hover:text-accent-foreground',
              )}
            >
              <span className="line-clamp-2">{h.nama}</span>
              {nonaktif && nonaktifAlasan && <span className="text-kecil font-medium">{nonaktifAlasan}</span>}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[1rem]">
        <Button
          varian="outline"
          ukuran="lg"
          disabled={idxAman === 0}
          onClick={() => setIdx(idxAman - 1)}
          className="justify-self-start px-[1.4rem] hp:px-[0.9rem]"
        >
          <IkonChevronKanan className="h-[1.2rem] w-[1.2rem] rotate-180" />
          <span className="hp:sr-only">Sebelumnya</span>
        </Button>
        <span className="text-isi text-muted-foreground">
          Halaman {idxAman + 1} dari {jumlah}
        </span>
        <Button
          varian="outline"
          ukuran="lg"
          disabled={idxAman >= jumlah - 1}
          onClick={() => setIdx(idxAman + 1)}
          className="justify-self-end px-[1.4rem] hp:px-[0.9rem]"
        >
          <span className="hp:sr-only">Berikutnya</span>
          <IkonChevronKanan className="h-[1.2rem] w-[1.2rem]" />
        </Button>
      </div>
    </div>
  );
}
