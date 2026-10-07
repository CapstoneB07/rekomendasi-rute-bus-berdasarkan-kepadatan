'use client';

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import dynamic from 'next/dynamic';
import { useQuery } from '@tanstack/react-query';

import { Beranda } from './_components/Beranda';
import { DaftarRencana } from './_components/DaftarRencana';
import { DetailRencana } from './_components/DetailRencana';
import { Footer } from './_components/Footer';
import { Header } from './_components/Header';
import { PeringatanIdle } from './_components/PeringatanIdle';
import { PilihHalte } from './_components/PilihHalte';
import { API_BASE, GalatApi, galatRute, waktuWib } from '@/lib/api';
import { formatTanggal } from '@/lib/koridor';
import {
  statusBusAsli,
  type Halte,
  type HalteOpsi,
  type PosisiBusAsliResponse,
  type PosisiBusResponse,
  type Rute,
} from '@/lib/route-utils';
import { useIdleReset } from '@/lib/use-idle-reset';
import { useOnline } from '@/lib/use-online';
import { useWaktuSimulasi } from '@/lib/use-waktu-simulasi';

// MapLibre butuh `window`, jadi hanya dirender di browser.
const RuteMap = dynamic(() => import('./_components/RuteMap').then((m) => m.RuteMap), {
  ssr: false,
});

const REFRESH_MS = 30_000;
// Rute dihitung ulang tiap 5 menit jam simulasi karena Dijkstra mahal; ETA memakai jam saat fetch.
const RUTE_BUCKET_DETIK = 300;
// Posisi bus diminta tiap 5 detik simulasi, ditunda 300 ms setelah jam berhenti berubah.
const POSISI_BUCKET_DETIK = 5;
const POSISI_DEBOUNCE_MS = 300;
// Posisi bus asli (mode waktu nyata) diambil dari backend tiap 5 detik.
const BUS_ASLI_REFRESH_MS = 5_000;
// Kiosk umum: kembali ke beranda bila tidak disentuh selama ini.
const IDLE_RESET_MS = 60_000;
// Peringatan tampil selama jendela ini sebelum reset.
const IDLE_PERINGATAN_MS = 10_000;
const HALTE_ASAL_DEFAULT = 'Harmoni';

type Layar = 'beranda' | 'daftar' | 'detail';
type Pemilih = 'tujuan' | 'asal' | null;

export default function Home() {
  const [layar, setLayar] = useState<Layar>('beranda');
  const [pemilih, setPemilih] = useState<Pemilih>(null);
  const [asalId, setAsalId] = useState<string | null>(null);
  const [tujuanId, setTujuanId] = useState<string | null>(null);
  const [aktifIdx, setAktifIdx] = useState(0);

  const waktu = useWaktuSimulasi();
  const { simTime, isLive } = waktu;
  const simTimeRef = useRef(simTime);
  useEffect(() => {
    simTimeRef.current = simTime;
  }, [simTime]);
  // Tanggal hanya dihitung di klien (kosong di server) supaya render server dan klien sama.
  const tanggal = useSyncExternalStore(
    () => () => {},
    () => formatTanggal(new Date()),
    () => '',
  );

  // ---- Posisi bus pada jam simulasi ----
  const [posisiWaktu, setPosisiWaktu] = useState<number | null>(null);
  useEffect(() => {
    const id = setTimeout(
      () => setPosisiWaktu(Math.floor(simTime / POSISI_BUCKET_DETIK) * POSISI_BUCKET_DETIK),
      POSISI_DEBOUNCE_MS,
    );
    return () => clearTimeout(id);
  }, [simTime]);

  const { data: posisiBus } = useQuery<PosisiBusResponse>({
    queryKey: ['posisi-bus', posisiWaktu],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/simulation/positions?sim_time=${posisiWaktu}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    enabled: !isLive && posisiWaktu !== null,
    placeholderData: (prev) => prev,
  });

  // ---- Posisi bus asli (mode waktu nyata) ----
  const { data: busAsli, isError: busAsliError } = useQuery<PosisiBusAsliResponse>({
    queryKey: ['posisi-bus-asli'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/live/positions`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    enabled: isLive,
    refetchInterval: BUS_ASLI_REFRESH_MS,
    placeholderData: (prev) => prev,
  });

  const { data: halteList, isError: halteError, refetch: muatUlangHalte } = useQuery<HalteOpsi[]>({
    queryKey: ['halte-user'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/rute/halte`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 10 * 60_000,
  });

  const halteMap = useMemo(
    () => new Map<string, Halte>((halteList ?? []).map((h) => [h.halte_id, h])),
    [halteList],
  );
  // Halte kiosk: pilihan demo, atau Harmoni (halte asal bawaan desain) selama belum dipilih.
  const asalDefault = useMemo(
    () => halteList?.find((h) => h.nama === HALTE_ASAL_DEFAULT) ?? halteList?.[0],
    [halteList],
  );
  const asal = asalId ?? asalDefault?.halte_id ?? null;
  const namaAsal = asal ? (halteMap.get(asal)?.nama ?? '…') : '…';
  const namaTujuan = tujuanId ? (halteMap.get(tujuanId)?.nama ?? null) : null;

  const pencarian =
    layar !== 'beranda' && asal && tujuanId && asal !== tujuanId ? { asal, tujuan: tujuanId } : null;

  const {
    data: hasilRute,
    isFetching,
    dataUpdatedAt,
    error,
    isError: ruteError,
    refetch: cobaLagiRute,
  } = useQuery<Rute[]>({
    queryKey: [
      'rute-user',
      pencarian?.asal,
      pencarian?.tujuan,
      Math.floor(simTime / RUTE_BUCKET_DETIK),
      isLive,
    ],
    queryFn: async () => {
      // Jam dibaca saat fetch (bukan saat render) supaya ETA bus segar pada tiap refetch.
      const detik = simTimeRef.current;
      const jam = Math.floor(detik / 3600) % 24;
      const { hariTipe } = waktuWib();
      const r = await fetch(`${API_BASE}/api/rute/rekomendasi`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          halte_asal: pencarian!.asal,
          halte_tujuan: pencarian!.tujuan,
          jam,
          hari_tipe: hariTipe,
          sim_time: detik,
          live: isLive,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new GalatApi(r.status, typeof body?.detail === 'string' ? body.detail : '');
      }
      return r.json();
    },
    enabled: pencarian !== null,
    refetchInterval: isLive ? REFRESH_MS : false,
    // Pertahankan hasil sebelumnya saat bucket jam berganti, hanya untuk pasangan halte yang sama.
    placeholderData: (prev, prevQuery) =>
      prevQuery?.queryKey[1] === pencarian?.asal && prevQuery?.queryKey[2] === pencarian?.tujuan
        ? prev
        : undefined,
    retry: 1,
  });

  const ruteAktif =
    hasilRute && hasilRute.length > 0 ? hasilRute[Math.min(aktifIdx, hasilRute.length - 1)] : undefined;

  // Saat satu rencana dibuka, peta hanya menampilkan koridor yang dipakai rencana itu.
  const koridorRencana = useMemo(
    () =>
      layar === 'detail' && ruteAktif
        ? [...new Set(ruteAktif.segmen.flatMap((s) => (s.tipe === 'naik' ? [s.koridor_id] : [])))]
        : undefined,
    [layar, ruteAktif],
  );

  // Reset penuh (pengguna berikutnya, atau asal berubah): tujuan ikut dihapus.
  const kembaliKeBeranda = useCallback(() => {
    setLayar('beranda');
    setPemilih(null);
    setTujuanId(null);
    setAktifIdx(0);
  }, []);

  // Pengguna berikutnya tidak boleh melihat pencarian orang sebelumnya.
  const adaSesi = layar !== 'beranda' || tujuanId !== null || pemilih !== null;
  const sisaIdleDetik = useIdleReset(kembaliKeBeranda, IDLE_RESET_MS, adaSesi, IDLE_PERINGATAN_MS);

  // Kembali dari daftar rencana: tujuan dipertahankan supaya bisa diganti atau dicari ulang.
  const ubahTujuan = () => {
    setLayar('beranda');
    setAktifIdx(0);
  };
  const pilihTujuan = (id: string) => {
    setTujuanId(id);
    setPemilih(null);
  };
  const pilihAsal = (id: string) => {
    setAsalId(id);
    setPemilih(null);
    setAktifIdx(0);
    // Asal baru sama dengan tujuan: pencarian tidak mungkin, ulangi dari beranda.
    if (id === tujuanId) kembaliKeBeranda();
  };

  const tampilPeta = layar !== 'beranda';
  const online = useOnline();
  // Jam WIB data rute terakhir; hanya relevan saat daftar/detail rencana tampil.
  const diperbaruiDetik = tampilPeta && pencarian && dataUpdatedAt > 0 ? waktuWib(new Date(dataUpdatedAt)).detik : null;
  // Jumlah bus di label status mengikuti bus yang benar-benar tampil (setelah filter koridor).
  const busAsliTampil = useMemo(
    () =>
      busAsli && koridorRencana
        ? { ...busAsli, features: busAsli.features.filter((f) => koridorRencana.includes(f.properties.koridor_id)) }
        : busAsli,
    [busAsli, koridorRencana],
  );
  const statusLive = isLive && tampilPeta ? statusBusAsli(busAsliTampil, busAsliError) : null;

  return (
    <div className="flex h-dvh w-screen flex-col overflow-hidden bg-white">
      <Header
        namaHalte={namaAsal}
        onUbahHalte={() => setPemilih('asal')}
        halteSiap={!!halteList}
        waktu={waktu}
        tanggal={tanggal}
      />

      <main className="grid min-h-0 flex-1 grid-cols-[45fr_55fr] grid-rows-[minmax(0,1fr)] gap-x-[1rem] px-[1.4rem]">
        {/* Peta tetap terpasang (hanya disembunyikan di beranda) supaya tidak dimuat ulang tiap pindah layar.
            Di beranda panel menutupi kedua kolom; peta yang tak terlihat tidak menangkap sentuhan. */}
        <div
          className={`relative col-start-2 row-start-1 mb-[0.4rem] min-h-0 min-w-0 overflow-hidden rounded-2xl bg-gray-100 ${
            tampilPeta ? '' : 'invisible'
          }`}
        >
          <RuteMap
            rute={layar === 'beranda' ? undefined : ruteAktif}
            halteMap={halteMap}
            bus={isLive ? busAsli : posisiBus}
            koridorFilter={koridorRencana}
          />
          {statusLive && (
            <p
              role="status"
              className="absolute left-[0.6rem] top-[0.6rem] z-10 rounded-lg border border-tj-garis bg-white/95 px-[0.6rem] py-[0.15rem] text-kecil text-tj-teks shadow"
            >
              {statusLive}
            </p>
          )}
        </div>

        <section
          className={`row-start-1 min-h-0 min-w-0 ${
            layar === 'beranda' ? 'col-span-2 col-start-1' : 'col-start-1'
          }`}
        >
          {layar === 'beranda' && (
            <Beranda
              namaTujuan={namaTujuan}
              halteSiap={!!halteList}
              bisaCari={!!asal && !!tujuanId && asal !== tujuanId}
              onPilihTujuan={() => setPemilih('tujuan')}
              onCari={() => {
                setAktifIdx(0);
                setLayar('daftar');
              }}
            />
          )}
          {layar === 'daftar' && (
            <DaftarRencana
              asal={namaAsal}
              tujuan={namaTujuan ?? '…'}
              hasilRute={hasilRute}
              memuat={isFetching}
              aktifIdx={aktifIdx}
              galat={ruteError ? galatRute(error) : null}
              onCoba={() => void cobaLagiRute()}
              onAktif={setAktifIdx}
              onPilih={(i) => {
                setAktifIdx(i);
                setLayar('detail');
              }}
              onKembali={ubahTujuan}
            />
          )}
          {layar === 'detail' && ruteAktif && (
            <DetailRencana
              rute={ruteAktif}
              tujuan={namaTujuan ?? '…'}
              simTime={simTime}
              onKembali={() => setLayar('daftar')}
            />
          )}
        </section>
      </main>

      <Footer online={online} diperbaruiDetik={diperbaruiDetik} />

      {halteError && (
        <div
          role="alert"
          className="fixed inset-x-0 bottom-[2.4rem] z-40 mx-auto flex w-fit items-center gap-[0.8rem] rounded-xl bg-tj-padat px-[1rem] py-[0.3rem] text-kecil text-white"
        >
          Gagal memuat daftar halte. Pastikan server backend berjalan.
          <button
            type="button"
            onClick={() => void muatUlangHalte()}
            className="h-[2rem] rounded-lg bg-white px-[0.8rem] font-bold text-tj-padat"
          >
            Coba lagi
          </button>
        </div>
      )}

      {pemilih && halteList && (
        <PilihHalte
          judul={pemilih === 'tujuan' ? 'Pilih halte tujuan' : 'Pilih halte asal (demo)'}
          halteList={halteList}
          terpilihId={pemilih === 'tujuan' ? tujuanId : asal}
          nonaktifNama={pemilih === 'tujuan' ? namaAsal : namaTujuan}
          nonaktifAlasan={pemilih === 'tujuan' ? 'Halte asal' : 'Halte tujuan'}
          onPilih={pemilih === 'tujuan' ? pilihTujuan : pilihAsal}
          onTutup={() => setPemilih(null)}
        />
      )}

      {sisaIdleDetik !== null && <PeringatanIdle sisaDetik={sisaIdleDetik} />}

      {/* Kiosk hanya dirancang lanskap. */}
      <div className="fixed inset-0 z-[60] hidden items-center justify-center bg-tj-biru p-[2rem] text-center text-judul font-bold text-white [@media(orientation:portrait)]:flex">
        Putar iPad ke posisi mendatar
      </div>
    </div>
  );
}
