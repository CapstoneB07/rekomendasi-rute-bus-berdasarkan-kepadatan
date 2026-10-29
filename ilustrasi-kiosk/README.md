# Ilustrasi 3D kiosk TransJakarta Lega

Ilustrasi isometrik interaktif (mode 3D skill [Anatomy](https://github.com/wheresryan22/anatomy), lisensi MIT: `LICENSE-anatomy`). Terpisah dari `frontend/`; layar kiosk meniru beranda aplikasi (logo, maskot, warna biru #0f47a1 dan oranye #ee6a00).

- `node build.mjs` menulis `kiosk.html` (terang); `node build.mjs --dark` menulis `kiosk-gelap.html`.
- Buka berkasnya langsung di browser. Seret untuk memutar, panah kiri/kanan juga memutar, `P` atau ketuk untuk mencetak tiket.
- `node build.mjs --audit [--quick]` menjalankan audit geometri (audit penuh lama, belasan menit hingga puluhan menit).
- `kit/` dan `scripts/` adalah salinan dari skill Anatomy; aset logo dan maskot di `aset/` (maskot diperkecil dari `frontend/public`).
