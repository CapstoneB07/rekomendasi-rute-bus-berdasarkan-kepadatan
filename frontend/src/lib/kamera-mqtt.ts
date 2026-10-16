'use client';

import { useEffect, useState } from 'react';
import type { MqttClient } from 'mqtt';

// Kamera ESP32-S3 menerbitkan frame ke broker publik HiveMQ (sama dengan
// worker/mqtt_subscriber.py di repo bus-density-cv); browser berlangganan langsung lewat WSS.
export const KAMERA_BROKER_URL = 'wss://broker.hivemq.com:8884/mqtt';
export const KAMERA_TOPIK = 'capstone/stefany/esp32s3/camera/base64';

export type StatusKameraMqtt = 'menyambung' | 'menunggu' | 'aktif' | 'terputus';

export type FrameMqtt = { src: string; diterimaPada: Date; ukuranByte: number };

// Walau nama topiknya "base64", firmware saat ini mengirim JPEG mentah. Keduanya diterima:
// JPEG mentah (diawali FF D8) atau teks base64, boleh berawalan data URL.
export function payloadKeGambar(payload: Uint8Array): Uint8Array | null {
  if (payload.length >= 2 && payload[0] === 0xff && payload[1] === 0xd8) return payload;
  const teks = new TextDecoder().decode(payload).trim().replace(/^data:image\/[\w+.-]+;base64,/, '');
  if (!teks || !/^[A-Za-z0-9+/\s]+={0,2}$/.test(teks)) return null;
  try {
    const biner = atob(teks.replace(/\s/g, ''));
    return Uint8Array.from(biner, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

// Berlangganan frame kamera bus secara realtime; frame terakhir disajikan sebagai object URL.
export function useKameraMqtt() {
  const [status, setStatus] = useState<StatusKameraMqtt>('menyambung');
  const [frame, setFrame] = useState<FrameMqtt | null>(null);

  useEffect(() => {
    let client: MqttClient | undefined;
    let urlAktif: string | null = null;
    let batal = false;

    import('mqtt').then(({ default: mqtt }) => {
      if (batal) return;
      client = mqtt.connect(KAMERA_BROKER_URL, { reconnectPeriod: 5_000, connectTimeout: 10_000 });
      client.on('connect', () => {
        setStatus((s) => (s === 'aktif' ? s : 'menunggu'));
        client?.subscribe(KAMERA_TOPIK);
      });
      client.on('close', () => setStatus('terputus'));
      client.on('message', (_topik, payload) => {
        const gambar = payloadKeGambar(payload);
        if (!gambar) return;
        const url = URL.createObjectURL(new Blob([gambar as BlobPart], { type: 'image/jpeg' }));
        if (urlAktif) URL.revokeObjectURL(urlAktif);
        urlAktif = url;
        setFrame({ src: url, diterimaPada: new Date(), ukuranByte: gambar.length });
        setStatus('aktif');
      });
    });

    return () => {
      batal = true;
      client?.end(true);
      if (urlAktif) URL.revokeObjectURL(urlAktif);
    };
  }, []);

  return { status, frame };
}
