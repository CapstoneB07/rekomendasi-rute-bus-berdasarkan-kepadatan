'use client';

import { useSyncExternalStore } from 'react';

function langgan(onChange: () => void) {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

// Status koneksi peramban; di server dianggap daring supaya render server dan klien sama.
export function useOnline(): boolean {
  return useSyncExternalStore(
    langgan,
    () => navigator.onLine,
    () => true,
  );
}
