'use client';

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import { daftarKelompok, filterKelompok, halaman, KELOMPOK_UTAMA } from '@/lib/pilih-halte';
import type { HalteOpsi } from '@/lib/route-utils';

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
      className="layar-masuk fixed inset-0 z-50 flex flex-col gap-[0.6rem] bg-white px-[1.6rem] pb-[1rem] pt-[0.8rem] outline-none"
    >
      <div className="flex items-center gap-[1rem]">
        <button
          type="button"
          onClick={onTutup}
          className="flex h-[2.8rem] items-center gap-[0.5rem] rounded-xl border-2 border-tj-biru px-[1rem] text-isi font-bold text-tj-biru"
        >
          <IkonPanahKiri className="h-[1.3rem] w-[1.3rem]" />
          Kembali
        </button>
        <h2 className="text-judul font-bold text-tj-biru">{judul}</h2>
      </div>

      <div role="tablist" aria-label="Kelompok halte" className="flex flex-wrap gap-[0.4rem]">
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
            className={`h-[2.4rem] min-w-[2.4rem] rounded-lg border-2 px-[0.6rem] text-isi font-bold ${
              k === kelompok
                ? 'border-tj-biru bg-tj-biru text-white'
                : 'border-tj-garis bg-white text-tj-biru'
            }`}
          >
            {k === KELOMPOK_UTAMA ? '★ Utama' : k}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-4 grid-rows-3 gap-[0.6rem]">
        {items.map((h) => {
          const nonaktif = h.nama === nonaktifNama;
          const terpilih = h.halte_id === terpilihId;
          return (
            <button
              key={h.halte_id}
              type="button"
              disabled={nonaktif}
              onClick={() => onPilih(h.halte_id)}
              className={`flex min-h-0 flex-col items-center justify-center rounded-xl border-2 px-[0.6rem] text-center text-isi font-bold leading-tight ${
                nonaktif
                  ? 'border-tj-garis bg-gray-100 text-gray-600'
                  : terpilih
                    ? 'border-tj-biru bg-tj-biru text-white'
                    : 'border-tj-garis bg-tj-biru-muda text-tj-biru'
              }`}
            >
              <span className="line-clamp-2">{h.nama}</span>
              {nonaktif && nonaktifAlasan && <span className="text-kecil font-medium">{nonaktifAlasan}</span>}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[1rem]">
        <button
          type="button"
          disabled={idxAman === 0}
          onClick={() => setIdx(idxAman - 1)}
          className="flex h-[2.8rem] items-center gap-[0.5rem] justify-self-start rounded-xl bg-tj-biru px-[1.4rem] text-isi font-bold text-white disabled:opacity-30"
        >
          <IkonChevronKanan className="h-[1.2rem] w-[1.2rem] rotate-180" />
          Sebelumnya
        </button>
        <span className="text-isi text-tj-teks">
          Halaman {idxAman + 1} dari {jumlah}
        </span>
        <button
          type="button"
          disabled={idxAman >= jumlah - 1}
          onClick={() => setIdx(idxAman + 1)}
          className="flex h-[2.8rem] items-center gap-[0.5rem] justify-self-end rounded-xl bg-tj-biru px-[1.4rem] text-isi font-bold text-white disabled:opacity-30"
        >
          Berikutnya
          <IkonChevronKanan className="h-[1.2rem] w-[1.2rem]" />
        </button>
      </div>
    </div>
  );
}
