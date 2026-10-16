'use client';

import { useKameraMqtt, type StatusKameraMqtt } from '@/lib/kamera-mqtt';

const PESAN: Record<Exclude<StatusKameraMqtt, 'aktif'>, string> = {
  menyambung: 'Menyambung ke broker kamera…',
  menunggu: 'Tersambung, menunggu frame dari kamera…',
  terputus: 'Koneksi broker kamera terputus, mencoba lagi…',
};

const JAM_WIB = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jakarta', timeStyle: 'medium' });

// Stream kamera ESP32-S3 langsung dari MQTT (tanpa backend/CV), untuk halaman operator.
export function PanelKameraMqtt() {
  const { status, frame } = useKameraMqtt();

  return (
    <section
      aria-label="Kamera realtime"
      className="w-[20rem] overflow-hidden rounded-xl border border-tj-garis bg-white/95 shadow"
    >
      <header className="flex items-center gap-[0.5rem] px-[0.6rem] py-[0.2rem] text-kecil">
        <span className="font-bold text-tj-biru">Kamera realtime</span>
        <span
          className={`ml-auto rounded-md px-[0.4rem] text-[0.7rem] font-bold text-white ${
            status === 'aktif' ? 'bg-tj-sepi' : status === 'terputus' ? 'bg-tj-padat' : 'bg-gray-400'
          }`}
        >
          {status === 'aktif' ? 'LIVE' : status === 'terputus' ? 'OFFLINE' : '…'}
        </span>
      </header>
      {frame && (
        // Object URL lokal tiap frame; next/image tidak membantu di sini.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={frame.src} alt="Frame kamera realtime" className="block h-auto w-full" />
      )}
      <p role="status" className="px-[0.6rem] py-[0.2rem] text-kecil text-tj-teks">
        {status !== 'aktif' && PESAN[status]}
        {status !== 'aktif' && frame && ' · '}
        {frame && `${JAM_WIB.format(frame.diterimaPada)} · ${(frame.ukuranByte / 1024).toFixed(1)} KB`}
      </p>
    </section>
  );
}
