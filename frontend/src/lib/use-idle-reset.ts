'use client';

import { useEffect, useRef, useState } from 'react';

const EVENT_SENTUH = ['pointerdown', 'keydown', 'wheel'] as const;
const CEK_MS = 250;

// Panggil `onIdle` bila tidak ada sentuhan selama `ms`. Hanya jalan saat `aktif`.
// Pada `peringatanMs` terakhir sebelum reset, mengembalikan sisa detik (null di luar jendela itu).
export function useIdleReset(onIdle: () => void, ms: number, aktif: boolean, peringatanMs = 0): number | null {
  const onIdleRef = useRef(onIdle);
  const [sisaDetik, setSisaDetik] = useState<number | null>(null);
  useEffect(() => {
    onIdleRef.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!aktif) return;
    let mulai = Date.now();
    const cek = () => {
      const sisa = ms - (Date.now() - mulai);
      if (sisa <= 0) {
        setSisaDetik(null);
        onIdleRef.current();
        return;
      }
      setSisaDetik(sisa <= peringatanMs ? Math.ceil(sisa / 1000) : null);
    };
    const timer = setInterval(cek, CEK_MS);
    const ulang = () => {
      mulai = Date.now();
      setSisaDetik(null);
    };
    EVENT_SENTUH.forEach((e) => window.addEventListener(e, ulang, { passive: true }));
    return () => {
      clearInterval(timer);
      EVENT_SENTUH.forEach((e) => window.removeEventListener(e, ulang));
    };
  }, [ms, aktif, peringatanMs]);

  return aktif ? sisaDetik : null;
}
