import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

// Kartu ala shadcn/ui: permukaan berbingkai tipis dengan bayangan halus.
export function Card({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('rounded-xl border bg-card text-card-foreground shadow-sm', className)} {...props} />;
}
