'use client';

import Image from 'next/image';

import { Button } from '@/components/ui/button';

import { IkonCaretBawah, IkonCari, IkonLokasi } from './ikon';

type Props = {
  namaTujuan: string | null;
  // Daftar halte sudah dimuat; sebelum itu pemilih tujuan belum bisa dibuka.
  halteSiap: boolean;
  bisaCari: boolean;
  onPilihTujuan: () => void;
  onCari: () => void;
};

export function Beranda({ namaTujuan, halteSiap, bisaCari, onPilihTujuan, onCari }: Props) {
  return (
    <div className="layar-masuk mx-auto flex h-full w-full max-w-[42rem] flex-col justify-center gap-[1.2rem] pb-[1.5rem]">
      <div className="flex items-center gap-[1rem]">
        <div className="min-w-0 flex-1">
          <h1 className="text-balance text-judul font-bold leading-tight tracking-tight">Cari Rute Bus yang Nyaman</h1>
          <p className="mt-[0.5rem] text-besar leading-snug text-muted-foreground">
            Pilih perjalanan yang nyaman, TJ siap membantu Anda.
          </p>
        </div>
        {/* Bidang accent lembut di belakang ilustrasi 3D supaya menyatu dengan UI yang datar. */}
        <div className="relative w-[45%] max-w-[18rem] shrink-0">
          <div aria-hidden className="absolute inset-x-[4%] bottom-[2%] top-[18%] rounded-[50%] bg-accent" />
          <Image
            src="/maskot-bus.png"
            alt="Maskot kucing TransJakarta melambai dari pintu bus"
            width={2000}
            height={1250}
            priority
            sizes="18rem"
            className="relative h-auto w-full"
          />
        </div>
      </div>

      <div className="w-full space-y-[0.8rem]">
        <button
          type="button"
          onClick={onPilihTujuan}
          disabled={!halteSiap}
          aria-label={namaTujuan ? `Tujuan: ${namaTujuan}. Sentuh untuk mengganti` : 'Pilih tujuan'}
          className="flex w-full items-center gap-[0.9rem] rounded-xl border border-input bg-background px-[1.1rem] py-[0.6rem] text-left shadow-xs hover:bg-accent disabled:opacity-50"
        >
          <span className="flex size-[2.6rem] shrink-0 items-center justify-center rounded-lg bg-accent">
            <IkonLokasi className="h-[1.6rem] w-[1.6rem] text-primary" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-kecil font-medium leading-tight text-muted-foreground">Ke:</span>
            <span
              className={`block truncate text-besar font-bold leading-tight ${namaTujuan ? '' : 'font-medium text-muted-foreground'}`}
            >
              {namaTujuan ?? (halteSiap ? 'Sentuh untuk memilih tujuan…' : 'Memuat daftar halte…')}
            </span>
          </span>
          <IkonCaretBawah className="h-[1.3rem] w-[1.3rem] shrink-0 text-muted-foreground" />
        </button>

        <Button onClick={onCari} disabled={!bisaCari} className="h-[3.4rem] w-full rounded-xl text-besar font-bold">
          <IkonCari className="h-[1.6rem] w-[1.6rem]" />
          Cari Rute
        </Button>
      </div>
    </div>
  );
}
