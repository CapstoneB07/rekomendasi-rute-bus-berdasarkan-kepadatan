'use client';

import { useMemo, useState } from 'react';

import type { GalatTampil } from '@/lib/api';
import { formatKm, formatRupiah, TARIF_RP, warnaKoridor } from '@/lib/koridor';
import { halaman } from '@/lib/pilih-halte';
import { jumlahTransit, labelRencana, type LabelRencana } from '@/lib/rencana';
import {
  kepadatanKeWarna,
  labelKepadatan,
  normalisasiKepadatanDisplay,
  type NaikItem,
  type Rute,
} from '@/lib/route-utils';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import { IkonBus, IkonChevronKanan, IkonPanahKiri } from './ikon';

const PER_HALAMAN = 2;
const LABEL = { sepi: 'Sepi', sedang: 'Sedang', padat: 'Padat' } as const;

export function LencanaKoridor({ koridorId, className = '' }: { koridorId: number | string; className?: string }) {
  const w = warnaKoridor(koridorId);
  return (
    <span
      className={cn('inline-flex min-w-[2rem] items-center justify-center rounded-md px-[0.4rem] text-isi font-bold leading-[1.7rem]', className)}
      style={{ background: w.bg, color: w.teks }}
    >
      {koridorId}
    </span>
  );
}

const VARIAN_LABEL_RENCANA = {
  Tercepat: 'default',
  'Paling lega': 'sukses',
} as const satisfies Record<LabelRencana, string>;

type PropsKartu = {
  rute: Rute;
  label: LabelRencana[];
  // Rencana yang sedang digambar di peta.
  aktif: boolean;
  onPilih: () => void;
  onDetail: () => void;
};

// Ketuk kartu = tampilkan di peta; kartu yang sudah tampil atau tombol panah = buka detail.
function KartuRencana({ rute, label, aktif, onPilih, onDetail }: PropsKartu) {
  const naik = rute.segmen.filter((s): s is NaikItem => s.tipe === 'naik');
  const v = normalisasiKepadatanDisplay(rute.rata_kepadatan);
  const teksKepadatan = LABEL[labelKepadatan(v)];
  const km = formatKm(rute.total_jarak_meter);
  const transit = jumlahTransit(rute);
  const ringkasan = `koridor ${naik.map((n) => n.koridor_id).join(' lalu ')}, ${rute.estimasi_menit} menit, kepadatan ${teksKepadatan}`;

  return (
    <Card
      className={cn(
        'relative flex min-h-0 w-full flex-col overflow-hidden',
        aktif && 'border-primary ring-2 ring-primary/20',
      )}
    >
      <button
        type="button"
        onClick={onPilih}
        aria-pressed={aktif}
        aria-label={`Rencana ${ringkasan}`}
        className="flex min-h-0 w-full flex-col text-left"
      >
        <div className="flex w-full items-center gap-[0.25rem] border-b py-[0.25rem] pl-[0.8rem] pr-[3.2rem]">
          {naik.map((n, i) => (
            <span key={i} className="flex items-center gap-[0.25rem]">
              {i > 0 && <IkonChevronKanan className="h-[0.9rem] w-[0.9rem] shrink-0 text-muted-foreground" />}
              {naik.length < 3 && <IkonBus className="h-[1.5rem] w-[1.5rem]" />}
              <LencanaKoridor koridorId={n.koridor_id} />
            </span>
          ))}
          <span className="ml-auto whitespace-nowrap text-isi font-bold leading-[1.7rem]">{rute.estimasi_menit} menit</span>
        </div>

        <div className="w-full px-[0.8rem] py-[0.3rem]">
          <div className="flex flex-wrap gap-[0.35rem]">
            <Badge varian="secondary">{formatRupiah(TARIF_RP)}</Badge>
            {km && <Badge varian="secondary">{km}</Badge>}
            {transit > 0 && <Badge varian="secondary">{transit}× transit</Badge>}
          </div>
          <div className="mt-[0.2rem] flex items-center justify-between gap-[0.4rem] text-kecil leading-tight text-muted-foreground">
            <span>Kepadatan rata-rata</span>
            <span className="flex gap-[0.3rem]">
              {label.map((l) => (
                <Badge key={l} varian={VARIAN_LABEL_RENCANA[l]} className="font-bold leading-tight">
                  {l}
                </Badge>
              ))}
            </span>
          </div>
          <div className="flex items-center gap-[0.6rem]">
            <div className="h-[0.5rem] flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full" style={{ width: `${Math.round(v * 100)}%`, background: kepadatanKeWarna(v) }} />
            </div>
            <span className="whitespace-nowrap text-kecil">
              {Math.round(v * 100)}% {teksKepadatan}
            </span>
          </div>
        </div>
      </button>

      <Button
        ukuran="icon"
        onClick={onDetail}
        aria-label={`Lihat detail rencana ${ringkasan}`}
        className="absolute right-[0.5rem] top-[0.2rem] rounded-full"
      >
        <IkonChevronKanan className="h-[1.1rem] w-[1.1rem]" />
      </Button>
    </Card>
  );
}

type Props = {
  asal: string;
  tujuan: string;
  hasilRute: Rute[] | undefined;
  memuat: boolean;
  // Indeks rencana yang sedang tampil di peta.
  aktifIdx: number;
  galat: GalatTampil | null;
  onCoba: () => void;
  onPilih: (idx: number) => void;
  onAktif: (idx: number) => void;
  onKembali: () => void;
};

// Backend menjawab 404 bila tidak ada rute, tetapi daftar kosong tetap harus punya tampilan.
const GALAT_KOSONG: GalatTampil = {
  judul: 'Rute tidak ditemukan',
  pesan: 'Belum ada rute untuk perjalanan ini pada jam ini.',
  bisaCoba: false,
};

export function DaftarRencana({ asal, tujuan, hasilRute, memuat, aktifIdx, galat, onCoba, onPilih, onAktif, onKembali }: Props) {
  // Mulai dari halaman yang memuat rencana aktif (mis. saat kembali dari detail).
  const [hal, setHal] = useState(Math.floor(aktifIdx / PER_HALAMAN));
  const { items, idx, jumlah } = halaman(hasilRute ?? [], hal, PER_HALAMAN);
  const label = useMemo(() => labelRencana(hasilRute ?? []), [hasilRute]);

  const pindah = (baru: number) => {
    setHal(baru);
    onAktif(baru * PER_HALAMAN); // peta menampilkan rencana pertama di halaman itu
  };

  const galatTampil = galat ?? (hasilRute?.length === 0 ? GALAT_KOSONG : null);

  return (
    <div className="layar-masuk flex h-full min-h-0 flex-col gap-[0.5rem] pb-[0.4rem]">
      <Button varian="outline" onClick={onKembali} className="self-start">
        <IkonPanahKiri className="h-[1.2rem] w-[1.2rem]" />
        Ubah tujuan
      </Button>

      <div className="flex items-center justify-between gap-[0.5rem]">
        <h2 className="whitespace-nowrap text-isi font-bold leading-tight">Rencana Perjalanan</h2>
        {jumlah > 1 && !galatTampil && (
          <div className="flex items-center gap-[0.4rem]">
            <Button varian="outline" ukuran="icon" disabled={idx === 0} onClick={() => pindah(idx - 1)} aria-label="Halaman sebelumnya">
              <IkonChevronKanan className="h-[1.1rem] w-[1.1rem] rotate-180" />
            </Button>
            <span className="text-kecil tabular-nums text-muted-foreground">
              {idx + 1}/{jumlah}
            </span>
            <Button varian="outline" ukuran="icon" disabled={idx >= jumlah - 1} onClick={() => pindah(idx + 1)} aria-label="Halaman berikutnya">
              <IkonChevronKanan className="h-[1.1rem] w-[1.1rem]" />
            </Button>
          </div>
        )}
      </div>

      <dl className="overflow-hidden rounded-xl border text-isi shadow-xs">
        {[
          ['Dari', asal],
          ['Ke', tujuan],
        ].map(([k, v]) => (
          <div key={k} className="grid grid-cols-[3.2rem_1fr] border-b last:border-b-0">
            <dt className="border-r bg-muted px-[0.5rem] py-[0.15rem] text-muted-foreground">{k}</dt>
            <dd className="truncate px-[0.7rem] py-[0.15rem] font-medium">{v}</dd>
          </div>
        ))}
      </dl>

      {galatTampil ? (
        <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-[0.9rem] text-isi">
          <div className="font-bold text-destructive">{galatTampil.judul}</div>
          <div className="mt-[0.2rem] text-kecil text-muted-foreground">{galatTampil.pesan}</div>
          <Button onClick={galatTampil.bisaCoba ? onCoba : onKembali} className="mt-[0.6rem]">
            {galatTampil.bisaCoba ? 'Coba lagi' : 'Ubah tujuan'}
          </Button>
        </div>
      ) : memuat && !hasilRute ? (
        <div aria-busy="true" className="grid min-h-0 flex-1 animate-pulse grid-rows-2 gap-[0.5rem]">
          <div className="rounded-xl bg-muted" />
          <div className="rounded-xl bg-muted" />
        </div>
      ) : (
        <>
          <div className="flex min-h-0 flex-1 flex-col gap-[0.5rem]">
            {items.map((r, i) => {
              const gi = idx * PER_HALAMAN + i;
              return (
                <KartuRencana
                  key={gi}
                  rute={r}
                  label={label[gi]}
                  aktif={gi === aktifIdx}
                  onPilih={() => (gi === aktifIdx ? onPilih(gi) : onAktif(gi))}
                  onDetail={() => onPilih(gi)}
                />
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
