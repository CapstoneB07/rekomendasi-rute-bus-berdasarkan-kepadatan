import { formatJam } from '@/lib/koridor';

type Props = {
  online: boolean;
  // Jam (detik sejak tengah malam WIB) data rute terakhir berhasil diambil; null bila belum ada pencarian.
  diperbaruiDetik: number | null;
};

export function Footer({ online, diperbaruiDetik }: Props) {
  return (
    <footer className="grid h-[2.1rem] shrink-0 grid-cols-[1fr_auto_1fr] items-center border-t px-[1.4rem] text-kecil text-muted-foreground">
      {/* Tombol Bantuan menyusul setelah isinya ditentukan; tombol mati hanya terlihat seperti rusak. */}
      <span />
      <span className="whitespace-nowrap">✚ Transjakarta Menghubungkan Kehidupan Jakarta ✚</span>
      {!online ? (
        <span role="status" className="flex items-center gap-[0.4rem] justify-self-end whitespace-nowrap font-medium text-destructive">
          <span aria-hidden className="size-[0.6rem] rounded-full bg-destructive" />
          Tidak ada koneksi internet
        </span>
      ) : diperbaruiDetik !== null ? (
        <span className="justify-self-end whitespace-nowrap tabular-nums">
          Diperbarui {formatJam(diperbaruiDetik)}
        </span>
      ) : (
        <span />
      )}
    </footer>
  );
}
