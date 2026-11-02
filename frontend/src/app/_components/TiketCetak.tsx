'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { kirimKePrinter, pesanGalatCetak } from '@/lib/cetak';
import { teksBusKe } from '@/lib/route-utils';
import { barisCetakTiket, type Tiket } from '@/lib/tiket';

import { Button } from '@/components/ui/button';

import { IkonCetak } from './ikon';

function Baris({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div className="tiket-baris">
      <span>{label}</span>
      <b>{nilai}</b>
    </div>
  );
}

// Pratinjau tiket. Dipasang langsung di <body> supaya CSS cetak cukup menyembunyikan saudara-saudaranya (seluruh UI kiosk) dan hanya struk ini yang tercetak.
export function TiketCetak({ tiket, onTutup }: { tiket: Tiket; onTutup: () => void }) {
  const [mencetak, setMencetak] = useState(false);
  const [galat, setGalat] = useState<string | null>(null);

  const cetak = async () => {
    setMencetak(true);
    setGalat(null);
    try {
      // Printer Bluetooth tidak punya driver Windows, jadi isi tiket dikirim ke backend yang menulis ESC/POS ke port COM-nya.
      await kirimKePrinter('/api/print/tiket', { baris: barisCetakTiket(tiket) });
      onTutup();
    } catch (err) {
      setGalat(pesanGalatCetak(err, 'Tiket'));
      setMencetak(false);
    }
  };

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
      className="area-cetak fixed inset-0 z-[50] flex flex-col items-center justify-center gap-[1rem] bg-black/50 p-[1rem] backdrop-blur-sm"
    >
      <article className="tiket rounded-lg shadow-lg">
        <header className="tiket-kepala">
          <b>Tiket Rencana Perjalanan</b>
        </header>
        <div className="tiket-garis" />
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
                  {teksBusKe(l.busKe) && ` · ${teksBusKe(l.busKe)}`}
                </b>
                <Baris label={`Naik - ${l.naikDi}`} nilai={l.jamNaik} />
                <Baris label={`Turun - ${l.turunDi}`} nilai={l.jamTurun} />
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

      {galat && (
        <p role="alert" className="tiket-aksi max-w-[24rem] rounded-lg bg-background px-[1rem] py-[0.8rem] text-center text-isi text-destructive shadow-lg">
          {galat}
        </p>
      )}

      <div className="tiket-aksi flex w-full max-w-[24rem] gap-[0.8rem]">
        <Button varian="outline" ukuran="lg" onClick={onTutup} className="flex-1">
          Tutup
        </Button>
        <Button ukuran="lg" autoFocus onClick={cetak} disabled={mencetak} className="flex-1 font-bold">
          <IkonCetak className="h-[1.4rem] w-[1.4rem]" />
          {mencetak ? 'Mencetak…' : 'Cetak'}
        </Button>
      </div>
    </div>,
    document.body,
  );
}
