-- Kepadatan bus nyata dari CV worker (repo kepadatan-bus-cv).
-- Satu baris per bus fisik; worker meng-upsert, backend memolling.
create table if not exists kepadatan_live (
    bus_id text primary key,
    jumlah_penumpang integer not null check (jumlah_penumpang >= 0),
    updated_at timestamptz not null default now()
);

-- Jam diambil dari server Postgres, bukan dari mesin worker, supaya cek
-- staleness di backend tidak terpengaruh selisih jam perangkat.
create or replace function kepadatan_live_touch() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists kepadatan_live_touch on kepadatan_live;
create trigger kepadatan_live_touch
    before insert or update on kepadatan_live
    for each row execute function kepadatan_live_touch();

-- RLS aktif tanpa policy: anon key (yang bisa terlihat di frontend) tidak bisa
-- membaca atau menulis. Backend dan CV worker memakai service-role key, yang
-- harus disimpan hanya di server/perangkat worker.
alter table kepadatan_live enable row level security;
