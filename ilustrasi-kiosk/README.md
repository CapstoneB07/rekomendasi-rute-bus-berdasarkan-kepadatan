# Ilustrasi 3D kiosk TransJakarta Lega

Ilustrasi isometrik interaktif (mode 3D skill [Anatomy](https://github.com/wheresryan22/anatomy), lisensi MIT: `LICENSE-anatomy`). Terpisah dari `frontend/`; layar kiosk meniru beranda aplikasi (logo, maskot, warna biru #2f489c dan oranye #ee6a00).

- `node build.mjs` menulis `kiosk.html` (terang); `node build.mjs --dark` menulis `kiosk-gelap.html`.
- Empat tab di atas kiosk mengganti layar: Beranda, Daftar rencana, Detail rencana, dan Cetak panduan (tampilan setelah Cetak Informasi ditekan: pratinjau tiket di layar dan tiket keluar dari slot). Layar selain beranda memakai tata letak dua kolom aplikasi dengan peta di kanan (`aset/peta-rute.jpeg`, tangkapan peta basemap OpenFreeMap dengan rute Bundaran HI ke Blok M).
- Buka berkasnya langsung di browser. Seret untuk memutar, panah kiri/kanan juga memutar, `P` atau ketuk untuk mencetak tiket.
- `node build.mjs --audit [--quick]` menjalankan audit geometri (audit penuh lama, belasan menit hingga puluhan menit).
- `kit/` dan `scripts/` adalah salinan dari skill Anatomy; aset logo dan maskot di `aset/` (maskot diperkecil dari `frontend/public`).
- `node build-ponsel.mjs` menulis `ponsel.html` (terang); `--dark` menulis `ponsel-gelap.html`. Ilustrasi 3D ponsel yang melayang miring (20° ke belakang pada sumbu x), layarnya beranda versi ponsel (satu kolom). Skrip geraknya `live-ponsel.js`.
