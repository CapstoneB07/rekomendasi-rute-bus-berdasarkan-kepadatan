'use client';

import { useState } from 'react';

import { formatJam } from '@/lib/koridor';
import { warnaLabelKepadatan, type NaikItem, type Rute } from '@/lib/route-utils';
import { buatTiket, jamLeg, type Tiket } from '@/lib/tiket';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import { LencanaKoridor } from './DaftarRencana';
import { IkonCetak, IkonPanahKiri } from './ikon';
import { TiketCetak } from './TiketCetak';

function KartuNaik({ item, simTime }: { item: NaikItem; simTime: number }) {
  const rek = item.bus_rekomendasi;
  const { naik, turun } = jamLeg(item, simTime);
  const label = rek?.label_kepadatan;

  return (
    <Card className="shrink-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-[0.5rem] gap-y-[0.1rem] border-b px-[0.8rem] py-[0.25rem]">
        <LencanaKoridor koridorId={item.koridor_id} />
        {rek ? (
          <>
            <Badge varian="outline" className="font-bold leading-[1.6rem]">
              {rek.bus_id}
            </Badge>
            <span className="ml-auto whitespace-nowrap text-kecil text-muted-foreground">
              {rek.eta_menit <= 0 ? 'Segera' : `${rek.eta_menit} menit lagi`}
            </span>
            {label && (
              <span
                className="flex items-center gap-[0.3rem] whitespace-nowrap text-kecil font-bold"
                style={{ color: warnaLabelKepadatan(label) }}
              >
                <span className="h-[0.7rem] w-[0.7rem] rounded-full" style={{ background: warnaLabelKepadatan(label) }} />
                {label}
              </span>
            )}
          </>
        ) : (
          <span className="ml-auto text-kecil text-muted-foreground">Belum ada bus terjadwal</span>
        )}
      </div>
      <dl className="space-y-[0.2rem] px-[0.8rem] py-[0.4rem] text-isi leading-tight">
        <div className="flex items-baseline justify-between gap-[0.6rem]">
          <dt className="min-w-0">
            Naik di <b>{item.naik_di}</b>
          </dt>
          <dd className="whitespace-nowrap text-kecil text-muted-foreground tabular-nums">{naik !== null ? formatJam(naik) : '—'}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-[0.6rem]">
          <dt className="min-w-0">
            Turun di <b>{item.turun_di}</b>{' '}
            <span className="whitespace-nowrap text-kecil text-muted-foreground">· {item.waktu_menit} menit</span>
          </dt>
          <dd className="whitespace-nowrap text-kecil text-muted-foreground tabular-nums">{turun !== null ? formatJam(turun) : '—'}</dd>
        </div>
      </dl>
    </Card>
  );
}

type Props = {
  rute: Rute;
  asal: string;
  tujuan: string;
  simTime: number;
  onKembali: () => void;
};

export function DetailRencana({ rute, asal, tujuan, simTime, onKembali }: Props) {
  // Tiket dibentuk sekali saat tombol ditekan supaya nomor dan jamnya tetap selama pratinjau.
  const [tiket, setTiket] = useState<Tiket | null>(null);

  return (
    <div className="layar-masuk flex h-full min-h-0 flex-col gap-[0.5rem] pb-[0.4rem]">
      <div className="flex items-center gap-[0.8rem]">
        <Button varian="outline" onClick={onKembali}>
          <IkonPanahKiri className="h-[1.2rem] w-[1.2rem]" />
          Kembali
        </Button>
        <span className="min-w-0 truncate text-besar font-bold tracking-tight">Ke {tujuan}</span>
      </div>

      {/* Rute dengan banyak bus tidak dipadatkan; daftar bergulir bila tidak muat. */}
      <div className="flex min-h-0 flex-1 flex-col gap-[0.5rem] overflow-y-auto">
        {rute.segmen.map((s, i) =>
          s.tipe === 'naik' ? (
            <KartuNaik key={i} item={s} simTime={simTime} />
          ) : (
            <div
              key={i}
              className="shrink-0 rounded-lg border border-dashed border-input bg-muted px-[0.8rem] py-[0.25rem] text-kecil leading-snug"
            >
              Pindah bus di <b>{s.transit_di}</b> ke koridor {s.ke_koridor}
            </div>
          ),
        )}
      </div>

      <Button
        ukuran="lg"
        onClick={() => setTiket(buatTiket(rute, { asal, tujuan, simTime, dicetak: new Date() }))}
        className="w-full font-bold"
      >
        <IkonCetak className="h-[1.4rem] w-[1.4rem]" />
        Cetak Informasi
      </Button>

      {tiket && <TiketCetak tiket={tiket} onTutup={() => setTiket(null)} />}
    </div>
  );
}
