import { describe, expect, it } from 'vitest';

import { cn } from './utils';

describe('cn', () => {
  it('ukuran teks kiosk tidak bentrok dengan warna teks', () => {
    expect(cn('text-isi text-primary-foreground', 'text-kecil')).toBe('text-primary-foreground text-kecil');
  });

  it('kelas pemanggil menimpa kelas bawaan', () => {
    expect(cn('h-[2.4rem] px-[0.9rem]', 'h-[2.8rem]', false && 'hidden')).toBe('px-[0.9rem] h-[2.8rem]');
  });
});
