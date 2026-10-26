// Menutupi layar sebelum reset otomatis; sentuhan apa pun di mana saja memperpanjang sesi (ditangkap useIdleReset) dan hanya menutup peringatan, tanpa menekan tombol di bawahnya.
export function PeringatanIdle({ sisaDetik }: { sisaDetik: number }) {
  return (
    <div
      role="alert"
      className="fixed inset-0 z-[55] flex items-center justify-center bg-black/50 p-[2rem] backdrop-blur-sm"
    >
      <div className="layar-masuk flex w-full max-w-[26rem] flex-col items-center gap-[0.6rem] rounded-2xl border bg-background p-[1.6rem] text-center shadow-lg">
        <p className="text-judul font-bold tracking-tight">Masih di sana?</p>
        <p className="text-besar text-muted-foreground">
          Layar kembali ke awal dalam <b className="tabular-nums text-foreground">{sisaDetik}</b> detik.
        </p>
        <p className="text-isi font-medium text-primary">Sentuh layar untuk melanjutkan.</p>
      </div>
    </div>
  );
}
