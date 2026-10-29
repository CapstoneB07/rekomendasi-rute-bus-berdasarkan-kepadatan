'use client';

import { Badge } from '@/components/ui/badge';
import { useKameraMqtt, type StatusKameraMqtt } from '@/lib/kamera-mqtt';

const PESAN: Record<Exclude<StatusKameraMqtt, 'aktif'>, string> = {
  menyambung: 'Menyambung ke broker kamera…',
  menunggu: 'Tersambung, menunggu frame dari kamera…',
  terputus: 'Koneksi broker kamera terputus, mencoba lagi…',
};

const JAM_WIB = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jakarta', timeStyle: 'medium' });

// Stream kamera ESP32-S3 langsung dari MQTT (tanpa backend/CV), untuk halaman operator.
// Mengisi satu sel grid penuh (setengah layar), sama seperti peta di sebelahnya.
export function PanelKameraMqtt() {
  const { status, frame } = useKameraMqtt();

  return (
    <section
      aria-label="Kamera realtime"
      className="relative col-start-1 row-start-1 min-h-0 min-w-0 overflow-hidden bg-zinc-950 text-white hp:row-start-2"
    >
      {frame && (
        // Object URL lokal tiap frame; next/image tidak membantu di sini. eslint-disable-next-line @next/next/no-img-element
        <img src={frame.src} alt="Frame kamera realtime" className="block h-full w-full object-contain" />
      )}
      <div className="absolute left-[0.6rem] top-[0.6rem] flex items-center gap-[0.5rem] rounded-lg bg-black/60 px-[0.6rem] py-[0.15rem] text-kecil">
        <span className="font-bold">Kamera realtime</span>
        <Badge
          varian={status === 'aktif' ? 'aktif' : status === 'terputus' ? 'destructive' : 'secondary'}
          className={`text-[0.7rem] font-bold leading-[1.2rem] ${status === 'aktif' ? 'border-transparent bg-background' : ''}`}
        >
          {status === 'aktif' ? 'LIVE' : status === 'terputus' ? 'OFFLINE' : '…'}
        </Badge>
      </div>
      <p
        role="status"
        className={
          frame
            ? 'absolute bottom-[0.6rem] left-[0.6rem] rounded-lg bg-black/60 px-[0.6rem] py-[0.15rem] text-kecil'
            : 'absolute inset-0 flex items-center justify-center px-[1rem] text-center text-isi text-white/70'
        }
      >
        {status !== 'aktif' && PESAN[status]}
        {status !== 'aktif' && frame && ' · '}
        {frame && `${JAM_WIB.format(frame.diterimaPada)} · ${(frame.ukuranByte / 1024).toFixed(1)} KB`}
      </p>
    </section>
  );
}
