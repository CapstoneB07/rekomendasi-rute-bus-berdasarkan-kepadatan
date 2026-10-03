'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap, type Marker } from 'maplibre-gl';

import { API_BASE } from '@/lib/api';
import {
  type BusPosisi,
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

const WARNA_LIVE = '#2563eb';
const WARNA_NAIK = '#111827';
const WARNA_TRANSIT = '#d97706';
const WARNA_TURUN = '#dc2626';

// Penanda berlabel: titik di koordinat halte, label menempel di kanannya.
// Label memakai textContent supaya nama halte tidak pernah diparse sebagai HTML.
function buatPenanda(warna: string, teks: string, belah = false): HTMLElement {
  const root = document.createElement('div');
  root.className = 'relative h-4 w-4';

  const titik = document.createElement('div');
  titik.className = `h-4 w-4 border-[3px] border-white shadow ${belah ? 'rotate-45 rounded-sm' : 'rounded-full'}`;
  titik.style.background = warna;

  const label = document.createElement('span');
  label.className =
    'absolute left-full top-1/2 ml-2 -translate-y-1/2 whitespace-nowrap rounded px-2 py-1 text-xs font-bold text-white shadow';
  label.style.background = warna;
  label.textContent = teks;

  root.append(titik, label);
  return root;
}

// Label di atas bus yang kepadatannya dari kamera CV. Cincin biru di titiknya
// digambar layer `bus-live-ring`; elemen ini hanya membawa tulisan.
function buatLabelLive(): HTMLElement {
  const root = document.createElement('div');
  root.className = 'h-0 w-0';
  const label = document.createElement('span');
  label.className =
    'absolute bottom-4 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold text-white shadow';
  label.style.background = WARNA_LIVE;
  root.append(label);
  return root;
}

function teksLabelLive(p: BusPosisi): string {
  return `LIVE · Bus ${p.bus_id} · ${Math.round(p.estimated_passengers)}/${p.capacity}`;
}

function isiPopupBus(p: BusPosisi): HTMLElement {
  const root = document.createElement('div');
  root.className = 'text-xs leading-5 text-gray-900';
  const baris = (teks: string, tebal = false) => {
    const el = document.createElement('div');
    el.textContent = teks;
    if (tebal) el.className = 'font-bold';
    root.append(el);
  };
  baris(`Bus ${p.bus_id}`, true);
  baris(`Koridor ${p.koridor_id} · menuju ${p.next_stop}`);
  baris(`Tiba ${p.eta_minutes <= 0 ? 'sebentar lagi' : `${p.eta_minutes} menit lagi`}`);
  baris(
    `${p.label_kepadatan === 'Sepi' ? 'Lega' : p.label_kepadatan} · ` +
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
};

export function RuteMap({ rute, halteMap, bus }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const liveMarkerRef = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);

  // Key sama dengan SimulationMap supaya cache react-query dipakai bersama.
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

    map.on('load', () => {
      // Jalur koridor tipis di bawah rute supaya posisi bus punya konteks.
      map.addSource('shapes', { type: 'geojson', data: EMPTY_LINES });
      map.addLayer({
        id: 'shapes-line',
        type: 'line',
        source: 'shapes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#9ca3af', 'line-width': 3, 'line-opacity': 0.6 },
      });
      map.addSource('rute', { type: 'geojson', data: EMPTY_LINES });
      // Casing putih di bawah garis berwarna supaya rute terbaca di atas jalan.
      map.addLayer({
        id: 'rute-casing',
        type: 'line',
        source: 'rute',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 10 },
      });
      map.addLayer({
        id: 'rute-line',
        type: 'line',
        source: 'rute',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'warna'], 'line-width': 6 },
      });

      // Bus di atas semua garis. Warna titik = kepadatan (ambang sama dengan
      // kepadatanKeWarna); cincin biru menandai bus berdata CV live.
      map.addSource('bus', { type: 'geojson', data: EMPTY_POINTS });
      map.addLayer({
        id: 'bus-live-ring',
        type: 'circle',
        source: 'bus',
        filter: ['==', ['get', 'data_source'], 'cv_live'],
        paint: {
          'circle-radius': 12,
          'circle-opacity': 0,
          'circle-stroke-color': WARNA_LIVE,
          'circle-stroke-width': 3,
        },
      });
      map.addLayer({
        id: 'bus-dots',
        type: 'circle',
        source: 'bus',
        paint: {
          'circle-radius': 6,
          'circle-color': [
            'step',
            ['get', 'trip_load_factor'],
            kepadatanKeWarna(0),
            0.4,
            kepadatanKeWarna(0.5),
            0.7,
            kepadatanKeWarna(1),
          ],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
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

  // ---- Posisi bus + label bus live ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('bus') as GeoJSONSource).setData(bus ?? EMPTY_POINTS);

    const live = bus?.features.find((f) => f.properties.data_source === 'cv_live');
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
  }, [ready, bus]);

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

    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: { top: 60, bottom: 60, left: 60, right: 200 }, maxZoom: 15, duration: 600 });
  }, [ready, rute, halteMap, shapes]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Peta rute dan posisi bus" role="img" />
      <ul className="absolute bottom-2 left-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-white/90 px-2.5 py-1.5 text-[11px] text-gray-700 shadow">
        {[
          ['Lega', kepadatanKeWarna(0)],
          ['Cukup ramai', kepadatanKeWarna(0.5)],
          ['Padat', kepadatanKeWarna(1)],
        ].map(([teks, warna]) => (
          <li key={teks} className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: warna }} />
            {teks}
          </li>
        ))}
        <li className="flex items-center gap-1 font-semibold" style={{ color: WARNA_LIVE }}>
          <span className="h-3 w-3 rounded-full border-2" style={{ borderColor: WARNA_LIVE }} />
          Data live (CV)
        </li>
      </ul>
    </div>
  );
}
