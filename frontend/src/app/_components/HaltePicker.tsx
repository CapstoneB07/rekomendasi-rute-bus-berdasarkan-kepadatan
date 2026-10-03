'use client';

import { useId, useMemo, useState } from 'react';

export type HalteOpsi = {
  halte_id: string;
  nama: string;
  koridor_list: number[];
};

type Props = {
  label: string;
  placeholder: string;
  halteList: HalteOpsi[];
  value: string | null;
  onChange: (halteId: string | null) => void;
  disabled?: boolean;
};

const MAKS_OPSI = 8;

export function HaltePicker({ label, placeholder, halteList, value, onChange, disabled }: Props) {
  const inputId = useId();
  const listId = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);

  const terpilih = useMemo(
    () => halteList.find((h) => h.halte_id === value) ?? null,
    [halteList, value],
  );

  const opsi = useMemo(() => {
    const q = query.trim().toLowerCase();
    const hasil = q
      ? halteList.filter((h) => h.nama.toLowerCase().includes(q))
      : halteList;
    return hasil.slice(0, MAKS_OPSI);
  }, [halteList, query]);

  const pilih = (h: HalteOpsi) => {
    onChange(h.halte_id);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className="relative">
      <label htmlFor={inputId} className="block text-xs font-medium text-gray-600 mb-1">
        {label}
      </label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={open ? query : terpilih?.nama ?? query}
        onFocus={() => {
          setQuery('');
          setOpen(true);
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onBlur={() => setOpen(false)}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-red-600 focus:outline-none focus:ring-2 focus:ring-red-600/20 disabled:bg-gray-100"
      />
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg"
        >
          {opsi.length === 0 ? (
            <li className="px-3 py-2.5 text-sm text-gray-500">Halte tidak ditemukan</li>
          ) : (
            opsi.map((h) => (
              <li
                key={h.halte_id}
                role="option"
                aria-selected={h.halte_id === value}
                // onMouseDown, bukan onClick: blur input terjadi lebih dulu dan
                // menutup list sebelum click sempat terdaftar.
                onMouseDown={(e) => {
                  e.preventDefault();
                  pilih(h);
                }}
                className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2.5 text-sm text-gray-900 hover:bg-red-50"
              >
                <span>{h.nama}</span>
                <span className="shrink-0 text-[11px] text-gray-500">
                  Koridor {h.koridor_list.join(', ')}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
