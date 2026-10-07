'use client';

/* eslint-disable @next/next/no-img-element -- logo statis kecil; next/image tidak menambah nilai untuk kiosk */

import { MODE_DEMO } from '@/lib/api';
import { formatJam } from '@/lib/koridor';
import type { WaktuSimulasi } from '@/lib/use-waktu-simulasi';

import { IkonCaretBawah } from './ikon';
import { WaktuKontrol } from './WaktuKontrol';

type Props = {
  namaHalte: string;
  onUbahHalte: () => void;
  // Daftar halte sudah dimuat; sebelum itu pemilih halte belum bisa dibuka.
  halteSiap: boolean;
  waktu: WaktuSimulasi;
  tanggal: string;
};

// Baris atas: halte kiosk, logo, tanggal dan jam. Mode demo menambah ganti halte dan bar mode simulasi.
export function Header({ namaHalte, onUbahHalte, halteSiap, waktu, tanggal }: Props) {
  const simulasi = MODE_DEMO && !waktu.isLive;
  return (
    <header className="shrink-0 space-y-[0.2rem] px-[1.4rem]">
      <div className="grid h-[3.6rem] grid-cols-[1fr_auto_1fr] items-center gap-[0.8rem]">
        {MODE_DEMO ? (
          <button
            type="button"
            onClick={onUbahHalte}
            disabled={!halteSiap}
            aria-label={`Halte asal: ${namaHalte}. Sentuh untuk mengganti`}
            className="flex min-w-0 flex-col items-start justify-self-start rounded-xl text-left text-tj-biru"
          >
            <span className="text-kecil leading-tight">Anda di halte</span>
            <span className="flex max-w-full items-center gap-[0.3rem] text-besar font-medium leading-tight">
              <span className="truncate">{namaHalte}</span>
              <IkonCaretBawah className="h-[1.1rem] w-[1.1rem] shrink-0" />
            </span>
          </button>
        ) : (
          // Kiosk terpasang di satu halte, jadi asal tidak bisa diganti pengguna.
          <div className="flex min-w-0 flex-col items-start justify-self-start text-tj-biru">
            <span className="text-kecil leading-tight">Anda di halte</span>
            <span className="max-w-full truncate text-besar font-medium leading-tight">{namaHalte}</span>
          </div>
        )}

        <img src="/logo-transjakarta.png" alt="TransJakarta" className="h-[2.7rem] w-auto" />

        <div className="justify-self-end text-right text-tj-biru">
          {simulasi ? (
            <div className="whitespace-nowrap text-kecil font-bold leading-tight text-tj-oranye">SIMULASI</div>
          ) : (
            <div className="whitespace-nowrap text-kecil leading-tight">{tanggal}</div>
          )}
          <div className={`text-jam font-medium leading-none tabular-nums ${simulasi ? 'text-tj-oranye' : ''}`}>
            {formatJam(waktu.simTime)}
          </div>
        </div>
      </div>

      {MODE_DEMO && <WaktuKontrol waktu={waktu} />}
    </header>
  );
}
