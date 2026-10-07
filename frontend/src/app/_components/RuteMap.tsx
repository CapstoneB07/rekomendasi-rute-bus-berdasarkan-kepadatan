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

const WARNA_LIVE = '#2563eb';
const TRANSPARAN = 'rgba(0,0,0,0)';
const WARNA_KORIDOR_EKSPRESI = ekspresiWarnaKoridor() as unknown as ExpressionSpecification;

// Panah putih berbingkai gelap yang menghadap utara; diputar layer 'bus-arrow' sesuai bearing bus.
function buatGambarPanah(): ImageData {
  const ukuran = 48;
  const canvas = document.createElement('canvas');
  canvas.width = ukuran;
  canvas.height = ukuran;
  const ctx = canvas.getContext('2d')!;
  ctx.beginPath();
  ctx.moveTo(24, 6);
  ctx.lineTo(39, 38);
  ctx.lineTo(24, 30);
  ctx.lineTo(9, 38);
  ctx.closePath();
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(17,24,39,0.85)';
  ctx.lineJoin = 'round';
  ctx.stroke();
  return ctx.getImageData(0, 0, ukuran, ukuran);
}
const WARNA_NAIK = '#111827';
const WARNA_TRANSIT = '#d97706';
const WARNA_TURUN = '#dc2626';

// Penanda berlabel: titik di koordinat halte, label menempel di kanannya.
// Label memakai textContent supaya nama halte tidak pernah diparse sebagai HTML.
function buatPenanda(warna: string, teks: string, belah = false): HTMLElement {
  const root = document.createElement('div');
  root.className = 'relative h-5 w-5';

  const titik = document.createElement('div');
  titik.className = `h-5 w-5 border-[3px] border-white shadow ${belah ? 'rotate-45 rounded-sm' : 'rounded-full'}`;
  titik.style.background = warna;

  const label = document.createElement('span');
  label.className =
    'absolute left-full top-1/2 ml-2 -translate-y-1/2 whitespace-nowrap rounded-lg border-2 border-white px-2.5 py-1 text-kecil font-bold text-white shadow';
  label.style.background = warna;
  label.textContent = teks;

  root.append(titik, label);
  return root;
}

// Label bus berdata CV; cincin birunya digambar layer bus-live-ring.
function buatLabelLive(): HTMLElement {
  const root = document.createElement('div');
  root.className = 'h-0 w-0';
  const label = document.createElement('span');
  label.className =
    'absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-2.5 py-0.5 text-kecil font-bold text-white shadow';
  label.style.background = WARNA_LIVE;
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

type Titik = { halte: Halte; warna: string; teks: string; belah?: boolean };

function titikPenanda(rute: Rute, halteMap: Map<string, Halte>): Titik[] {
  const titik: Titik[] = [];
  const tambah = (id: string, warna: string, awalan: string, belah?: boolean) => {
    const halte = halteMap.get(id);
    if (halte) titik.push({ halte, warna, teks: `${awalan} · ${halte.nama}`, belah });
  };

  const naik = rute.segmen.filter((s) => s.tipe === 'naik');
  if (naik.length === 0) return titik;
  tambah(naik[0].naik_di_id, WARNA_NAIK, 'NAIK');
  for (const s of rute.segmen) {
    if (s.tipe === 'transit') tambah(s.transit_di_id, WARNA_TRANSIT, 'TRANSIT', true);
  }
  tambah(naik[naik.length - 1].turun_di_id, WARNA_TURUN, 'TURUN');
  return titik;
}

type Props = {
  rute: Rute | undefined;
  halteMap: Map<string, Halte>;
  bus: PosisiBusResponse | undefined;
  // Bila diisi, hanya jalur koridor dan bus dari koridor-koridor ini yang digambar.
  koridorFilter?: number[];
};

const LAYER_BUS = ['bus-ring', 'bus-dots', 'bus-arrow'] as const;

export function RuteMap({ rute, halteMap, bus, koridorFilter }: Props) {
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
      // Jalur koridor tipis di bawah rute supaya posisi bus punya konteks.
      map.addSource('shapes', { type: 'geojson', data: EMPTY_LINES });
      map.addLayer({
        id: 'shapes-casing',
        type: 'line',
        source: 'shapes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': 'rgba(17,24,39,0.35)', 'line-width': 7 },
      });
      map.addLayer({
        id: 'shapes-line',
        type: 'line',
        source: 'shapes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': WARNA_KORIDOR_EKSPRESI, 'line-width': 4 },
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

      // Bus di atas semua garis: titik = warna koridor, cincin = kepadatan (tanpa cincin bila tidak ada data),
      // panah putih = arah jalan.
      map.addImage('panah', buatGambarPanah());
      map.addSource('bus', { type: 'geojson', data: EMPTY_POINTS });
      map.addLayer({
        id: 'bus-ring',
        type: 'circle',
        source: 'bus',
        paint: {
          'circle-radius': 17,
          'circle-opacity': 0,
          'circle-stroke-width': 5,
          // null -> -1 -> di bawah ambang pertama -> tanpa cincin.
          'circle-stroke-color': [
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
        id: 'bus-dots',
        type: 'circle',
        source: 'bus',
        paint: {
          'circle-radius': 12,
          'circle-color': WARNA_KORIDOR_EKSPRESI,
          'circle-stroke-color': '#111827',
          'circle-stroke-width': 2.5,
        },
      });
      map.addLayer({
        id: 'bus-arrow',
        type: 'symbol',
        source: 'bus',
        layout: {
          'icon-image': 'panah',
          'icon-size': 0.36,
          'icon-rotate': ['coalesce', ['get', 'bearing'], 0],
          'icon-rotation-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
        },
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

    const garis = rute ? buildRouteGeoJSON(rute.segmen, halteMap, shapes) : EMPTY_LINES;
    (map.getSource('rute') as GeoJSONSource).setData(garis);
    if (!rute) return;

    const bounds = new maplibregl.LngLatBounds();
    garis.features.forEach((f) => f.geometry.coordinates.forEach((c) => bounds.extend(c as [number, number])));

    for (const t of titikPenanda(rute, halteMap)) {
      const lngLat: [number, number] = [t.halte.lng, t.halte.lat];
      markersRef.current.push(
        new maplibregl.Marker({ element: buatPenanda(t.warna, t.teks, t.belah) })
          .setLngLat(lngLat)
          .addTo(map),
      );
      bounds.extend(lngLat);
    }

    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: { top: 70, bottom: 70, left: 70, right: 70 }, maxZoom: 15, duration: 600 });
  }, [ready, rute, halteMap, shapes]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Peta rute dan posisi bus" role="img" />
      {petaGagal && (
        <p
          role="status"
          className="pointer-events-none absolute inset-x-[1rem] top-1/2 z-10 mx-auto w-fit -translate-y-1/2 rounded-xl border border-tj-garis bg-white px-[1rem] py-[0.4rem] text-center text-isi font-bold text-tj-padat shadow"
        >
          Peta belum dapat dimuat. Periksa koneksi internet.
        </p>
      )}
      <ul className="absolute bottom-[0.6rem] left-[0.6rem] z-10 flex items-center gap-x-[0.8rem] rounded-xl border border-tj-garis bg-white/95 px-[0.7rem] py-[0.25rem] text-kecil text-tj-teks shadow">
        <li className="font-bold">Kepadatan:</li>
        {[
          ['Sepi', kepadatanKeWarna(0)],
          ['Sedang', kepadatanKeWarna(0.5)],
          ['Padat', kepadatanKeWarna(1)],
        ].map(([teks, warna]) => (
          <li key={teks} className="flex items-center gap-[0.3rem]">
            <span className="h-[0.9rem] w-[0.9rem] rounded-full border-[3px]" style={{ borderColor: warna }} />
            {teks}
          </li>
        ))}
      </ul>
    </div>
  );
}
