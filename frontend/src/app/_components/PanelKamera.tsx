'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE, GalatApi } from '@/lib/api';
import { skalaBbox, statusKamera, type Bbox, type FrameKameraResponse } from '@/lib/kamera';

// Frame baru diminta tiap 5 detik, sama seperti posisi bus asli.
const KAMERA_REFRESH_MS = 5_000;

const PESAN = {
  memuat: 'Memuat kamera…',
  basi: 'Frame kamera basi: kamera belum mengirim frame baru.',
  offline: 'Kamera offline: belum ada frame dari bus.',
  galat: 'Kamera tidak dapat dimuat. Pastikan server backend berjalan.',
} as const;

const JAM_WIB = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jakarta', timeStyle: 'medium' });

// Frame kamera dengan kotak deteksi. Kotak memakai persen ukuran asli gambar
// (diketahui setelah gambar dimuat), jadi ikut skala lebar tampilan.
export function FrameKamera({ src, bboxes }: { src: string; bboxes: Bbox[] }) {
  const [ukuran, setUkuran] = useState<{ lebar: number; tinggi: number } | null>(null);

  return (
    <div className="relative">
      {/* Signed URL Supabase berubah tiap permintaan; next/image tidak membantu di sini. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="Frame kamera bus"
        className="block h-auto w-full"
        onLoad={(e) =>
          setUkuran({ lebar: e.currentTarget.naturalWidth, tinggi: e.currentTarget.naturalHeight })
        }
      />
      {ukuran &&
        ukuran.lebar > 0 &&
        ukuran.tinggi > 0 &&
        bboxes.map((b, i) => {
          const k = skalaBbox(b, ukuran.lebar, ukuran.tinggi);
          return (
            <div
              key={i}
              data-testid="bbox"
              aria-hidden
              className="absolute border-2 border-tj-oranye"
              style={{ left: `${k.left}%`, top: `${k.top}%`, width: `${k.width}%`, height: `${k.height}%` }}
            >
              <span className="absolute left-0 top-0 whitespace-nowrap bg-tj-oranye px-[0.2rem] text-[0.6rem] leading-tight text-white">
                {b.kelas} {Math.round(b.skor * 100)}%
              </span>
            </div>
          );
        })}
    </div>
  );
}

// Panel kamera bus fisik (CV worker) untuk halaman operator.
export function PanelKamera() {
  const { data, error } = useQuery<FrameKameraResponse>({
    queryKey: ['kamera-bus'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/live/camera`);
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        throw new GalatApi(r.status, typeof body?.detail === 'string' ? body.detail : '');
      }
      return r.json();
    },
    refetchInterval: KAMERA_REFRESH_MS,
    // 404/410 adalah status, bukan galat sementara; polling berikutnya yang mencoba lagi.
    retry: false,
  });
  const status = statusKamera(data, error);

  return (
    <section
      aria-label="Kamera bus"
      className="w-[20rem] overflow-hidden rounded-xl border border-tj-garis bg-white/95 shadow"
    >
      <header className="flex items-center gap-[0.5rem] px-[0.6rem] py-[0.2rem] text-kecil">
        <span className="font-bold text-tj-biru">Kamera{data && status === 'aktif' ? ` ${data.bus_id}` : ''}</span>
        <span
          className={`ml-auto rounded-md px-[0.4rem] text-[0.7rem] font-bold text-white ${
            status === 'aktif' ? 'bg-tj-sepi' : status === 'memuat' ? 'bg-gray-400' : 'bg-tj-padat'
          }`}
        >
          {status === 'aktif' ? 'AKTIF' : status === 'basi' ? 'BASI' : status === 'memuat' ? '…' : 'OFFLINE'}
        </span>
      </header>
      {status !== 'aktif' ? (
        <p role="status" className="px-[0.6rem] py-[0.4rem] text-kecil text-tj-teks">
          {PESAN[status]}
        </p>
      ) : (
        data && (
          <>
            <FrameKamera src={data.frame_url} bboxes={data.bboxes} />
            <p role="status" className="px-[0.6rem] py-[0.2rem] text-kecil text-tj-teks">
              {data.bboxes.length} deteksi · {JAM_WIB.format(new Date(data.updated_at))}
            </p>
          </>
        )
      )}
    </section>
  );
}
