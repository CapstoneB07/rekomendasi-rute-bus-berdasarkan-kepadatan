import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TransJakarta Lega",
    short_name: "TJ Lega",
    description: "Rekomendasi rute dan bus TransJakarta yang paling lega.",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#0f47a1",
    orientation: "landscape",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
