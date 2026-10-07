// Tipe dan GeoJSON overlay rute Dijkstra di MapLibre, dipakai RuteMap dan RuteResult.

export type Halte = {
  halte_id: string;
  nama: string;
  lat: number;
  lng: number;
};

// Halte dari GET /api/rute/halte, dengan koridor yang melayaninya.
export type HalteOpsi = Halte & { koridor_list: number[] };

export type SegmenDetail = {
  dari_id: string;
  ke_id: string;
  kepadatan: number;
  waktu_menit: number;
  jarak_meter?: number;
};

// 'cv_live' = kepadatan dari kamera CV bus fisik; 'generated' = simulasi.
export type DataSource = 'cv_live' | 'generated';

export type BusRekomendasi = {
  bus_id: string;
  data_source?: DataSource;
  // 'tj_live' = ETA dari posisi bus asli (MQTT); 'simulasi' = ETA dari jadwal simulasi.
  eta_sumber?: 'tj_live' | 'simulasi';
  kepadatan: number;
  label_kepadatan: 'Sepi' | 'Sedang' | 'Padat';
  eta_menit: number;
  kategori_kepadatan?: 'sepi' | 'sedang' | 'padat' | 'sangat_padat';
  selection_score?: number;
  selection_reason?: 'next_bus_safe_density' | 'bus_score';
  safe_density_threshold?: number;
  eta_norm?: number;
  earliest_eta_menit?: number;
  extra_wait_menit?: number;
  extra_wait_norm?: number;
  estimated_passengers?: number;
  capacity?: number;
  // Jam (detik) penumpang tiba di halte naik, memperhitungkan transit sebelumnya; eta_menit dihitung dari sini.
  leg_clock_detik?: number;
  candidate_count?: number;
  considered_candidate_count?: number;
  candidate_debug?: Array<{
    bus_id: string;
    eta_menit: number;
    kepadatan: number;
    score: number;
  }>;
};

// Properti tiap bus di GET /api/simulation/positions.
export type BusPosisiSimulasi = {
  bus_id: string;
  koridor_id: number;
  bearing: number;
  next_stop: string;
  eta_minutes: number;
  trip_load_factor: number;
  label_kepadatan: 'Sepi' | 'Sedang' | 'Padat';
  estimated_passengers: number;
  capacity: number;
  data_source: DataSource;
};

// Bus asli dari GET /api/live/positions (MQTT TransJakarta). Posisi dan ETA asli; kepadatan
// hanya perkiraan dari trip simulasi yang setara, atau null untuk koridor di luar simulasi.
export type BusPosisiAsli = Pick<
  BusPosisiSimulasi,
  'bus_id' | 'koridor_id' | 'bearing' | 'next_stop' | 'eta_minutes'
> & {
  data_source: 'tj_live';
  trip_load_factor: number | null;
  label_kepadatan: BusPosisiSimulasi['label_kepadatan'] | null;
  estimated_passengers: number | null;
  capacity: number | null;
};

export type BusPosisi = BusPosisiSimulasi | BusPosisiAsli;

export type PosisiBusResponse = GeoJSON.FeatureCollection<GeoJSON.Point, BusPosisi>;

export type PosisiBusAsliResponse = GeoJSON.FeatureCollection<GeoJSON.Point, BusPosisiAsli> & {
  connected: boolean;
};

// Teks status di bawah jam saat mode waktu nyata.
export function statusBusAsli(data: PosisiBusAsliResponse | undefined, isError: boolean): string {
  if (isError) return 'Bus asli tidak dapat dimuat. Pastikan server backend berjalan.';
  if (!data) return 'Memuat posisi bus asli…';
  if (!data.connected) return 'Menyambung ke data bus TransJakarta…';
  return `${data.features.length} bus asli di peta`;
}

export type NaikItem = {
  tipe: 'naik';
  dari: string;
  ke: string;
  naik_di_id: string;
  turun_di_id: string;
  koridor_id: number;
  nama_koridor: string | null;
  naik_di: string;
  turun_di: string;
  kepadatan: number;
  waktu_menit: number;
  jarak_meter?: number;
  jumlah_segmen: number;
  segmen_detail: SegmenDetail[];
  // Diisi oleh Algoritma 2 (backend services/bus_selector.py). Null bila tidak
  // ada bus kandidat (sudah lewat semua / kepadatan tidak tersedia).
  bus_rekomendasi?: BusRekomendasi | null;
};

export type TransitItem = {
  tipe: 'transit';
  transit_di: string;
  transit_di_id: string;
  dari_koridor: number | null;
  ke_koridor: number;
};

export type RuteSegmen = NaikItem | TransitItem;

export type Rute = {
  skor: number;
  primary_score?: number;
  total_jarak_meter?: number;
  jumlah_transit: number;
  estimasi_menit: number;
  rata_kepadatan: number;
  density_source?: 'selected_bus' | 'mixed_edge_fallback';
  density_norm?: number;
  ranking_method?: 'primary_score_then_density_rerank';
  ranking_phase_1?: {
    estimasi_menit: number;
    total_jarak_meter: number;
    jumlah_transit: number;
    time_norm: number;
    distance_norm: number;
    transfer_norm: number;
    primary_score: number;
    weights: {
      time: number;
      distance: number;
      transfer: number;
    };
  };
  ranking_phase_2?: {
    rata_kepadatan: number;
    density_norm: number;
  };
  segmen: RuteSegmen[];
};

export type ShapeFeature = GeoJSON.Feature<GeoJSON.LineString, {
  koridor_id: number | string;
  shape_id: string;
}>;

type ShapeIndex = Map<string, ShapeFeature[]>;

import { warnaKoridor } from './koridor';

export function normalisasiKepadatanDisplay(kepadatan: number): number {
  if (!Number.isFinite(kepadatan)) return 0;
  return Math.max(0, Math.min(kepadatan, 1));
}

// Pemetaan kepadatan (0..1) ke warna semafor. Threshold 0.4/0.7 dipilih
// supaya distribusi merah/kuning/hijau seimbang untuk kepadatan jam sibuk
// TransJakarta tipikal (mean ~0.5, std ~0.2).
// Satu-satunya palet kepadatan: teks, bar, cincin bus, dan legenda memakainya. Cukup gelap untuk
// terbaca di atas peta terang dan teks putih; samakan dengan --color-tj-sepi/-padat di globals.css.
export const WARNA_KEPADATAN = { sepi: '#15803d', sedang: '#b45309', padat: '#b91c1c' } as const;

export function kepadatanKeWarna(kepadatan: number): string {
  return WARNA_KEPADATAN[labelKepadatan(kepadatan)];
}

// Untuk label dari backend ('Sepi' | 'Sedang' | 'Padat').
export function warnaLabelKepadatan(label: 'Sepi' | 'Sedang' | 'Padat'): string {
  return WARNA_KEPADATAN[label.toLowerCase() as keyof typeof WARNA_KEPADATAN];
}

export function labelKepadatan(kepadatan: number): 'sepi' | 'sedang' | 'padat' {
  const value = normalisasiKepadatanDisplay(kepadatan);
  if (value < 0.4) return 'sepi';
  if (value < 0.7) return 'sedang';
  return 'padat';
}

function jarakKuadratKoordinat(a: [number, number], b: [number, number]): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function nearestCoordinateIndex(
  coordinates: [number, number][],
  target: [number, number],
): number {
  let bestIdx = 0;
  let bestDistance = Infinity;
  coordinates.forEach((coord, idx) => {
    const distance = jarakKuadratKoordinat(coord, target);
    if (distance < bestDistance) {
      bestIdx = idx;
      bestDistance = distance;
    }
  });
  return bestIdx;
}

function buildShapeIndex(
  shapes?: GeoJSON.FeatureCollection<GeoJSON.LineString, {
    koridor_id: number | string;
    shape_id: string;
  }>,
): ShapeIndex {
  const index: ShapeIndex = new Map();
  for (const feature of shapes?.features ?? []) {
    const key = String(feature.properties?.koridor_id ?? '');
    if (!key) continue;
    const list = index.get(key) ?? [];
    list.push(feature);
    index.set(key, list);
  }
  return index;
}

function coordinatesFromShape(
  shapeIndex: ShapeIndex,
  koridorId: number,
  a: Halte,
  b: Halte,
): [number, number][] | null {
  const candidates = shapeIndex.get(String(koridorId)) ?? [];
  if (candidates.length === 0) return null;

  const start: [number, number] = [a.lng, a.lat];
  const end: [number, number] = [b.lng, b.lat];
  let best: [number, number][] | null = null;
  let bestScore = Infinity;

  for (const feature of candidates) {
    const coordinates = feature.geometry.coordinates as [number, number][];
    if (coordinates.length < 2) continue;
    const startIdx = nearestCoordinateIndex(coordinates, start);
    const endIdx = nearestCoordinateIndex(coordinates, end);
    if (startIdx === endIdx) continue;

    const slice =
      startIdx < endIdx
        ? coordinates.slice(startIdx, endIdx + 1)
        : coordinates.slice(endIdx, startIdx + 1).reverse();
    if (slice.length < 2) continue;

    const score =
      jarakKuadratKoordinat(slice[0], start) +
      jarakKuadratKoordinat(slice[slice.length - 1], end);
    if (score < bestScore) {
      bestScore = score;
      best = slice;
    }
  }

  return best;
}

// Bangun FeatureCollection LineString. Tiap fine-grained segmen = 1 Feature
// dengan property `warna` yang dipakai oleh paint expression `['get', 'warna']`
// pada layer line MapLibre. Ini memberikan warna per-segmen tanpa membuat
// banyak layer terpisah.
export function buildRouteGeoJSON(
  segmen: RuteSegmen[],
  halteMap: Map<string, Halte>,
  shapes?: GeoJSON.FeatureCollection<GeoJSON.LineString, {
    koridor_id: number | string;
    shape_id: string;
  }>,
): GeoJSON.FeatureCollection<GeoJSON.LineString> {
  const features: GeoJSON.Feature<GeoJSON.LineString>[] = [];
  const shapeIndex = buildShapeIndex(shapes);
  for (const s of segmen) {
    if (s.tipe !== 'naik') continue;
    for (const d of s.segmen_detail) {
      const a = halteMap.get(d.dari_id);
      const b = halteMap.get(d.ke_id);
      if (!a || !b) continue;
      const coordinates = coordinatesFromShape(shapeIndex, s.koridor_id, a, b) ?? [
        [a.lng, a.lat],
        [b.lng, b.lat],
      ];
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates,
        },
        properties: {
          warna: warnaKoridor(s.koridor_id).bg,
          kepadatan: normalisasiKepadatanDisplay(d.kepadatan),
          koridor_id: s.koridor_id,
        },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}
