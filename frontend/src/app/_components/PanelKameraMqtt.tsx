'use client';

import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
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
    <Card role="region" aria-label="Kamera realtime" className="w-[20rem] overflow-hidden bg-card/95">
      <header className="flex items-center gap-[0.5rem] border-b px-[0.7rem] py-[0.3rem] text-kecil">
        <span className="font-bold">Kamera realtime</span>
        <Badge
          varian={status === 'aktif' ? 'aktif' : status === 'terputus' ? 'destructive' : 'secondary'}
          className="ml-auto text-[0.7rem] font-bold leading-[1.2rem]"
        >
          {status === 'aktif' ? 'LIVE' : status === 'terputus' ? 'OFFLINE' : '…'}
        </Badge>
      </header>
      {frame && (
        // Object URL lokal tiap frame; next/image tidak membantu di sini. eslint-disable-next-line @next/next/no-img-element
        <img src={frame.src} alt="Frame kamera realtime" className="block h-auto w-full" />
      )}
      <p role="status" className="px-[0.7rem] py-[0.2rem] text-kecil text-muted-foreground">
        {status !== 'aktif' && PESAN[status]}
        {status !== 'aktif' && frame && ' · '}
        {frame && `${JAM_WIB.format(frame.diterimaPada)} · ${(frame.ukuranByte / 1024).toFixed(1)} KB`}
      </p>
    </Card>
  );
}
