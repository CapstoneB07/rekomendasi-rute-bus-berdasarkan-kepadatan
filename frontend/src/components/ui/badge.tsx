import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

const VARIAN = {
  default: 'border-transparent bg-primary text-primary-foreground',
  secondary: 'border-transparent bg-secondary text-secondary-foreground',
  outline: 'text-foreground',
  destructive: 'border-transparent bg-destructive text-white',
  sukses: 'border-transparent bg-tj-sepi text-white',
  peringatan: 'border-transparent bg-tj-oranye text-white',
} as const;

type Props = ComponentProps<'span'> & { varian?: keyof typeof VARIAN };

// Lencana ala shadcn/ui.
export function Badge({ varian = 'default', className, ...props }: Props) {
  return (
    <span
      className={cn(
        'inline-flex w-fit shrink-0 items-center justify-center gap-[0.3rem] whitespace-nowrap rounded-md border px-[0.4rem] text-kecil font-medium leading-[1.5rem]',
        VARIAN[varian],
        className,
      )}
      {...props}
    />
  );
}
