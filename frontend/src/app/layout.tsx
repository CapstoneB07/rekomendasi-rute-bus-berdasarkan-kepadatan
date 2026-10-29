import type { Metadata, Viewport } from "next";
import { Noto_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { RegistrasiSw } from "./registrasi-sw";

const notoSans = Noto_Sans({
  variable: "--font-noto",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "TransJakarta Lega",
  description: "Rekomendasi rute dan bus TransJakarta yang paling lega.",
  icons: { apple: "/apple-touch-icon.png" },
  appleWebApp: {
    capable: true,
    title: "TJ Lega",
    statusBarStyle: "default",
  },
};

// Kiosk iPad: tanpa zoom cubit/dobel-ketuk, memenuhi seluruh layar.
export const viewport: Viewport = {
  themeColor: "#2f489c",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" className={`${notoSans.variable} h-full antialiased`}>
      <body className="h-full" suppressHydrationWarning>
        <Providers>{children}</Providers>
        <RegistrasiSw />
      </body>
    </html>
  );
}
