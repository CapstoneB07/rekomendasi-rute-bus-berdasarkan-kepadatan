'use client';

import { useEffect } from 'react';

// Service worker hanya didaftarkan di build produksi; di dev, cache-nya mengganggu HMR.
export function RegistrasiSw() {
  useEffect(() => {
    if (process.env.NODE_ENV === 'production' && 'serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  }, []);
  return null;
}
