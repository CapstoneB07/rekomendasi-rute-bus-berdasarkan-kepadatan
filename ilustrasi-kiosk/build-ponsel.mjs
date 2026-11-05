// Ilustrasi isometrik 3D ponsel TransJakarta Lega (skill Anatomy, mode 3D), layar menampilkan beranda aplikasi.
// Satuan model: milimeter nyata x M. x ke kanan, y ke depan ponsel, z ke atas.
// Jalankan: node build-ponsel.mjs [--dark]
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";
import * as G from "./kit/lathe.mjs";
import * as A from "./kit/audit.mjs";
import { turning } from "./kit/turn-build.mjs";
import { turnScript } from "./scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const theme = argv.includes("--dark") ? "dark" : "light";

const WIDTH = 560;
const HEIGHT = 720;
const AZIMUTH = 52;
const ELEVATION = 24;
const M = 0.25;
const m = (v) => v * M;
const rect = (x, y, w, d, r = 0) => ({ x: m(x), y: m(y), w: m(w), d: m(d), r: m(r) });

// ---- ukuran (mm): ponsel 140 x 320 x 14 melayang miring ----
const TILT = 20;
const PHONE = { halfW: 70, halfH: 160, halfT: 7, zc: 215 };
const SCREEN = { halfW: 66, halfH: 152 };
const THETA = (TILT * Math.PI) / 180;
const COS = Math.cos(THETA);
const SIN = Math.sin(THETA);
const N = [0, COS, SIN];
const TUP = [0, -SIN, COS];

const FIT = [];
for (let i = 0; i < 48; i++) for (const z of [PHONE.zc - 165, PHONE.zc + 165]) FIT.push([m(95) * Math.cos((i / 48) * Math.PI * 2), m(95) * Math.sin((i / 48) * Math.PI * 2), m(z)]);
export const P = k.fitProjection(FIT, WIDTH, HEIGHT, { pad: 18, azimuth: AZIMUTH, elevation: ELEVATION });
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const w3 = (p) => p.map((v) => v * M);

export const R = A.recorder(P);
const put = (item) => R.put({ ...item, shapes: item.shapes.map((shape, index) => R.solid(Object.assign(shape, { name: shape.name ?? (index ? `${item.name}#${index + 1}` : item.name) }))) });

export const T = turning(P, { recorder: R });
const ponsel = T.group("ponsel", { turn: { pivot: [0, 0] } });
const body = T.layer("ponsel");
T.stack(["ponsel"]);
export const follow = (values) => ({ ...values });
export const poses = () => {
  const list = [];
  for (let deg = 0; deg < 360; deg += 6) list.push(follow({ ponsel: deg }));
  return list;
};

// ---- bantu ----
const frame = (o, a, u) => {
  const axis = G.unit3(a);
  const uu = G.unit3(G.sub3(u, G.mul3(axis, G.dot3(u, axis))));
  return { o, a: axis, u: uu, v: G.cross3(axis, uu) };
};
const roundRect = (cu, cv, hu, hv, r, steps = 3) => {
  const out = [];
  for (const [sx, sy, a0] of [[1, 1, 0], [-1, 1, 90], [-1, -1, 180], [1, -1, 270]]) {
    for (let i = 0; i <= steps; i++) {
      const a = ((a0 + (90 * i) / steps) * Math.PI) / 180;
      out.push([cu + sx * (hu - r) + r * Math.cos(a), cv + sy * (hv - r) + r * Math.sin(a)]);
    }
  }
  return out;
};
const slab = (name, plan, z0, z1, extra = {}) => T.prism({ name, group: ponsel, layer: body, plan: rect(...plan), z: m(z0), h: m(z1 - z0), steps: extra.steps ?? 4, ...extra });
// Bidang ponsel: sumbu y keluar dari muka depan; (u, v) = (z, x). Bidang belakang: sumbu -y, (u, v) = (z, -x).
const FRONT = (y) => frame(w3([0, y, 0]), [0, 1, 0], [0, 0, 1]);
const BACK = (y) => frame(w3([0, y, 0]), [0, -1, 0], [0, 0, 1]);

// ponsel melayang, dimiringkan ke belakang pada sumbu x: N = normal layar, TUP = arah atas layar
const C = [0, 0, PHONE.zc];
const at = (u, v, d) => [C[0] + v + 0, C[1] - u * SIN + d * COS, C[2] + u * COS + d * SIN];
const FACE = (d) => frame(w3(at(0, 0, d)), N, TUP);
const FACE_BACK = (d) => frame(w3(at(0, 0, d)), N.map((v) => -v), TUP);

// badan ponsel: persegi panjang bersudut bulat, tepi dibevel
T.prism({ name: "ponsel.badan", group: ponsel, layer: body, F: FACE(-PHONE.halfT), polygon: roundRect(0, 0, m(PHONE.halfH), m(PHONE.halfW), m(20), 5), s0: 0, s1: m(2 * PHONE.halfT), tone: "hi", crease: "faint", material: "steel", bevel: 1.1 });
// kaca layar
const GLASS_T = [0, m(1.2)];
const glass = T.prism({ name: "ponsel.kaca", group: ponsel, layer: body, F: FACE(PHONE.halfT), polygon: roundRect(0, 0, m(SCREEN.halfH), m(SCREEN.halfW), m(14), 4), s0: GLASS_T[0], s1: GLASS_T[1], tone: "mid", crease: "lo", material: "gunmetal" });

// tombol samping kanan (daya dan volume): persegi panjang di bidang (y, z) ikut miring
const sideButton = (name, t0, t1) => {
  const pts = [[t0, -2.5], [t1, -2.5], [t1, 2.5], [t0, 2.5]].map(([u, d]) => at(u, 0, d)).map(([, y, z]) => [m(y), m(z)]);
  const area = pts.reduce((s, [y, z], i) => s + y * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * z, 0);
  T.prism({ name, group: ponsel, layer: body, F: frame(w3([PHONE.halfW, 0, 0]), [1, 0, 0], [0, 1, 0]), polygon: area < 0 ? pts.reverse() : pts, s0: 0, s1: m(2.4), tone: "mid", material: "steel", crease: "lo", bevel: 0.2 });
};
sideButton("ponsel.tombol.daya", -60, -20);
sideButton("ponsel.tombol.volume", 0, 45);

// modul kamera di punggung (kiri atas jika dilihat dari belakang; v = -x)
T.prism({ name: "kamera.modul", group: ponsel, layer: body, F: FACE_BACK(-PHONE.halfT), polygon: roundRect(m(112), m(-34), m(24), m(24), m(9), 4), s0: 0, s1: m(3), tone: "mid", crease: "lo", material: "gunmetal", bevel: 0.4 });
const backPoint = (x, u, d) => at(u, x, -d);
for (const [i, [x, u]] of [[44, 124], [44, 100]].entries()) {
  T.round({ name: `kamera.lensa.${i}`, group: ponsel, layer: body, F: frame(w3(backPoint(x, u, PHONE.halfT + 3)), N.map((v) => -v), TUP), s0: 0, s1: m(1.8), r: m(8), tone: "lo", material: "chrome", crease: "lo" });
  T.round({ name: `kamera.kaca.${i}`, group: ponsel, layer: body, F: frame(w3(backPoint(x, u, PHONE.halfT + 4.8)), N.map((v) => -v), TUP), s0: 0, s1: m(0.8), r: m(5), tone: "lo", material: "gunmetal" });
}
T.round({ name: "kamera.lampu", group: ponsel, layer: body, F: frame(w3(backPoint(24, 124, PHONE.halfT + 3)), N.map((v) => -v), TUP), s0: 0, s1: m(1), r: m(3.2), tone: "mid", material: "brass" });

// isi layar: beranda aplikasi (versi ponsel: satu kolom, ilustrasi di atas judul)
const asset = (name) => `data:image/png;base64,${readFileSync(join(HERE, "aset", name)).toString("base64")}`;
const logo = asset("logo-transjakarta-putih.png");
const mascot = asset("maskot-bus.png");
const screenSvg = () => {
  const U = 3;
  const W = (2 * SCREEN.halfW) * U;
  const H = (2 * SCREEN.halfH) * U;
  const font = "Noto Sans, Segoe UI, Arial, sans-serif";
  const pill = (x, y, w, h, r, fill, stroke = "none") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
  const txt = (x, y, size, weight, fill, text, anchor = "start") => `<text x="${x}" y="${y}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${text}</text>`;
  const ink = "#09090b";
  const muted = "#52525b";
  const blue = "#2f489c";
  // Sudut isi layar dipotong sama bulat dengan kaca (radius 14 mm).
  return `<g transform="scale(${M / U})"><clipPath id="ponsel-layar"><rect width="${W}" height="${H}" rx="${14 * U}"/></clipPath><g clip-path="url(#ponsel-layar)">
    <rect width="${W}" height="${H}" fill="#ffffff"/>
    <circle cx="${W / 2}" cy="15" r="6" fill="#09090b"/>
    ${txt(24, 21, 13, 700, ink, "08:30")}
    <rect x="${W - 54}" y="11" width="24" height="11" rx="3" fill="none" stroke="${ink}" stroke-width="1.5"/><rect x="${W - 52}" y="13" width="17" height="7" rx="1.5" fill="${ink}"/>
    <rect y="30" width="${W}" height="62" fill="${blue}"/><rect y="92" width="${W}" height="4" fill="#d62126"/>
    ${txt(16, 54, 11, 400, "#ffffffcc", "Anda di halte")}
    ${txt(16, 78, 19, 700, "#ffffff", "Bundaran HI")}
    <image href="${logo}" x="${W / 2 + 6}" y="42" width="100" height="26" preserveAspectRatio="xMidYMid meet"/>
    ${txt(W - 16, 78, 27, 700, "#ffffff", "08:30", "end")}
    <ellipse cx="${W / 2}" cy="258" rx="118" ry="60" fill="#eef1f9"/>
    <image href="${mascot}" x="${W / 2 - 128}" y="186" width="256" height="160" preserveAspectRatio="xMidYMid meet"/>
    ${txt(W / 2, 400, 27, 700, ink, "Cari Rute Bus", "middle")}
    ${txt(W / 2, 432, 27, 700, ink, "yang Nyaman", "middle")}
    ${txt(W / 2, 462, 15, 400, muted, "Pilih perjalanan yang nyaman,", "middle")}
    ${txt(W / 2, 483, 15, 400, muted, "TJ siap membantu Anda.", "middle")}
    ${pill(20, 516, W - 40, 62, 14, "#ffffff", "#d4d4d8")}
    ${pill(30, 526, 42, 42, 10, "#eef1f9")}
    <circle cx="51" cy="543" r="7" fill="none" stroke="${blue}" stroke-width="3"/><path d="M51 550 L51 556" stroke="${blue}" stroke-width="3"/>
    ${txt(86, 543, 13, 400, muted, "Ke:")}
    ${txt(86, 565, 17, 500, muted, "Sentuh untuk memilih tujuan…")}
    <path d="M${W - 48} 544 l7 7 7 -7" stroke="${muted}" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    ${pill(20, 594, W - 40, 62, 14, blue)}
    <circle cx="${W / 2 - 52}" cy="624" r="9" fill="none" stroke="#fff" stroke-width="3.2"/><path d="M${W / 2 - 45} 631 L${W / 2 - 38} 638" stroke="#fff" stroke-width="3.2"/>
    ${txt(W / 2 - 24, 633, 21, 700, "#ffffff", "Cari Rute")}
    <path d="M0 ${H - 50} H${W}" stroke="#e4e4e7" stroke-width="1.5"/>
    <rect x="${W / 2 - 52}" y="${H - 16}" width="104" height="5" rx="2.5" fill="${ink}"/>
  </g></g>`;
};
const screenO = w3(at(SCREEN.halfH, -SCREEN.halfW, PHONE.halfT + 1.2 + 0.04));
T.plane({ part: glass, o: screenO, u: [1, 0, 0], v: TUP.map((x) => -x), svg: screenSvg(), normal: N, fade: [0.02, 0.2] });

const out = T.build({ statics: R.items, poses });
A.settle(R, P);
const BACKDROP = [];

const LABEL = "Ponsel melayang miring: layar menampilkan beranda aplikasi TransJakarta Lega, punggungnya berisi modul kamera.";
const backSvg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: LABEL, body: BACKDROP });
const stage = `<div class="iso-stage iso-turn ks-stage" tabindex="0" role="slider" aria-label="Ponsel: seret untuk memutar, panah kiri kanan juga memutar" aria-valuemin="0" aria-valuemax="359" aria-valuenow="0" aria-valuetext="ponsel menghadap depan">${backSvg}${out.layerSvg("ponsel", { width: WIDTH, height: HEIGHT })}</div>`;
const LIVE = readFileSync(join(HERE, "live-ponsel.js"), "utf8").replace("__DATA__", JSON.stringify({ turn: out.data }));
const CSS = out.css + "\n" + readFileSync(join(HERE, "kiosk.css"), "utf8");
const content = k.plateHtml({
  fig: "Gbr 3D",
  title: "Ponsel TransJakarta Lega",
  hint: "Seret untuk memutar",
  readout: "ponsel 0°",
  keys: [{ mark: "raised", label: "Ponsel: satu grup putar" }],
  caption: "Layar menampilkan beranda aplikasi versi ponsel: satu kolom, maskot di atas judul, lalu pilihan tujuan dan tombol Cari Rute.",
  body: `<style>${CSS}</style>${stage}`,
});
const page = k.pageHtml({ title: "Ponsel TransJakarta Lega", theme, body: content, script: turnScript() + LIVE, width: 640 });
const name = `ponsel${theme === "dark" ? "-gelap" : ""}.html`;
writeFileSync(join(HERE, name), page);
console.log(`wrote ${name} · ${(page.length / 1024).toFixed(0)} KB · ${out.report.parts} parts · build ${out.report.seconds.toFixed(1)} s`);
