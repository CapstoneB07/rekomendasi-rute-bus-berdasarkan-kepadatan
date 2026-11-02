This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Photobox operator (cetak foto kamera ke printer thermal)

Tombol **Ambil Foto** di `/operator` (panel kamera) mengambil frame + kotak deteksi
terbaru, menampilkan pratinjau 1-bit, lalu mencetaknya ke struk thermal 80 mm.

Tombol **Cetak** mengirim bitmap 1-bit (576 dot, kertas 80 mm) ke
`POST /api/print/foto`. Backend membungkusnya menjadi ESC/POS raster (`GS v 0`) dan
menulisnya langsung ke port serial Bluetooth printer, jadi **tanpa driver printer Windows**
dan tanpa dialog cetak browser. Backend harus berjalan di komputer yang ter-pairing dengan printer.

Setup (Windows):

1. Pasangkan printer di Pengaturan > Bluetooth & perangkat. Windows membuat port
   "Standard Serial over Bluetooth link (COMn)" untuknya; cari nomornya di Device Manager
   (Ports) atau lewat properti perangkat Bluetooth.
2. Set `PRINTER_PORT` (default `COM13`) di lingkungan backend, mis. `PRINTER_PORT=COM13`.
3. Jalankan backend, buka `/operator`, tekan **Ambil Foto** lalu **Cetak**.

Port COM bersifat eksklusif: tutup aplikasi lain yang memakai printer (mis. OpenLabel di
komputer yang sama) sebelum mencetak. Printer mati/di luar jangkauan menghasilkan 503 dan
pesan di dialog.

Catatan: lebar gambar = `LEBAR_DOT_80MM` (576 dot, area cetak 72 mm @ 203 dpi) di `src/lib/photobox.ts`.
Bila kepala cetak printer hanya 58 mm (384 dot), ubah konstanta itu ke 384. Gambar dicetak 1:1 per dot.
Frame diambil lewat `GET /api/live/camera/snapshot` (backend yang mengunduh dari
Supabase), sehingga gambar dan bbox selalu dari frame yang sama dan tanpa CORS.
