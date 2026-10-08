// Menutupi layar sebelum reset otomatis; sentuhan apa pun di mana saja memperpanjang sesi
// (ditangkap useIdleReset) dan hanya menutup peringatan, tanpa menekan tombol di bawahnya.
export function PeringatanIdle({ sisaDetik }: { sisaDetik: number }) {
  return (
    <div
      role="alert"
      className="fixed inset-0 z-[55] flex flex-col items-center justify-center gap-[0.8rem] bg-tj-biru/90 p-[2rem] text-center text-white"
    >
      <p className="text-judul font-bold">Masih di sana?</p>
      <p className="text-besar">
        Layar kembali ke awal dalam <b className="tabular-nums">{sisaDetik}</b> detik.
      </p>
      <p className="text-isi">Sentuh layar untuk melanjutkan.</p>
    </div>
  );
}
