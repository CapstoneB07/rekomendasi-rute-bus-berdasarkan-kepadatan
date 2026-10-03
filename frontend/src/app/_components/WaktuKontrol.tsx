'use client';

import {
  JAM_MULAI,
  JAM_SELESAI,
  KECEPATAN,
  type WaktuSimulasi,
} from '@/lib/use-waktu-simulasi';

function formatJam(detik: number): string {
  const h = Math.floor(detik / 3600);
  const m = Math.floor((detik % 3600) / 60);
  const s = detik % 60;
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
}

export function WaktuKontrol({ waktu }: { waktu: WaktuSimulasi }) {
  const { simTime, isLive, isPlaying, kecepatan, aturJam, togglePlay, aturKecepatan, kembaliKeLive } = waktu;
  const berjalan = isLive || isPlaying;

  return (
    <section aria-label="Jam simulasi" className="rounded-2xl bg-white p-4 shadow-md">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlay}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700"
          aria-label={berjalan ? 'Jeda jam' : 'Jalankan jam'}
        >
          {berjalan ? '⏸' : '▶'}
        </button>

        <div className="min-w-0 flex-1">
          <div className="font-mono text-xl font-bold tabular-nums text-gray-900">
            {formatJam(simTime)} <span className="text-xs font-normal text-gray-500">WIB</span>
          </div>
          <div className={`text-xs font-medium ${isLive ? 'text-green-700' : 'text-amber-700'}`}>
            {isLive ? 'Waktu nyata' : 'Mode simulasi'}
          </div>
        </div>

        {!isLive && (
          <button
            type="button"
            onClick={kembaliKeLive}
            className="shrink-0 rounded-lg border border-red-600 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
          >
            Waktu nyata
          </button>
        )}
      </div>

      <input
        type="range"
        min={JAM_MULAI}
        max={JAM_SELESAI}
        step={60}
        value={Math.min(Math.max(simTime, JAM_MULAI), JAM_SELESAI)}
        onChange={(e) => aturJam(Number(e.target.value))}
        className="mt-3 w-full accent-red-600"
        aria-label="Geser jam simulasi"
      />
      <div className="flex justify-between text-[10px] text-gray-400" aria-hidden>
        <span>05:00</span>
        <span>23:00</span>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-gray-500">Kecepatan</span>
        {KECEPATAN.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => aturKecepatan(k)}
            aria-pressed={!isLive && kecepatan === k}
            className={`rounded border px-2.5 py-1 text-xs font-medium ${
              !isLive && kecepatan === k
                ? 'border-gray-900 bg-gray-900 text-white'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            {k}×
          </button>
        ))}
      </div>
    </section>
  );
}
