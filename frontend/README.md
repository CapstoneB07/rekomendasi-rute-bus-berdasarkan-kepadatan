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

Setup komputer operator (printer thermal via USB):

1. Pasang driver printer, jadikan **printer default** Windows, ukuran kertas **80 mm**
   (roll), margin 0 atau minimum, skala 100%.
2. Jalankan Chrome dalam mode cetak langsung (tanpa dialog):

   ```
   chrome.exe --kiosk-printing --app=https://<alamat-frontend>/operator
   ```

Catatan: gambar dibuat selebar 576 dot (area cetak 80 mm @ 203 dpi) dan dicetak 1:1.
Bila printer memakai 58 mm, ubah `LEBAR_DOT_80MM` di `src/lib/photobox.ts` menjadi 384.
Frame diambil lewat `GET /api/live/camera/snapshot` (backend yang mengunduh dari
Supabase), sehingga gambar dan bbox selalu dari frame yang sama dan tanpa CORS.
