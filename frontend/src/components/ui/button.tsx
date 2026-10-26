import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

// Tombol ala shadcn/ui, ukuran disesuaikan untuk jari di kiosk (rem ikut skala layar).
const VARIAN = {
  default: 'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
  outline: 'border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  ghost: 'hover:bg-accent hover:text-accent-foreground',
  destructive: 'bg-destructive text-white shadow-xs hover:bg-destructive/90',
} as const;

const UKURAN = {
  default: 'h-[2.4rem] px-[0.9rem] text-isi',
  sm: 'h-[2rem] rounded-md px-[0.6rem] text-kecil',
  lg: 'h-[2.8rem] px-[1.2rem] text-isi',
  // Tombol ikon selalu bulat supaya mudah dibedakan dari tombol berlabel.
  icon: 'size-[2rem] rounded-full',
} as const;

export type VarianTombol = keyof typeof VARIAN;

export function tombolVarian({
  varian = 'default',
  ukuran = 'default',
  className,
}: { varian?: VarianTombol; ukuran?: keyof typeof UKURAN; className?: string } = {}) {
  return cn(
    'inline-flex shrink-0 items-center justify-center gap-[0.5rem] whitespace-nowrap rounded-lg font-medium transition-colors disabled:opacity-50 [&_svg]:shrink-0',
    VARIAN[varian],
    UKURAN[ukuran],
    className,
  );
}

type Props = ComponentProps<'button'> & {
  varian?: VarianTombol;
  ukuran?: keyof typeof UKURAN;
};

export function Button({ varian, ukuran, className, type = 'button', ...props }: Props) {
  return <button type={type} className={tombolVarian({ varian, ukuran, className })} {...props} />;
}
