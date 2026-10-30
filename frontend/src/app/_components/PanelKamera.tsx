'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { API_BASE, GalatApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { skalaBbox, statusKamera, type Bbox, type FrameKameraResponse } from '@/lib/kamera';

// Worker mengunggah frame tiap ±1 detik; polling 2 detik menjaga tampilan tetap dekat realtime.
const KAMERA_REFRESH_MS = 2_000;

const PESAN = {
  memuat: 'Memuat kamera…',
  basi: 'Frame kamera basi: kamera belum mengirim frame baru.',
  offline: 'Kamera offline: belum ada frame dari bus.',
  galat: 'Kamera tidak dapat dimuat. Pastikan server backend berjalan.',
} as const;

const JAM_WIB = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jakarta', timeStyle: 'medium' });

// Frame kamera dengan kotak deteksi. Kotak memakai persen ukuran asli gambar (diketahui setelah gambar dimuat), jadi ikut skala tampilan.
// Pembungkus dipaskan ke wadah (object-contain ala container query) supaya kotak tepat di atas gambar, bukan di area kosong.
export function FrameKamera({ src, bboxes }: { src: string; bboxes: Bbox[] }) {
  const [ukuran, setUkuran] = useState<{ lebar: number; tinggi: number } | null>(null);
  const valid = ukuran && ukuran.lebar > 0 && ukuran.tinggi > 0 ? ukuran : null;

  return (
    <div
      className="relative"
      style={
        valid
          ? { aspectRatio: `${valid.lebar} / ${valid.tinggi}`, width: `min(100cqw, calc(100cqh * ${valid.lebar / valid.tinggi}))` }
          : { width: '100%', height: '100%' }
      }
    >
      {/* Signed URL Supabase berubah tiap permintaan; next/image tidak membantu di sini. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="Frame kamera bus"
        className="block h-full w-full"
        onLoad={(e) =>
          setUkuran({ lebar: e.currentTarget.naturalWidth, tinggi: e.currentTarget.naturalHeight })
        }
      />
      {valid &&
        bboxes.map((b, i) => {
          const k = skalaBbox(b, valid.lebar, valid.tinggi);
          return (
            <div
              key={i}
              data-testid="bbox"
              aria-hidden
              className="absolute border border-blue-600"
              style={{ left: `${k.left}%`, top: `${k.top}%`, width: `${k.width}%`, height: `${k.height}%` }}
            >
              <span className="absolute bottom-full left-0 whitespace-nowrap bg-blue-600/80 px-[0.2rem] text-[0.6rem] leading-tight text-white">
                {b.kelas} {b.skor.toFixed(2)}
              </span>
            </div>
          );
        })}
    </div>
  );
}

// Panel kamera bus fisik (CV worker) untuk halaman operator.
// Mengisi satu sel grid penuh (setengah layar), sama seperti peta di sebelahnya.
export function PanelKamera() {
  const { data, error } = useQuery<FrameKameraResponse>({
    queryKey: ['kamera-bus'],
    queryFn: async () => {
      // no-store: respons 404/410 tanpa header cache dipakai ulang browser, sehingga panel tetap BASI setelah worker hidup lagi.
      const r = await fetch(`${API_BASE}/api/live/camera`, { cache: 'no-store' });
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
      className="relative col-start-1 row-start-1 min-h-0 min-w-0 overflow-hidden bg-zinc-950 text-white hp:row-start-2"
      style={{ containerType: 'size' }}
    >
      {status === 'aktif' && data && (
        <div className="flex h-full w-full items-center justify-center">
          <FrameKamera src={data.frame_url} bboxes={data.bboxes} />
        </div>
      )}
      <div className="absolute left-[0.6rem] top-[0.6rem] flex items-center gap-[0.5rem] rounded-lg bg-black/60 px-[0.6rem] py-[0.15rem] text-kecil">
        <span className="font-bold">Kamera{data && status === 'aktif' ? ` ${data.bus_id}` : ''}</span>
        <Badge
          varian={status === 'aktif' ? 'aktif' : status === 'memuat' ? 'secondary' : 'destructive'}
          className={`text-[0.7rem] font-bold leading-[1.2rem] ${status === 'aktif' ? 'border-transparent bg-background' : ''}`}
        >
          {status === 'aktif' ? 'AKTIF' : status === 'basi' ? 'BASI' : status === 'memuat' ? '…' : 'OFFLINE'}
        </Badge>
      </div>
      <p
        role="status"
        className={
          status === 'aktif'
            ? 'absolute bottom-[0.6rem] left-[0.6rem] rounded-lg bg-black/60 px-[0.6rem] py-[0.15rem] text-kecil'
            : 'absolute inset-0 flex items-center justify-center px-[1rem] text-center text-isi text-white/70'
        }
      >
        {status === 'aktif' ? `${data?.bboxes.length} deteksi · ${JAM_WIB.format(new Date(data!.updated_at))}` : PESAN[status]}
      </p>
    </section>
  );
}
