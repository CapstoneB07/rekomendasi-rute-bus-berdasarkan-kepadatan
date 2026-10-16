'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { MqttClient } from 'mqtt';

import { API_BASE } from '@/lib/api';
import type { StatusBroker } from '@/lib/route-utils';

// Broker MQTT TransJakarta memblokir IP VPS backend, jadi browser yang berlangganan lalu
// meneruskan pesan bus ke backend (PUT /api/live/buses). Lihat backend/services/live_buses.py.
const BROKER_URL = 'wss://mqtt.tj.co.id:8084/mqtt';
const KIRIM_MS = 5_000;

export type StatusRelay = Exclude<StatusBroker, 'menyambung'>;

type HalteRelay = { name: unknown; stop_id: unknown; parent_stop_id: unknown; eta: unknown };

// Subset pesan /mobile_armada yang dipakai backend; validasi lengkapnya di backend.
export type PesanBusRelay = {
  route_code: unknown;
  bus_body_no: string;
  trip_id: unknown;
  latitude: unknown;
  longitude: unknown;
  bearing: unknown;
  eta: unknown;
  stops: HalteRelay[];
};

// Hanya koridor yang dipakai: broker yang menyaring (±3% trafik), bukan browser.
export function topikLangganan(routeCodes: string[]): string[] {
  return routeCodes.map((kode) => `/mobile_armada/+/${kode}/#`);
}

export function pangkasPesan(payload: { toString(): string }): PesanBusRelay | null {
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(payload.toString());
  } catch {
    return null;
  }
  if (typeof data !== 'object' || data === null || typeof data.bus_body_no !== 'string') return null;
  const stops = Array.isArray(data.stops) ? (data.stops as Record<string, unknown>[]) : [];
  return {
    route_code: data.route_code,
    bus_body_no: data.bus_body_no,
    trip_id: data.trip_id,
    latitude: data.latitude,
    longitude: data.longitude,
    bearing: data.bearing,
    eta: data.eta,
    stops: stops.map((s) => ({ name: s?.name, stop_id: s?.stop_id, parent_stop_id: s?.parent_stop_id, eta: s?.eta })),
  };
}

// CONNACK 5 (MQTT 3.1.1) / 135 (MQTT 5) = broker menolak, mis. client ID tidak berawalan mqttjs_.
export function statusDariGalat(galat: Error & { code?: unknown }): StatusRelay {
  return galat.code === 5 || galat.code === 135 || /not authori[sz]ed/i.test(galat.message) ? 'ditolak' : 'terputus';
}

function clientIdAcak(): string {
  const b = crypto.getRandomValues(new Uint8Array(4));
  return `mqttjs_${Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')}`;
}

// Berlangganan bus asli TransJakarta di browser ini dan meneruskannya ke backend tiap KIRIM_MS.
export function useRelayBusTj() {
  const { data } = useQuery<{ route_codes: string[] }>({
    queryKey: ['relay-route-codes'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/live/koridor`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: Infinity,
  });
  const routeCodes = data?.route_codes;

  useEffect(() => {
    if (!routeCodes?.length) return;
    // null = belum ada kabar dari broker; jangan laporkan apa pun supaya relay lain tidak tertimpa.
    let status: StatusRelay | null = null;
    const antrian = new Map<string, PesanBusRelay>();
    let client: MqttClient | undefined;
    let batal = false;

    import('mqtt').then(({ default: mqtt }) => {
      if (batal) return;
      client = mqtt.connect(BROKER_URL, { clientId: clientIdAcak(), reconnectPeriod: 5_000, connectTimeout: 10_000 });
      client.on('connect', () => {
        status = 'tersambung';
        client?.subscribe(topikLangganan(routeCodes));
      });
      client.on('error', (galat) => {
        status = statusDariGalat(galat);
      });
      // Penolakan broker juga diikuti close; alasan penolakan tetap dipertahankan.
      client.on('close', () => {
        if (status !== 'ditolak') status = 'terputus';
      });
      client.on('message', (_topik, payload) => {
        const pesan = pangkasPesan(payload);
        if (pesan) antrian.set(pesan.bus_body_no, pesan);
      });
    });

    const id = setInterval(() => {
      if (status === null) return;
      const buses = [...antrian.values()];
      antrian.clear();
      // Gagal kirim tidak diulang: tiap bus mengirim pesan baru kira-kira tiap 30 detik.
      fetch(`${API_BASE}/api/live/buses`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, buses }),
      }).catch(() => {});
    }, KIRIM_MS);

    return () => {
      batal = true;
      clearInterval(id);
      client?.end(true);
    };
  }, [routeCodes]);
}
