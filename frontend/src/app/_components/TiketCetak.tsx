'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';

import type { Tiket } from '@/lib/tiket';

import { IkonCetak } from './ikon';

function Baris({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div className="tiket-baris">
      <span>{label}</span>
      <b>{nilai}</b>
    </div>
  );
}

// Pratinjau tiket. Dipasang langsung di <body> supaya CSS cetak cukup menyembunyikan
// saudara-saudaranya (seluruh UI kiosk) dan hanya struk ini yang tercetak.
export function TiketCetak({ tiket, onTutup }: { tiket: Tiket; onTutup: () => void }) {
  useEffect(() => {
    const tutup = (e: KeyboardEvent) => e.key === 'Escape' && onTutup();
    window.addEventListener('keydown', tutup);
    return () => window.removeEventListener('keydown', tutup);
  }, [onTutup]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Tiket perjalanan"
      className="area-cetak fixed inset-0 z-[50] flex flex-col items-center justify-center gap-[1rem] bg-black/60 p-[1rem]"
    >
      <article className="tiket">
        <header className="tiket-kepala">
          <b>TransJakarta Lega</b>
          <span>Tiket Rencana Perjalanan</span>
        </header>
        <div className="tiket-garis" />
        <Baris label="No. tiket" nilai={tiket.nomor} />
        <Baris label="Dicetak" nilai={tiket.dicetak} />
        <div className="tiket-garis" />
        <Baris label="Dari" nilai={tiket.asal} />
        <Baris label="Ke" nilai={tiket.tujuan} />
        <Baris label="Berangkat" nilai={tiket.berangkat} />
        <Baris label="Tiba (perkiraan)" nilai={tiket.tiba} />
        <Baris label="Estimasi" nilai={`${tiket.estimasiMenit} menit`} />
        <Baris label="Transit" nilai={tiket.jumlahTransit === 0 ? 'Langsung' : `${tiket.jumlahTransit}x`} />
        <div className="tiket-garis" />
        <ol className="tiket-langkah">
          {tiket.langkah.map((l, i) =>
            l.tipe === 'naik' ? (
              <li key={i}>
                <b>
                  Koridor {l.koridor}
                  {l.bus && ` · Bus ${l.bus}`}
                </b>
                <Baris label={`Naik ${l.naikDi}`} nilai={l.jamNaik} />
                <Baris label={`Turun ${l.turunDi}`} nilai={l.jamTurun} />
              </li>
            ) : (
              <li key={i} className="tiket-transit">
                Pindah di {l.di} ke koridor {l.keKoridor}
              </li>
            ),
          )}
        </ol>
        <div className="tiket-garis" />
        <p className="tiket-kaki">Jam bersifat perkiraan dan dapat berubah. Selamat jalan!</p>
      </article>

      <div className="tiket-aksi flex w-full max-w-[24rem] gap-[0.8rem]">
        <button
          type="button"
          onClick={onTutup}
          className="h-[2.8rem] flex-1 rounded-xl border-2 border-white text-isi font-bold text-white"
        >
          Tutup
        </button>
        <button
          type="button"
          autoFocus
          onClick={() => window.print()}
          className="flex h-[2.8rem] flex-1 items-center justify-center gap-[0.6rem] rounded-xl bg-tj-biru text-isi font-bold text-white"
        >
          <IkonCetak className="h-[1.4rem] w-[1.4rem]" />
          Cetak
        </button>
      </div>
    </div>,
    document.body,
  );
}
