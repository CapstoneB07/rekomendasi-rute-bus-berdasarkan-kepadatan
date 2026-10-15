-- Frame kamera terbaru + bounding box deteksi dari CV worker (repo kepadatan-bus-cv).
-- Satu baris per bus fisik; worker mengunggah frame ke bucket Storage
-- `kamera-frames` lalu meng-upsert baris ini. Backend membacanya per request.
--
-- bboxes: array objek {"x","y","w","h","kelas","skor"}; x,y,w,h dalam piksel
-- frame asli (x,y = pojok kiri atas), skor 0..1.
create table if not exists kamera_live (
    bus_id text primary key,
    frame_path text not null,
    bboxes jsonb not null default '[]'::jsonb check (jsonb_typeof(bboxes) = 'array'),
    updated_at timestamptz not null default now()
);

-- Jam dari server Postgres (sama seperti kepadatan_live) agar cek basi tidak
-- terpengaruh selisih jam perangkat worker.
create or replace function kamera_live_touch() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists kamera_live_touch on kamera_live;
create trigger kamera_live_touch
    before insert or update on kamera_live
    for each row execute function kamera_live_touch();

-- RLS aktif tanpa policy: hanya service-role (backend & worker) yang bisa akses.
alter table kamera_live enable row level security;

-- Bucket privat; backend menyajikan frame lewat signed URL berumur pendek.
insert into storage.buckets (id, name, public)
values ('kamera-frames', 'kamera-frames', false)
on conflict (id) do nothing;
