'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap, type Marker } from 'maplibre-gl';

import { API_BASE } from '@/lib/api';
import { type Halte, type Rute, buildRouteGeoJSON } from '@/lib/route-utils';

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
};

export function RuteMap({ rute, halteMap }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
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
      setReady(true);
    });

    mapRef.current = map;
    return () => {
      ro.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

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

  return <div ref={containerRef} className="h-full w-full" aria-label="Peta rute" role="img" />;
}
