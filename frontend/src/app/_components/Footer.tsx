import { formatJam } from '@/lib/koridor';

import { IkonBantuan } from './ikon';

type Props = {
  online: boolean;
  // Jam (detik sejak tengah malam WIB) data rute terakhir berhasil diambil; null bila belum ada pencarian.
  diperbaruiDetik: number | null;
};

export function Footer({ online, diperbaruiDetik }: Props) {
  return (
    <footer className="grid h-[2.1rem] shrink-0 grid-cols-[1fr_auto_1fr] items-center px-[1.4rem] text-kecil text-tj-biru">
      {/* Isi bantuan belum ditentukan, jadi tombol dinonaktifkan dulu. */}
      <button
        type="button"
        disabled
        title="Belum tersedia"
        className="flex items-center gap-[0.4rem] justify-self-start opacity-60"
      >
        <IkonBantuan className="h-[1.2rem] w-[1.2rem]" />
        Bantuan
      </button>
      <span className="whitespace-nowrap">✚ Transjakarta Menghubungkan Kehidupan Jakarta ✚</span>
      {!online ? (
        <span role="status" className="justify-self-end whitespace-nowrap font-bold text-tj-padat">
          ● Tidak ada koneksi internet
        </span>
      ) : diperbaruiDetik !== null ? (
        <span className="justify-self-end whitespace-nowrap tabular-nums text-gray-600">
          Diperbarui {formatJam(diperbaruiDetik)}
        </span>
      ) : (
        <span />
      )}
    </footer>
  );
}
