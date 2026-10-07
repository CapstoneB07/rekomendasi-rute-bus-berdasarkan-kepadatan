// Ikon SVG inline (tanpa dependensi). Warna mengikuti `currentColor`.

type Props = { className?: string };

const dasar = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2.2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export function IkonBus({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <rect x="4" y="3" width="16" height="14" rx="3" />
      <path d="M4 11h16M8 21v-3M16 21v-3" />
      <circle cx="8.5" cy="14" r="0.6" fill="currentColor" />
      <circle cx="15.5" cy="14" r="0.6" fill="currentColor" />
    </svg>
  );
}

export function IkonPanahKiri({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M19 12H5M11 6l-6 6 6 6" />
    </svg>
  );
}

export function IkonChevronKanan({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

export function IkonLokasi({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
      <circle cx="12" cy="9.5" r="2.5" />
    </svg>
  );
}

export function IkonCari({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-4-4" />
    </svg>
  );
}

export function IkonBantuan({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01" />
    </svg>
  );
}

export function IkonCetak({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M7 9V3h10v6M7 17H4v-7h16v7h-3" />
      <rect x="7" y="14" width="10" height="7" />
    </svg>
  );
}

export function IkonCaretBawah({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function IkonTutup({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function IkonMain({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M8 5l11 7-11 7z" fill="currentColor" />
    </svg>
  );
}

export function IkonJeda({ className }: Props) {
  return (
    <svg {...dasar} className={className}>
      <path d="M8 5v14M16 5v14" strokeWidth={3.4} />
    </svg>
  );
}
