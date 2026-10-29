'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import maplibregl, {
  type ExpressionSpecification,
  type FilterSpecification,
  type GeoJSONSource,
  type Map as MapLibreMap,
  type Marker,
} from 'maplibre-gl';

import { API_BASE } from '@/lib/api';
import { OPSI_BUS_SIMULASI, PenganimasiBus } from '@/lib/animasi-bus';
import { ekspresiWarnaKoridor } from '@/lib/koridor';
import {
  type BusPosisi,
  type BusPosisiSimulasi,
  type Halte,
  type PosisiBusResponse,
  type Rute,
  buildRouteGeoJSON,
  bearingNaikDiAtas,
  potongGarisRute,
  kepadatanKeWarna,
} from '@/lib/route-utils';

type ShapesResponse = GeoJSON.FeatureCollection<GeoJSON.LineString, {
  koridor_id: number | string;
  shape_id: string;
}>;

// Style vector MapLibre gratis tanpa API key (OpenFreeMap).
const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';
const JAKARTA: [number, number] = [106.827, -6.175];
const EMPTY_LINES: GeoJSON.FeatureCollection<GeoJSON.LineString> = {
  type: 'FeatureCollection',
  features: [],
};

const EMPTY_POINTS: PosisiBusResponse = { type: 'FeatureCollection', features: [] };

// Gambar ulang bus asli maksimal ±30x per detik; cukup halus dan tidak membebani peta.
const FRAME_BUS_MS = 33;

const TRANSPARAN = 'rgba(0,0,0,0)';
const WARNA_KORIDOR_EKSPRESI = ekspresiWarnaKoridor() as unknown as ExpressionSpecification;
const WARNA_TEKS_KORIDOR_EKSPRESI = ekspresiWarnaKoridor('teks') as unknown as ExpressionSpecification;

// Ukuran titik bus mengikuti zoom: titik kecil saat kota terlihat utuh, membesar menjadi lencana bernomor koridor saat zoom dekat (gaya peta bus langsung).
const ZOOM_PANAH = 13;
const ZOOM_LABEL = 15;
// Skala penanda rute (titik + label) mengikuti zoom seperti titik bus: kecil saat kota terlihat utuh,
// ukuran penuh saat zoom dekat. Label tetap terbaca di skala terkecil.
const SKALA_PENANDA: [number, number][] = [[10, 0.55], [12, 0.7], [14, 0.85], [15, 1]];

function skalaPenanda(zoom: number): number {
  const [z0, s0] = SKALA_PENANDA[0];
  if (zoom <= z0) return s0;
  for (let i = 1; i < SKALA_PENANDA.length; i++) {
    const [za, sa] = SKALA_PENANDA[i - 1];
    const [zb, sb] = SKALA_PENANDA[i];
    if (zoom <= zb) return sa + ((zoom - za) / (zb - za)) * (sb - sa);
  }
  return SKALA_PENANDA[SKALA_PENANDA.length - 1][1];
}

const JARI_TITIK: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 10, 3.5, 12, 5, 14, 7, 15, 9, 17, 12];
// Kepadatan sebagai cahaya lembut di sekeliling titik; jarinya selalu sedikit lebih besar dari titik.
const JARI_HALO: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 10, 7, 12, 9, 14, 12, 15, 14, 17, 18];
// Gambar moncong memakai jari titik JARI_GAMBAR px (setelah pixelRatio), jadi skala = jari titik / JARI_GAMBAR.
const JARI_GAMBAR = 10;
const SKALA_MONCONG: ExpressionSpecification = [
  'interpolate', ['linear'], ['zoom'], ZOOM_PANAH, 5.5 / JARI_GAMBAR, 14, 7 / JARI_GAMBAR, 15, 9 / JARI_GAMBAR, 17, 12 / JARI_GAMBAR,
];

// Moncong kecil di tepi titik yang menghadap utara; diputar layer 'bus-arrow' sesuai bearing bus.
function buatGambarMoncong(): { data: ImageData; pixelRatio: number } {
  const pixelRatio = 2;
  const ukuran = 96;
  const tengah = ukuran / 2;
  const jari = JARI_GAMBAR * pixelRatio;
  const canvas = document.createElement('canvas');
  canvas.width = ukuran;
  canvas.height = ukuran;
  const ctx = canvas.getContext('2d')!;
  ctx.beginPath();
  ctx.moveTo(tengah, tengah - jari - 18);
  ctx.lineTo(tengah + 11, tengah - jari + 2);
  ctx.lineTo(tengah - 11, tengah - jari + 2);
  ctx.closePath();
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = 'rgba(17,24,39,0.75)';
  ctx.lineJoin = 'round';
  ctx.stroke();
  return { data: ctx.getImageData(0, 0, ukuran, ukuran), pixelRatio };
}
// Penanda rute dibedakan lewat bentuk dan warna netral/primary, bukan hijau/kuning/merah, karena warna semafor di peta khusus untuk kepadatan.
const GAYA_PENANDA = {
  // NAIK adalah yang pertama dicari mata: label lebih besar dan selalu di atas penanda lain (z), nomor langkah menyusul urutan perjalanan.
  naik: { titik: 'rounded-full border-white bg-primary', label: 'border-primary bg-primary text-isi text-primary-foreground', nomor: 'bg-white text-primary', z: 3 },
  transit: { titik: 'rotate-45 rounded-sm border-foreground bg-background', label: 'border-foreground bg-background text-kecil text-foreground', nomor: 'bg-foreground text-background', z: 1 },
  turun: { titik: 'rounded-full border-white bg-foreground', label: 'border-foreground bg-foreground text-kecil text-background', nomor: 'bg-background text-foreground', z: 2 },
} as const;
type JenisPenanda = keyof typeof GAYA_PENANDA;

// Penanda berlabel: titik di koordinat halte, label menempel di kanannya. Label memakai textContent supaya nama halte tidak pernah diparse sebagai HTML.
// `urut` (nomor langkah perjalanan) opsional: penanda lokasi operator tidak punya urutan.
function buatPenanda(jenis: JenisPenanda, teks: string, urut?: number): HTMLElement {
  const gaya = GAYA_PENANDA[jenis];
  const root = document.createElement('div');
  root.className = 'h-5 w-5';
  root.dataset.jenis = jenis;
  root.style.zIndex = String(gaya.z);
  // Posisi root dikendalikan MapLibre (transform); skala zoom dipasang di isi agar tidak bertabrakan.
  const isi = document.createElement('div');
  isi.className = 'relative h-full w-full';

  const titik = document.createElement('div');
  titik.className = `h-5 w-5 border-[3px] shadow ${gaya.titik}`;

  const label = document.createElement('span');
  // Posisi label diatur tataLabel (left/top inline) supaya tidak terpotong tepi atau menimpa label lain.
  label.className = `absolute left-0 top-0 inline-flex items-center gap-[0.35rem] whitespace-nowrap rounded-lg border px-2 py-0.5 font-bold shadow-sm ${gaya.label}`;
  if (urut !== undefined) {
    const nomor = document.createElement('span');
    nomor.className = `inline-flex size-[1.2em] shrink-0 items-center justify-center rounded-full text-[0.8em] leading-none ${gaya.nomor}`;
    nomor.textContent = String(urut);
    label.append(nomor);
  }
  label.append(teks);

  isi.append(titik, label);
  root.append(isi);
  return root;
}

type Kotak = { x: number; y: number; w: number; h: number };

// Jarak minimum antar label/titik supaya label yang berdekatan tidak tampak menempel.
const RENGGANG_LABEL = 4;
// Ukuran label pecahan (skala zoom) membuat luas tumpang "nol" bisa bernilai 1e-12; di bawah ini dianggap bebas.
const TUMPANG_DIABAIKAN = 0.5;

function lebarkan(k: Kotak, d: number): Kotak {
  return { x: k.x - d, y: k.y - d, w: k.w + 2 * d, h: k.h + 2 * d };
}

function luasTumpang(a: Kotak, b: Kotak): number {
  const lebar = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const tinggi = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return Math.max(0, lebar) * Math.max(0, tinggi);
}

// Tata label penanda supaya tidak terpotong tepi peta dan tidak saling menimpa. Tiap label mencoba sisi
// kanan/kiri titiknya (sisi ke arah tengah peta dulu), lalu digeser ke atas/bawah; dipakai posisi pertama
// yang bebas, atau yang paling sedikit menimpa bila semuanya bertabrakan. Titik penanda ikut dihindari.
// NAIK/TURUN ditata dulu dan selalu tampil; label TRANSIT yang tidak punya tempat bebas (peta jauh di-zoom
// out) disembunyikan sampai ada ruang, titiknya tetap terlihat.
function tataLabel(map: MapLibreMap, penanda: Marker[]) {
  const wadah = map.getContainer();
  const batas: Kotak = { x: 0, y: 0, w: wadah.clientWidth, h: wadah.clientHeight };
  // Ukur semua dulu, baru tulis posisi, supaya tidak memaksa tata letak ulang di tiap label.
  // Isi penanda diskalakan k di sekitar pusat titik; ukuran layar = ukuran CSS x k.
  const k = skalaPenanda(map.getZoom());
  const data = penanda.flatMap((m) => {
    const root = m.getElement();
    const isi = root.firstElementChild as HTMLElement | null;
    const label = root.querySelector('span');
    if (!isi || !label) return [];
    const wajib = root.dataset.jenis !== 'transit';
    const s0 = root.offsetWidth;
    return [{ isi, label, wajib, p: map.project(m.getLngLat()), s0, s: s0 * k, w: label.offsetWidth * k, h: label.offsetHeight * k }];
  });
  data.sort((a, b) => Number(b.wajib) - Number(a.wajib));
  const terisi: Kotak[] = data.map(({ p, s }) => ({ x: p.x - s / 2, y: p.y - s / 2, w: s, h: s }));

  for (const { isi, label, wajib, p, s0, s, w, h } of data) {
    isi.style.transform = `scale(${k})`;
    const jarak = s * 0.4;
    const kanan = p.x + s / 2 + jarak;
    const kiri = p.x - s / 2 - jarak - w;
    const [utama, cadangan] = p.x < batas.w / 2 ? [kanan, kiri] : [kiri, kanan];
    const naik = -(h / 2 + jarak);
    const turun = h / 2 + jarak;
    const calon: [number, number][] = [
      [utama, 0], [cadangan, 0], [utama, naik], [utama, turun], [cadangan, naik], [cadangan, turun],
    ];

    let terbaik: Kotak = { x: utama, y: p.y - h / 2, w, h };
    let skorTerbaik = Infinity;
    for (const [x, dy] of calon) {
      const k = { x, y: p.y - h / 2 + dy, w, h };
      const longgar = lebarkan(k, RENGGANG_LABEL);
      const skor = w * h - luasTumpang(k, batas) + terisi.reduce((t, o) => t + luasTumpang(longgar, o), 0);
      if (skor < skorTerbaik) {
        terbaik = k;
        skorTerbaik = skor;
      }
      if (skor < TUMPANG_DIABAIKAN) break;
    }
    const tampil = wajib || skorTerbaik < TUMPANG_DIABAIKAN;
    label.style.visibility = tampil ? '' : 'hidden';
    if (!tampil) continue;
    terisi.push(terbaik);
    // Kembalikan dari koordinat layar ke koordinat CSS isi (sebelum diskalakan di sekitar pusatnya).
    label.style.left = `${(terbaik.x - p.x) / k + s0 / 2}px`;
    label.style.top = `${(terbaik.y - p.y) / k + s0 / 2}px`;
  }
}

// Label bus berdata CV; cincin birunya digambar layer bus-live-ring.
function buatLabelLive(): HTMLElement {
  const root = document.createElement('div');
  root.className = 'h-0 w-0';
  const label = document.createElement('span');
  label.className =
    'absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-primary px-2.5 py-0.5 text-kecil font-bold text-primary-foreground shadow';
  root.append(label);
  return root;
}

function teksLabelLive(p: BusPosisiSimulasi): string {
  return `LIVE · Bus ${p.bus_id} · ${Math.round(p.estimated_passengers)}/${p.capacity}`;
}

function isiPopupBus(p: BusPosisi): HTMLElement {
  const root = document.createElement('div');
  root.className = 'text-kecil leading-snug text-gray-900';
  const baris = (teks: string, tebal = false) => {
    const el = document.createElement('div');
    el.textContent = teks;
    if (tebal) el.className = 'font-bold';
    root.append(el);
  };
  baris(`Bus ${p.bus_id}`, true);
  baris(`Koridor ${p.koridor_id} · menuju ${p.next_stop}`);
  baris(`Tiba ${p.eta_minutes <= 0 ? 'sebentar lagi' : `${p.eta_minutes} menit lagi`}`);
  if (p.data_source === 'tj_live') {
    baris(
      p.label_kepadatan === null
        ? 'Kepadatan tidak tersedia untuk koridor ini'
        : `${p.label_kepadatan} · perkiraan simulasi`,
    );
    baris('Posisi dan ETA: data asli TransJakarta', true);
    return root;
  }
  baris(
    `${p.label_kepadatan} · ` +
      `${Math.round(p.estimated_passengers)}/${p.capacity} penumpang`,
  );
  baris(
    p.data_source === 'cv_live' ? 'Data kepadatan: LIVE (kamera CV)' : 'Data kepadatan: simulasi',
    p.data_source === 'cv_live',
  );
  return root;
}

type Titik = { halte: Halte; jenis: JenisPenanda; teks: string; urut: number };

function titikPenanda(rute: Rute, halteMap: Map<string, Halte>): Titik[] {
  const titik: Titik[] = [];
  const tambah = (id: string, jenis: JenisPenanda) => {
    const halte = halteMap.get(id);
    if (halte) titik.push({ halte, jenis, teks: `${jenis.toUpperCase()} · ${halte.nama}`, urut: titik.length + 1 });
  };

  const naik = rute.segmen.filter((s) => s.tipe === 'naik');
  if (naik.length === 0) return titik;
  tambah(naik[0].naik_di_id, 'naik');
  for (const s of rute.segmen) {
    if (s.tipe === 'transit') tambah(s.transit_di_id, 'transit');
  }
  tambah(naik[naik.length - 1].turun_di_id, 'turun');
  return titik;
}

type Props = {
  rute: Rute | undefined;
  halteMap: Map<string, Halte>;
  bus: PosisiBusResponse | undefined;
  // Bila diisi, hanya jalur koridor dan bus dari koridor-koridor ini yang digambar.
  koridorFilter?: number[];
  // Tanpa rute: peta diarahkan ke halte ini dan menandainya (pemilih lokasi halaman operator).
  fokus?: Halte;
  // Legenda kepadatan bus; halaman user menyembunyikannya supaya peta bersih.
  legenda?: boolean;
  // Bila diisi, rute digambar bertahap (operator) dan animasinya diputar ulang tiap nilai ini berganti.
  animasi?: number;
  // Peta diputar otomatis saat ada rute supaya halte NAIK di atas dan TURUN di bawah (operator).
  putarKeNaik?: boolean;
};

const DURASI_ANIMASI_RUTE_MS = 3000;

const LAYER_BUS = ['bus-ring', 'bus-arrow', 'bus-dots', 'bus-label'] as const;

export function RuteMap({ rute, halteMap, bus, koridorFilter, fokus, legenda = true, animasi, putarKeNaik }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const liveMarkerRef = useRef<Marker | null>(null);
  const koridorFilterRef = useRef(koridorFilter);
  const penganimasiAsliRef = useRef(new PenganimasiBus());
  const penganimasiSimulasiRef = useRef(new PenganimasiBus(OPSI_BUS_SIMULASI));
  const [ready, setReady] = useState(false);
  const [petaGagal, setPetaGagal] = useState(false);

  // Jalur koridor untuk garis latar peta.
  const { data: shapes } = useQuery<ShapesResponse>({
    queryKey: ['shapes'],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/simulation/shapes`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: Infinity,
    retry: 1,
  });

  // ---- Init map sekali ----
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: BASEMAP_STYLE,
      center: JAKARTA,
      zoom: 11,
      // Atribusi wajib (lisensi OSM/OpenMapTiles) tetap ada, tetapi diringkas menjadi tombol ⓘ.
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container);

    // Tile atau style gagal diambil (offline/server peta mati); hilang sendiri begitu peta selesai digambar.
    map.on('error', (e) => {
      const { sourceId } = e as { sourceId?: string };
      if (sourceId || /fetch|network/i.test(e.error?.message ?? '')) setPetaGagal(true);
    });
    map.on('idle', () => setPetaGagal(false));

    map.on('load', () => {
      // Mode ringkas MapLibre mulai terbuka dan baru menutup saat peta diseret; kiosk jarang diseret.
      container.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
      // Jalur koridor tipis di bawah rute supaya posisi bus punya konteks.
      map.addSource('shapes', { type: 'geojson', data: EMPTY_LINES });
      map.addLayer({
        id: 'shapes-casing',
        type: 'line',
        source: 'shapes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': 'rgba(17,24,39,0.35)', 'line-width': 4.5 },
      });
      map.addLayer({
        id: 'shapes-line',
        type: 'line',
        source: 'shapes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': WARNA_KORIDOR_EKSPRESI, 'line-width': 2.5 },
      });
      map.addSource('rute', { type: 'geojson', data: EMPTY_LINES });
      // Casing gelap di bawah garis berwarna supaya rute (termasuk koridor kuning) terbaca di peta terang.
      map.addLayer({
        id: 'rute-casing',
        type: 'line',
        source: 'rute',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': 'rgba(17,24,39,0.6)', 'line-width': 14 },
      });
      map.addLayer({
        id: 'rute-line',
        type: 'line',
        source: 'rute',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'warna'], 'line-width': 9 },
      });

      // Bus di atas semua garis: titik warna koridor berbingkai putih, cahaya = kepadatan (tanpa cahaya bila tidak ada data), moncong = arah jalan (zoom sedang), nomor koridor di dalam titik (zoom dekat).
      const { data: moncong, pixelRatio } = buatGambarMoncong();
      map.addImage('moncong', moncong, { pixelRatio });
      map.addSource('bus', { type: 'geojson', data: EMPTY_POINTS });
      map.addLayer({
        id: 'bus-ring',
        type: 'circle',
        source: 'bus',
        paint: {
          'circle-radius': JARI_HALO,
          'circle-blur': 0.15,
          'circle-opacity': 0.7,
          // null -> -1 -> di bawah ambang pertama -> tanpa cahaya.
          'circle-color': [
            'step',
            ['coalesce', ['get', 'trip_load_factor'], -1],
            TRANSPARAN,
            0,
            kepadatanKeWarna(0),
            0.4,
            kepadatanKeWarna(0.5),
            0.7,
            kepadatanKeWarna(1),
          ],
        },
      });
      map.addLayer({
        id: 'bus-arrow',
        type: 'symbol',
        source: 'bus',
        minzoom: ZOOM_PANAH,
        layout: {
          'icon-image': 'moncong',
          'icon-size': SKALA_MONCONG,
          'icon-rotate': ['coalesce', ['get', 'bearing'], 0],
          'icon-rotation-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
        },
      });
      map.addLayer({
        id: 'bus-dots',
        type: 'circle',
        source: 'bus',
        paint: {
          'circle-radius': JARI_TITIK,
          'circle-color': WARNA_KORIDOR_EKSPRESI,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 14, 2],
        },
      });
      map.addLayer({
        id: 'bus-label',
        type: 'symbol',
        source: 'bus',
        minzoom: ZOOM_LABEL,
        layout: {
          'text-field': ['to-string', ['get', 'koridor_id']],
          'text-font': ['Noto Sans Bold'],
          'text-size': ['interpolate', ['linear'], ['zoom'], ZOOM_LABEL, 10, 17, 13],
          'text-allow-overlap': true,
          'text-ignore-placement': true,
        },
        paint: { 'text-color': WARNA_TEKS_KORIDOR_EKSPRESI },
      });
      map.on('click', 'bus-dots', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        new maplibregl.Popup({ offset: 12 })
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setDOMContent(isiPopupBus(f.properties as BusPosisi))
          .addTo(map);
      });
      map.on('mouseenter', 'bus-dots', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'bus-dots', () => (map.getCanvas().style.cursor = ''));
      setReady(true);
    });

    mapRef.current = map;
    return () => {
      ro.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      liveMarkerRef.current?.remove();
      liveMarkerRef.current = null;
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- Jalur koridor ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !shapes) return;
    (map.getSource('shapes') as GeoJSONSource).setData(shapes);
  }, [ready, shapes]);

  // ---- Filter koridor: jalur latar dan bus hanya untuk koridor rencana yang dibuka ----
  const kunciFilter = koridorFilter ? koridorFilter.join(',') : null;
  useEffect(() => {
    koridorFilterRef.current = koridorFilter;
    const map = mapRef.current;
    if (!map || !ready) return;
    const filterJalur = koridorFilter
      ? ['in', ['to-string', ['get', 'koridor_id']], ['literal', koridorFilter.map(String)]]
      : null;
    const filterBus = koridorFilter ? ['in', ['get', 'koridor_id'], ['literal', koridorFilter]] : null;
    for (const id of ['shapes-casing', 'shapes-line']) map.setFilter(id, filterJalur as FilterSpecification | null);
    for (const id of LAYER_BUS) map.setFilter(id, filterBus as FilterSpecification | null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- kunciFilter mewakili isi koridorFilter
  }, [ready, kunciFilter]);

  // ---- Posisi bus (digeser mulus) + label bus ber-CV ----
  const busAsli = bus?.features[0]?.properties.data_source === 'tj_live';

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource('bus') as GeoJSONSource;
    // Bus asli dan simulasi diperbarui dengan irama berbeda, jadi masing-masing punya penganimasi.
    const pakai = busAsli ? penganimasiAsliRef.current : penganimasiSimulasiRef.current;
    (busAsli ? penganimasiSimulasiRef.current : penganimasiAsliRef.current).reset();

    // Label bus ber-CV mengikuti posisi titiknya yang sedang digeser, bukan posisi mentah dari server.
    const pasangLabelCv = (data: PosisiBusResponse) => {
      const filter = koridorFilterRef.current;
      const live = data.features.find(
        (f): f is GeoJSON.Feature<GeoJSON.Point, BusPosisiSimulasi> =>
          f.properties.data_source === 'cv_live' && (!filter || filter.includes(Number(f.properties.koridor_id))),
      );
      if (!live) {
        liveMarkerRef.current?.remove();
        liveMarkerRef.current = null;
        return;
      }
      const lngLat = live.geometry.coordinates as [number, number];
      if (!liveMarkerRef.current) {
        liveMarkerRef.current = new maplibregl.Marker({ element: buatLabelLive() }).setLngLat(lngLat).addTo(map);
      }
      liveMarkerRef.current.setLngLat(lngLat);
      const label = liveMarkerRef.current.getElement().querySelector('span');
      if (label) label.textContent = teksLabelLive(live.properties);
    };

    if (!bus) {
      pakai.reset();
      source.setData(EMPTY_POINTS);
      pasangLabelCv(EMPTY_POINTS);
      return;
    }
    pakai.perbarui(bus, performance.now());

    let raf = 0;
    let terakhir = -Infinity;
    const frame = (t: number) => {
      if (t - terakhir >= FRAME_BUS_MS) {
        const data = pakai.frame(t);
        source.setData(data);
        pasangLabelCv(data);
        terakhir = t;
      }
      // Berhenti menggambar saat semua bus sudah sampai (jam dijeda, data belum berubah).
      if (pakai.bergerak(t)) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [ready, bus, busAsli, kunciFilter]);

  // ---- Gambar rute aktif + penanda, lalu zoom ke seluruh rute ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    const aturLabel = () => tataLabel(map, markersRef.current);
    map.on('move', aturLabel);

    const garis = rute ? buildRouteGeoJSON(rute.segmen, halteMap, shapes) : EMPTY_LINES;
    const sumberRute = map.getSource('rute') as GeoJSONSource;
    let raf = 0;
    const lepas = () => {
      cancelAnimationFrame(raf);
      map.off('move', aturLabel);
    };
    if (!rute) {
      sumberRute.setData(garis);
      if (map.getBearing() !== 0) map.easeTo({ bearing: 0, duration: 600 });
      if (fokus) {
        const lngLat: [number, number] = [fokus.lng, fokus.lat];
        markersRef.current.push(
          new maplibregl.Marker({ element: buatPenanda('naik', fokus.nama) }).setLngLat(lngLat).addTo(map),
        );
        map.flyTo({ center: lngLat, zoom: 15, duration: 600 });
      }
      aturLabel();
      return lepas;
    }

    const bounds = new maplibregl.LngLatBounds();
    garis.features.forEach((f) => f.geometry.coordinates.forEach((c) => bounds.extend(c as [number, number])));

    const titik = titikPenanda(rute, halteMap);
    const pasangPenanda = (daftar: Titik[]) => {
      for (const t of daftar) {
        markersRef.current.push(
          new maplibregl.Marker({ element: buatPenanda(t.jenis, t.teks, t.urut) })
            .setLngLat([t.halte.lng, t.halte.lat])
            .addTo(map),
        );
      }
      aturLabel();
    };
    for (const t of titik) bounds.extend([t.halte.lng, t.halte.lat]);
    const bearing = putarKeNaik && titik.length >= 2 ? bearingNaikDiAtas(titik[0].halte, titik[titik.length - 1].halte) : 0;
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: { top: 70, bottom: legenda ? 120 : 70, left: 70, right: 70 }, maxZoom: 15, bearing, duration: putarKeNaik ? 1000 : 600 });
    }

    // Animasi pembentukan rute (operator): garis tumbuh dari halte naik, penanda lain muncul setelah garis selesai.
    const animasikan = animasi !== undefined && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!animasikan) {
      sumberRute.setData(garis);
      pasangPenanda(titik);
      return lepas;
    }
    sumberRute.setData(EMPTY_LINES);
    pasangPenanda(titik.slice(0, 1));
    const mulai = performance.now();
    const frame = (t: number) => {
      const p = Math.min((t - mulai) / DURASI_ANIMASI_RUTE_MS, 1);
      sumberRute.setData(potongGarisRute(garis, p * p * (3 - 2 * p)));
      if (p < 1) {
        raf = requestAnimationFrame(frame);
      } else {
        pasangPenanda(titik.slice(1));
      }
    };
    raf = requestAnimationFrame(frame);
    return lepas;
  }, [ready, rute, halteMap, shapes, fokus, animasi, legenda, putarKeNaik]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Peta rute dan posisi bus" role="img" />
      {petaGagal && (
        <p
          role="status"
          className="pointer-events-none absolute inset-x-[1rem] top-1/2 z-10 mx-auto w-fit -translate-y-1/2 rounded-xl border bg-background px-[1rem] py-[0.4rem] text-center text-isi font-bold text-destructive shadow-md"
        >
          Peta belum dapat dimuat. Periksa koneksi internet.
        </p>
      )}
      {legenda && (
        <ul className="absolute bottom-[0.6rem] left-[0.6rem] z-10 flex items-center gap-x-[0.8rem] rounded-lg border bg-background/95 px-[0.7rem] py-[0.25rem] text-kecil shadow-sm">
          <li className="font-bold">Kepadatan:</li>
          {[
            ['Sepi', kepadatanKeWarna(0)],
            ['Sedang', kepadatanKeWarna(0.5)],
            ['Padat', kepadatanKeWarna(1)],
          ].map(([teks, warna]) => (
            <li key={teks} className="flex items-center gap-[0.3rem]">
              {/* Cincin kepadatan di sekeliling titik bus, versi tegas dari layer bus-ring di peta. */}
              <span
                className="size-[0.55rem] rounded-full border border-white bg-muted-foreground"
                style={{ boxShadow: `0 0 0 0.18rem ${warna}` }}
              />
              {teks}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
