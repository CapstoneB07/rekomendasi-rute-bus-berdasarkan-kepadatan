'use client';

import { useSyncExternalStore } from 'react';

// Harus sama dengan `@custom-variant hp` di globals.css.
const QUERY_HP = '(max-width: 767px)';

function langgan(onChange: () => void) {
  const mq = window.matchMedia(QUERY_HP);
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

// Layar ponsel (tata letak satu kolom); di server dianggap bukan ponsel supaya render server dan klien sama.
export function useLayarHp(): boolean {
  return useSyncExternalStore(
    langgan,
    () => window.matchMedia(QUERY_HP).matches,
    () => false,
  );
}
