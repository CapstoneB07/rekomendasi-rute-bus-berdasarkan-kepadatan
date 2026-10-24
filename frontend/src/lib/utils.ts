import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// Ukuran teks kiosk (globals.css) harus dikenali sebagai ukuran font, bukan warna,
// supaya `text-isi` tidak menghapus `text-primary-foreground` saat digabung.
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ['kecil', 'isi', 'besar', 'judul', 'jam'] } },
});

// Penggabung kelas ala shadcn/ui: kelas pemanggil menimpa kelas bawaan komponen.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
