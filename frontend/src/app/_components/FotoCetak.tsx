'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { Button } from '@/components/ui/button';
import { ambilSnapshot, buatFotoThermal, pesanGalatFoto, type FotoThermal } from '@/lib/photobox';
import { nomorTiket } from '@/lib/tiket';

import { IkonCetak } from './ikon';

type Hasil = { status: 'memuat' } | { status: 'galat'; pesan: string } | { status: 'siap'; foto: FotoThermal; bus: string; direkam: string; nomor: string };

const WAKTU_WIB = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jakarta', dateStyle: 'short', timeStyle: 'medium', hourCycle: 'h23' });

// Photobox: ambil frame + bbox terbaru, tampilkan pratinjau 1-bit, lalu cetak ke struk thermal.
// Dipasang di <body> dengan kelas .area-cetak, sama seperti TiketCetak, sehingga CSS cetak hanya mencetak struk ini.
export function FotoCetak({ onTutup }: { onTutup: () => void }) {
  const [hasil, setHasil] = useState<Hasil>({ status: 'memuat' });
  const [percobaan, setPercobaan] = useState(0);

  useEffect(() => {
    let batal = false;
    ambilSnapshot()
      .then(async (snap) => {
        const foto = await buatFotoThermal(snap);
        if (batal) return;
        const waktu = new Date(snap.updated_at);
        setHasil({ status: 'siap', foto, bus: snap.bus_id, direkam: WAKTU_WIB.format(waktu), nomor: nomorTiket(new Date()) });
      })
      .catch((err) => !batal && setHasil({ status: 'galat', pesan: pesanGalatFoto(err) }));
    return () => {
      batal = true;
    };
  }, [percobaan]);

  useEffect(() => {
    const tutup = (e: KeyboardEvent) => e.key === 'Escape' && onTutup();
    window.addEventListener('keydown', tutup);
    return () => window.removeEventListener('keydown', tutup);
  }, [onTutup]);

  const ulangi = () => {
    setHasil({ status: 'memuat' });
    setPercobaan((n) => n + 1);
  };
  const cetak = () => {
    // Dengan --kiosk-printing tidak ada dialog yang bisa dibatalkan; tutup setelah cetak dikirim supaya satu tekan = satu foto.
    window.addEventListener('afterprint', onTutup, { once: true });
    window.print();
  };

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Cetak foto kamera"
      className="area-cetak fixed inset-0 z-[50] flex flex-col items-center justify-center gap-[1rem] bg-black/50 p-[1rem] backdrop-blur-sm"
    >
      {hasil.status === 'siap' ? (
        <article className="tiket rounded-lg shadow-lg">
          <header className="tiket-kepala">
            <b>TransJakarta Lega</b>
            <span>Foto Kamera Bus</span>
          </header>
          <div className="tiket-garis" />
          {/* Data URL hasil canvas: next/image tidak berguna, dan harus tercetak 1:1 per dot. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={hasil.foto.dataUrl} alt="Foto kamera bus beserta kotak deteksi" width={hasil.foto.lebar} height={hasil.foto.tinggi} className="foto-cetak" />
          <div className="tiket-garis" />
          <div className="tiket-baris">
            <span>Terdeteksi</span>
            <b>{hasil.foto.jumlahDeteksi} penumpang</b>
          </div>
          <div className="tiket-baris">
            <span>Bus</span>
            <b>{hasil.bus}</b>
          </div>
          <div className="tiket-baris">
            <span>Direkam</span>
            <b>{hasil.direkam}</b>
          </div>
          <div className="tiket-baris">
            <span>No.</span>
            <b>{hasil.nomor}</b>
          </div>
        </article>
      ) : (
        <p role="status" className="tiket-aksi max-w-[24rem] rounded-lg bg-background px-[1rem] py-[0.8rem] text-center text-isi shadow-lg">
          {hasil.status === 'memuat' ? 'Mengambil foto…' : hasil.pesan}
        </p>
      )}

      <div className="tiket-aksi flex w-full max-w-[24rem] gap-[0.8rem]">
        <Button varian="outline" ukuran="lg" onClick={onTutup} className="flex-1">
          Tutup
        </Button>
        <Button varian="outline" ukuran="lg" onClick={ulangi} disabled={hasil.status === 'memuat'} className="flex-1">
          Ulangi
        </Button>
        <Button ukuran="lg" autoFocus onClick={cetak} disabled={hasil.status !== 'siap'} className="flex-1 font-bold">
          <IkonCetak className="h-[1.4rem] w-[1.4rem]" />
          Cetak
        </Button>
      </div>
    </div>,
    document.body,
  );
}
