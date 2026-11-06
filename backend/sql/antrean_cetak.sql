-- Antrean cetak untuk printer thermal yang terpasang di komputer lain (mis. laptop kiosk).
--
-- Backend produksi jalan di server tanpa printer. Dengan PRINT_MODE=antrean, POST /api/print/*
-- menyusun byte ESC/POS lalu menaruhnya di sini; scripts/agen_cetak.py di komputer yang
-- ter-pairing dengan printer mengambilnya dan menulis ke port COM. Browser yang tidak punya
-- Web Bluetooth (Safari/iPad) memantau status baris lewat GET /api/print/antrean/{id}.
--
-- data_b64: byte ESC/POS siap tulis (base64). Dikosongkan begitu baris selesai/gagal, supaya
-- foto penumpang tidak tertinggal di database.
create table if not exists antrean_cetak (
    id bigint generated always as identity primary key,
    jenis text not null check (jenis in ('foto', 'tiket')),
    data_b64 text not null,
    status text not null default 'menunggu' check (status in ('menunggu', 'mencetak', 'selesai', 'gagal')),
    galat text,
    dibuat_pada timestamptz not null default now(),
    diproses_pada timestamptz
);

create index if not exists antrean_cetak_status_id on antrean_cetak (status, id);

-- RLS aktif tanpa policy: hanya service-role (backend & agen cetak) yang bisa akses.
alter table antrean_cetak enable row level security;

-- Semua batas waktu memakai jam server Postgres, jadi tidak terpengaruh selisih jam perangkat.
--   menunggu > 30 dtk   : tidak ada agen yang mengambil -> gagal (browser berhenti menunggu ±40 dtk).
--   mencetak > 2 menit  : agen mati di tengah cetak -> gagal.
--   umur > 1 hari       : dihapus.
create or replace function kedaluwarsakan_cetak() returns void
language sql as $$
    update antrean_cetak
       set status = 'gagal', galat = 'Agen cetak tidak merespons', data_b64 = '', diproses_pada = now()
     where status = 'menunggu' and dibuat_pada < now() - interval '30 seconds';

    update antrean_cetak
       set status = 'gagal', galat = 'Pencetakan terhenti', data_b64 = '', diproses_pada = now()
     where status = 'mencetak' and diproses_pada < now() - interval '2 minutes';

    delete from antrean_cetak where dibuat_pada < now() - interval '1 day';
$$;

-- Ambil satu cetakan tertua dan tandai 'mencetak' sekaligus (skip locked: dua agen tidak
-- pernah mendapat baris yang sama). Kosong bila antrean kosong.
create or replace function ambil_cetak() returns setof antrean_cetak
language plpgsql as $$
begin
    perform kedaluwarsakan_cetak();
    return query
        update antrean_cetak
           set status = 'mencetak', diproses_pada = now()
         where id = (
             select id from antrean_cetak where status = 'menunggu' order by id for update skip locked limit 1
         )
        returning *;
end;
$$;

create or replace function status_cetak(p_id bigint) returns table (status text, galat text)
language plpgsql as $$
begin
    perform kedaluwarsakan_cetak();
    return query select a.status, a.galat from antrean_cetak a where a.id = p_id;
end;
$$;

-- Fungsi baru otomatis boleh dipanggil siapa saja (termasuk anon lewat /rest/v1/rpc); batasi.
revoke execute on function kedaluwarsakan_cetak(), ambil_cetak(), status_cetak(bigint) from public, anon, authenticated;
grant execute on function kedaluwarsakan_cetak(), ambil_cetak(), status_cetak(bigint) to service_role;
