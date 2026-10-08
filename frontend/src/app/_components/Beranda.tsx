'use client';

import { IkonCari, IkonLokasi } from './ikon';

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
    <div className="layar-masuk flex h-full flex-col items-center justify-center gap-[1.2rem] pb-[1.5rem] text-center">
      <div>
        <h1 className="text-judul font-bold text-tj-biru">Cari Rute Bus yang Nyaman</h1>
        <p className="mx-auto mt-[0.5rem] max-w-[28rem] text-besar leading-snug text-tj-teks">
          Pilih perjalanan dengan informasi kepadatan bus secara langsung.
        </p>
      </div>

      <div className="w-full max-w-[30rem] space-y-[0.8rem]">
        <button
          type="button"
          onClick={onPilihTujuan}
          disabled={!halteSiap}
          aria-label={namaTujuan ? `Tujuan: ${namaTujuan}. Sentuh untuk mengganti` : 'Pilih tujuan'}
          className="flex w-full items-center gap-[0.9rem] rounded-2xl border-[3px] border-tj-biru bg-white px-[1.1rem] py-[0.6rem] text-left shadow-sm disabled:opacity-60"
        >
          <IkonLokasi className="h-[2rem] w-[2rem] shrink-0 text-tj-oranye" />
          <span className="min-w-0">
            <span className="block text-kecil font-bold leading-tight text-tj-oranye">Ke:</span>
            <span
              className={`block truncate text-besar font-bold leading-tight ${namaTujuan ? 'text-tj-teks' : 'text-gray-600'}`}
            >
              {namaTujuan ?? (halteSiap ? 'Sentuh untuk memilih tujuan…' : 'Memuat daftar halte…')}
            </span>
          </span>
        </button>

        <button
          type="button"
          onClick={onCari}
          disabled={!bisaCari}
          className="flex h-[3.4rem] w-full items-center justify-center gap-[0.7rem] rounded-2xl bg-tj-biru text-besar font-bold text-white disabled:bg-gray-200 disabled:text-gray-600"
        >
          <IkonCari className="h-[1.6rem] w-[1.6rem]" />
          Cari Rute
        </button>
      </div>
    </div>
  );
}
