'use client';

/* eslint-disable @next/next/no-img-element -- logo statis kecil; next/image tidak menambah nilai untuk kiosk */

import { MODE_DEMO } from '@/lib/api';
import { formatJam } from '@/lib/koridor';
import type { JamHalaman } from '@/lib/use-waktu-simulasi';

import { Badge } from '@/components/ui/badge';

import { IkonCaretBawah } from './ikon';

type Props = {
  namaHalte: string;
  onUbahHalte: () => void;
  // Daftar halte sudah dimuat; sebelum itu pemilih halte belum bisa dibuka.
  halteSiap: boolean;
  waktu: JamHalaman;
  tanggal: string;
};

// Baris atas: halte kiosk, logo, tanggal dan jam. Mode demo menambah ganti halte; jam simulasi diatur operator di /operator.
export function Header({ namaHalte, onUbahHalte, halteSiap, waktu, tanggal }: Props) {
  const simulasi = !waktu.isLive;
  return (
    <header className="shrink-0 border-b px-[1.4rem]">
      <div className="grid h-[3.6rem] grid-cols-[1fr_auto_1fr] items-center gap-[0.8rem]">
        {MODE_DEMO ? (
          <button
            type="button"
            onClick={onUbahHalte}
            disabled={!halteSiap}
            aria-label={`Halte asal: ${namaHalte}. Sentuh untuk mengganti`}
            className="-mx-[0.5rem] flex min-w-0 flex-col items-start justify-self-start rounded-lg px-[0.5rem] py-[0.1rem] text-left hover:bg-accent disabled:opacity-50"
          >
            <span className="text-kecil leading-tight text-muted-foreground">Anda di halte</span>
            <span className="flex max-w-full items-center gap-[0.3rem] text-besar font-bold leading-tight text-primary">
              <span className="truncate">{namaHalte}</span>
              <IkonCaretBawah className="h-[1.1rem] w-[1.1rem] shrink-0 text-muted-foreground" />
            </span>
          </button>
        ) : (
          // Kiosk terpasang di satu halte, jadi asal tidak bisa diganti pengguna.
          <div className="flex min-w-0 flex-col items-start justify-self-start">
            <span className="text-kecil leading-tight text-muted-foreground">Anda di halte</span>
            <span className="max-w-full truncate text-besar font-bold leading-tight text-primary">{namaHalte}</span>
          </div>
        )}

        <img src="/logo-transjakarta.png" alt="TransJakarta" className="h-[2.7rem] w-auto" />

        <div className="flex flex-col items-end justify-self-end">
          {simulasi ? (
            <Badge varian="peringatan" className="font-bold leading-tight">
              SIMULASI
            </Badge>
          ) : (
            <div className="whitespace-nowrap text-kecil leading-tight text-muted-foreground">{tanggal}</div>
          )}
          <div className={`text-jam font-bold leading-none tabular-nums ${simulasi ? 'text-tj-oranye' : 'text-primary'}`}>
            {formatJam(waktu.simTime)}
          </div>
        </div>
      </div>
    </header>
  );
}
