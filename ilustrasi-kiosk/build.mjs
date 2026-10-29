// Ilustrasi isometrik 3D kiosk TransJakarta Lega (skill Anatomy, mode 3D).
// Satuan model: milimeter nyata x M. x ke kanan, y ke depan kiosk, z ke atas.
// Jalankan: node build.mjs [--dark] [--audit] [--quick] [--only=a,b] [--verify]
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";
import * as G from "./kit/lathe.mjs";
import * as A from "./kit/audit.mjs";
import { turning } from "./kit/turn-build.mjs";
import * as TA from "./kit/turn-audit.mjs";
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

// ---- ukuran (mm) mengikuti gambar acuan: layar 1000-1300, slot tiket 700 ----
const BASE = [-470, -470, 940, 940, 470];
const BASE_H = 40;
const PLATTER_R = 360;
const Z_PLATTER = [0, 20];
const Z_PLINTH = [20, 60];
const Z_CAB = [60, 790];
const Z_TOP = 1350;
const CAP_H = 16;
const HALF_W = 280;
const UP_FRONT_TOP_Y = 33;
const UP_BACK_TOP_Y = -100;
const THETA = Math.atan((150 - UP_FRONT_TOP_Y) / (Z_TOP - Z_CAB[1]));
const COS = Math.cos(THETA);
const SIN = Math.sin(THETA);
const N = [0, COS, SIN];
const TUP = [0, -SIN, COS];
const faceAt = (l) => [0, 150 - l * SIN, Z_CAB[1] + l * COS];

const FIT = [];
for (let i = 0; i < 48; i++) for (const z of [-BASE_H - 18, 0, Z_TOP + CAP_H + 30]) FIT.push([m(470) * Math.cos((i / 48) * Math.PI * 2), m(470) * Math.sin((i / 48) * Math.PI * 2), m(z)]);
export const P = k.fitProjection(
  FIT,
  WIDTH,
  HEIGHT,
  { pad: 18, azimuth: AZIMUTH, elevation: ELEVATION },
);
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const VERT = (x, y) => G.frameOf([x * M, y * M, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0]);
const w3 = (p) => p.map((v) => v * M);

export const R = A.recorder(P);
const put = (item) => R.put({ ...item, shapes: item.shapes.map((shape, index) => R.solid(Object.assign(shape, { name: shape.name ?? (index ? `${item.name}#${index + 1}` : item.name) }))) });

// ---- alas statis: pelat lantai bundar berskala derajat dan empat kaki ----
function floor() {
  const plan = rect(...BASE);
  const baseH = m(BASE_H);
  const foot = m(18);
  for (const [sx, sy] of [[1, 1], [-1, 1], [-1, -1], [1, -1]]) {
    const x = sx * m(330);
    const y = sy * m(330);
    const svg = S(k.cylinder(x, y, m(34), -baseH - foot, m(7), P, 28), { tone: "lo" }) + S(k.cylinder(x, y, m(26), -baseH - foot + m(7), foot - m(7), P, 28), { tone: "mid" });
    put({ name: `lantai.kaki.${sx}.${sy}`, layer: "back", at: [x, y, -baseH - foot], svg, shapes: [A.cylinder(x, y, m(34), -baseH - foot, m(7), { ground: true }), A.cylinder(x, y, m(26), -baseH - foot + m(7), foot - m(7))] });
  }
  const ticks = k.radialTicks(0, 0, m(460), 120, 5, 0, [m(7), m(14)], P);
  const svg = S(k.slabOf(plan, -baseH, baseH, P, 24, 1.6), { tone: "mid", inner: L(k.sideSeam(plan, -baseH + m(16), P, 24), { tone: "faint" }) }) + L(k.ring(0, 0, m(460), 0, P, 96), { tone: "faint" }) + L(ticks.minor, { tone: "lo" }) + L(ticks.major, { tone: "mid" });
  put({ name: "lantai.pelat", layer: "back", at: [0, 0, -baseH], bias: 4, svg, shapes: [A.slab(plan, -baseH, baseH, { ground: true })] });
}

// ---- grup: kiosk berputar di atas piringan, tiket meluncur keluar dari slot ----
export const T = turning(P, { recorder: R });
const kiosk = T.group("kiosk", { turn: { pivot: [0, 0] } });
const TICKET_TRAVEL = 130;
const tiket = T.group("tiket", { parent: kiosk, slide: { direction: [0, 1, 0], travel: m(TICKET_TRAVEL) } });
const body = T.layer("kiosk");
T.stack(["back", "kiosk"]);
export const follow = (values) => ({ ...values });
export const printAt = (time) => {
  const phase = ((time % 7) + 7) % 7;
  const ease = (x) => x * x * (3 - 2 * x);
  const out = Math.min(1, Math.max(0, (phase - 0.6) / 1.5));
  const back = Math.min(1, Math.max(0, (phase - 4.6) / 1.1));
  return ease(out) * (1 - ease(back));
};
export const poses = () => {
  const list = [];
  for (let deg = 0; deg < 360; deg += 6) for (const s of [0, 0.25, 0.5, 0.75, 1]) list.push(follow({ kiosk: deg, tiket: s * m(TICKET_TRAVEL) }));
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
      out.push([cu + sx * (hu - r) + r * Math.cos(a) * 1 - (sx < 0 ? 2 * 0 : 0), cv + sy * (hv - r) + r * Math.sin(a) * 1]);
    }
  }
  return out;
};
const slab = (name, plan, z0, z1, extra = {}) => T.prism({ name, group: kiosk, layer: body, plan: rect(...plan), z: m(z0), h: m(z1 - z0), steps: extra.steps ?? 4, ...extra });
const upright = { o: [0, 0, 0], a: [1, 0, 0], u: [0, 1, 0], v: [0, 0, 1] };

// piringan putar + kaki plinth
T.round({ name: "kiosk.piringan", group: kiosk, layer: body, F: VERT(0, 0), s0: m(Z_PLATTER[0]), s1: m(Z_PLATTER[1]), r: m(PLATTER_R), tone: "mid", crease: "lo", material: "steel", details: { ribs: { s0: m(Z_PLATTER[0] + 3), s1: m(Z_PLATTER[1] - 3), count: 160, seams: true, tone: "lo" }, bolts: [{ s: m(Z_PLATTER[1]), r: m(342), count: 12, phase: 0.2, size: 0.5, tone: "mid" }] } });
slab("badan.plinth", [-290, -170, 580, 340, 18], Z_PLINTH[0], Z_PLINTH[1], { tone: "lo", crease: "lo", material: "gunmetal", bevel: 0.8 });
// Kabinet dipecah secara vertikal di sekeliling kantong tiket di tengah (celah 170 x 16 mm, dalam 140 mm):
// sisi kabinet tetap satu bidang utuh; sambungan vertikal di muka tinggal garis tipis.
const SLOT = { x0: -85, x1: 85, z0: 690, z1: 706, back: 10 };
const column = (name, x0, x1) => slab(name, [x0, -150, x1 - x0, 300, 1], Z_CAB[0], Z_CAB[1], { tone: "hi", crease: "faint", bevel: 0.6 });
const colLeft = column("badan.kolom.kiri", -HALF_W, SLOT.x0);
const colRight = column("badan.kolom.kanan", SLOT.x1, HALF_W);
slab("badan.kabinet", [SLOT.x0, -150, SLOT.x1 - SLOT.x0, 300, 1], Z_CAB[0], SLOT.z0, { tone: "hi", crease: "faint", bevel: 0.6 });
slab("badan.kabinet.atas", [SLOT.x0, -150, SLOT.x1 - SLOT.x0, 300, 1], SLOT.z1, Z_CAB[1], { tone: "hi", crease: "faint", bevel: 0.6 });
slab("slot.dinding", [SLOT.x0, -150, SLOT.x1 - SLOT.x0, SLOT.back + 150, 0.5], SLOT.z0, SLOT.z1, { tone: "lo", material: "gunmetal", crease: "lo", steps: 2 });

// bagian atas miring: profil (y, z) diekstrusi sepanjang x
T.prism({ name: "badan.atas", group: kiosk, layer: body, F: upright, polygon: [[-150, Z_CAB[1]], [150, Z_CAB[1]], [UP_FRONT_TOP_Y, Z_TOP], [UP_BACK_TOP_Y, Z_TOP]].map(([y, z]) => [m(y), m(z)]), s0: -m(HALF_W), s1: m(HALF_W), tone: "hi", crease: "faint", bevel: 0.9 });
const cap = slab("badan.tutup", [-285, -104, 570, 141, 12], Z_TOP, Z_TOP + CAP_H, { tone: "mid", material: "steel", bevel: 0.7 });

// layar: bezel oranye, kaca gelap, isi layar di bidang miring
const FACE_F = frame(w3(faceAt(0)), N, TUP);
const SCREEN_W = 476;
const SCREEN_H = 268;
const SCREEN_L = 349;
const bezelPoly = roundRect(m(SCREEN_L), 0, m(SCREEN_H / 2 + 20), m(SCREEN_W / 2 + 24), m(16)).map(([l, x]) => [l, x]);
const bezel = T.prism({ name: "layar.bezel", group: kiosk, layer: body, F: FACE_F, polygon: bezelPoly, s0: 0, s1: m(6), tone: "hi", crease: "lo", material: "gold", bevel: 0.4, details: { dots: [[-1, -1], [-1, 1], [1, -1], [1, 1]].map(([a, b]) => ({ at: [m(6), m(SCREEN_L + a * (SCREEN_H / 2 + 12)), m(b * (SCREEN_W / 2 + 14))], normal: N, size: 0.5, tone: "mid" })) } });
const GLASS_T = [m(6), m(7.6)];
const glassPoly = roundRect(m(SCREEN_L), 0, m(SCREEN_H / 2 + 5), m(SCREEN_W / 2 + 4), m(8));
const glass = T.prism({ name: "layar.kaca", group: kiosk, layer: body, F: FACE_F, polygon: glassPoly, s0: GLASS_T[0], s1: GLASS_T[1], tone: "mid", crease: "lo", material: "gunmetal" });

const asset = (name) => `data:image/png;base64,${readFileSync(join(HERE, "aset", name)).toString("base64")}`;
const logo = asset("logo-transjakarta.png");
const mascot = asset("maskot-bus.png");
const screenSvg = () => {
  const W = SCREEN_W;
  const H = SCREEN_H;
  const font = "Noto Sans, Segoe UI, Arial, sans-serif";
  const pill = (x, y, w, h, r, fill, stroke = "none") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
  const txt = (x, y, size, weight, fill, text, anchor = "start") => `<text x="${x}" y="${y}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${text}</text>`;
  return `<g transform="scale(${M})">
    <rect width="${W}" height="${H}" fill="#ffffff"/>
    ${txt(18, 20, 10.5, 400, "#52525b", "Anda di halte")}
    ${txt(18, 40, 17, 700, "#0f47a1", "Bundaran HI")}
    <image href="${logo}" x="${W / 2 - 46}" y="7" width="92" height="38" preserveAspectRatio="xMidYMid meet"/>
    ${txt(W - 18, 18, 10, 400, "#52525b", "Kamis, 29 Oktober 2026", "end")}
    ${txt(W - 18, 42, 24, 700, "#0f47a1", "08:30", "end")}
    <rect x="0" y="52" width="${W}" height="1.5" fill="#e4e4e7"/>
    ${txt(70, 94, 23, 700, "#09090b", "Cari Rute Bus")}
    ${txt(70, 120, 23, 700, "#09090b", "yang Nyaman")}
    ${txt(70, 142, 11.5, 400, "#52525b", "Pilih perjalanan yang nyaman,")}
    ${txt(70, 158, 11.5, 400, "#52525b", "TJ siap membantu Anda.")}
    <ellipse cx="350" cy="116" rx="86" ry="44" fill="#eef3fb"/>
    <image href="${mascot}" x="282" y="68" width="136" height="85" preserveAspectRatio="xMidYMid meet"/>
    ${pill(70, 176, W - 140, 38, 9, "#ffffff", "#d4d4d8")}
    ${pill(78, 182, 26, 26, 6, "#eef3fb")}
    <circle cx="91" cy="193" r="4.4" fill="none" stroke="#0f47a1" stroke-width="2"/><path d="M91 198 L91 203" stroke="#0f47a1" stroke-width="2"/>
    ${txt(114, 192, 9, 500, "#52525b", "Ke:")}
    ${txt(114, 206, 12.5, 500, "#52525b", "Sentuh untuk memilih tujuan…")}
    ${pill(70, 222, W - 140, 38, 9, "#0f47a1")}
    <circle cx="${W / 2 - 50}" cy="241" r="6" fill="none" stroke="#fff" stroke-width="2.2"/><path d="M${W / 2 - 46} 245 L${W / 2 - 41} 250" stroke="#fff" stroke-width="2.2"/>
    ${txt(W / 2 - 32, 247, 15, 700, "#ffffff", "Cari Rute")}
  </g>`;
};
const SCREEN_TOP = SCREEN_L + SCREEN_H / 2;
const screenO = G.add3(w3([-SCREEN_W / 2, 150 - SCREEN_TOP * SIN, Z_CAB[1] + SCREEN_TOP * COS]), G.mul3(N, GLASS_T[1] + 0.04));
T.plane({ part: glass, o: screenO, u: [1, 0, 0], v: G.mul3(TUP, -1), svg: screenSvg(), normal: N, fade: [0.02, 0.2] });
void bezel;

// aksen emas
const band = (name, plan, z0 = 60, z1 = 96) => slab(name, plan, z0, z1, { tone: "mid", material: "gold", crease: "lo", bevel: 0.2, steps: 2 });
band("aksen.pita.depan", [-HALF_W, 150, 2 * HALF_W, 3, 1]);
band("aksen.pita.kanan", [HALF_W, -150, 3, 300, 1]);
band("aksen.pita.kiri", [-HALF_W - 3, -150, 3, 300, 1]);

// kunci servis di sisi kiri
slab("servis.pelat.kunci", [-HALF_W - 3, -34, 3, 68, 1.5], 466, 534, { tone: "mid", material: "steel", bevel: 0.2, steps: 2 });
T.round({ name: "servis.kunci", group: kiosk, layer: body, F: frame(w3([-HALF_W - 3, 0, 500]), [-1, 0, 0], [0, 0, 1]), s0: 0, s1: m(5), r: m(11), tone: "hi", material: "brass", details: { seams: [m(2)], rules: [{ points: [[m(5), -m(0.1), -m(6)], [m(5), -m(0.1), m(6)]], tone: "lo", free: true }] } });

// pintu servis di belakang: engsel, gagang, kisi
const door = slab("belakang.pintu", [-150, -153, 300, 3, 1], 62, 788, { tone: "mid", crease: "lo", bevel: 0.3, steps: 2 });
for (const [i, [z0, z1]] of [[150, 230], [410, 490], [620, 700]].entries()) for (const sx of [-1, 1]) T.round({ name: `belakang.engsel.${i}.${sx}`, group: kiosk, layer: body, F: VERT(sx * 153, -153), s0: m(z0), s1: m(z1), r: m(3), tone: "mid", material: "steel", details: { seams: [m((z1 - z0) / 2)] } });
slab("belakang.gagang", [90, -163, 40, 10, 3], 380, 400, { tone: "hi", material: "chrome", bevel: 0.3, steps: 2 });
T.round({ name: "badan.selongsong", group: kiosk, layer: body, F: frame(w3([100, -170, 40]), [0, -1, 0], [0, 0, 1]), s0: 0, s1: m(14), r: m(10), tone: "mid", material: "brass", details: { seams: [m(8)] } });

// pelat nama di muka kabinet
const plate = slab("badan.pelat.nama", [-70, 150, 140, 3, 1.5], 380, 470, { tone: "lo", material: "gunmetal", crease: "lo", bevel: 0.25, steps: 2 });
const plateSvg = `<g transform="scale(${M})"><text x="70" y="48" font-family="Noto Sans, Segoe UI, Arial, sans-serif" font-size="25" font-weight="700" letter-spacing="2" fill="#ffffff" text-anchor="middle">SENIORA</text><rect x="50" y="62" width="40" height="3" rx="1.5" fill="#ee6a00"/></g>`;
T.plane({ part: plate, o: w3([-70, 150 + 3, 470]), u: [1, 0, 0], v: [0, 0, -1], svg: plateSvg, normal: [0, 1, 0], fade: [0.02, 0.2] });

// kisi udara di atas tutup
for (let i = 0; i < 5; i++) slab(`tutup.kisi.${i}`, [-130 + i * 65, -92, 14, 110, 2], Z_TOP + CAP_H, Z_TOP + CAP_H + 3.5, { tone: "lo", bevel: 0.15, steps: 2 });

// bidang cetak di muka kabinet, sisi kanan dan pintu belakang (satuan mm, titik asal kiri atas)
const engraved = (svg) => `<g transform="scale(${M})">${svg}</g>`;
const slots = (x, y, w, rows, h = 5, gap = 7) => Array.from({ length: rows }, (_, i) => `M${x} ${y + i * (h + gap)}h${w}v${h}h-${w}z`).join("");
const label = (x, y, size, text) => `<text class="iso-face-text" data-tone="lo" font-size="${size}" text-anchor="middle" x="${x}" y="${y}">${text}</text>`;
const ventPanel = `<path class="iso-line" data-tone="lo" d="${slots(60, 43, 180, 7, 5, 8)}"/><path class="iso-line" data-tone="faint" d="M40 30h220v110h-220z"/>`;
const nudge = (p, axis, d) => p.map((v, i) => (i === axis ? v + d : v));
T.plane({ part: colRight, o: nudge(w3([HALF_W, 150, 790]), 0, 0.04), u: [0, -1, 0], v: [0, 0, -1], normal: [1, 0, 0], svg: engraved(
  ventPanel + `<path class="iso-line" data-tone="faint" d="M40 190h220v440h-220z"/>` + label(150, 410, 20, "SENIORA")) });
T.plane({ part: colLeft, o: nudge(w3([-HALF_W, -150, 790]), 0, -0.04), u: [0, 1, 0], v: [0, 0, -1], normal: [-1, 0, 0], svg: engraved(ventPanel) });
T.plane({ part: door, o: w3([150, -153, 720]).map((v, i) => (i === 1 ? v - 0.04 : v)), u: [-1, 0, 0], v: [0, 0, -1], normal: [0, -1, 0], svg: engraved(
  `<path class="iso-line" data-tone="lo" d="${slots(60, 460, 180, 8, 6, 7)}"/><path class="iso-line" data-tone="faint" d="M24 24h252v540h-252z"/>`) });

// slot receipt: bingkai terang rata dengan muka panel, celah gelap, lidah kecil dan pelat label
const frameBar = (name, x0, x1, z0, z1) => slab(name, [x0, 150, x1 - x0, 3, 1], z0, z1, { tone: "mid", material: "steel", crease: "lo", bevel: 0.3, steps: 2 });
frameBar("slot.bingkai.atas", SLOT.x0 - 10, SLOT.x1 + 10, SLOT.z1, SLOT.z1 + 10);
frameBar("slot.bingkai.bawah", SLOT.x0 - 10, SLOT.x1 + 10, SLOT.z0 - 10, SLOT.z0);
frameBar("slot.bingkai.kiri", SLOT.x0 - 10, SLOT.x0, SLOT.z0, SLOT.z1);
frameBar("slot.bingkai.kanan", SLOT.x1, SLOT.x1 + 10, SLOT.z0, SLOT.z1);
slab("slot.lidah", [-35, 150, 70, 6, 2], SLOT.z0 - 18, SLOT.z0 - 10, { tone: "lo", material: "gunmetal", crease: "lo", bevel: 0.3, steps: 2 });
slab("slot.alas", [SLOT.x0, SLOT.back, SLOT.x1 - SLOT.x0, 150 - SLOT.back, 0.5], SLOT.z0, SLOT.z0 + 1, { tone: "lo", material: "gunmetal", crease: "lo", steps: 2 });
const slotLabel = slab("slot.label", [-78, 150, 156, 3, 1.5], 724, 748, { tone: "lo", material: "gunmetal", crease: "lo", bevel: 0.25, steps: 2 });
const slotLabelSvg = `<g transform="scale(${M})"><rect x="12" y="5" width="12" height="14" rx="1.5" fill="none" stroke="#e4e4e7" stroke-width="1.6"/><path d="M15 10h6M15 14h6" stroke="#e4e4e7" stroke-width="1.4"/><text x="90" y="17" font-family="Noto Sans, Segoe UI, Arial, sans-serif" font-size="12" font-weight="700" letter-spacing="1.5" fill="#e4e4e7" text-anchor="middle">TIKET</text></g>`;
T.plane({ part: slotLabel, o: w3([-78, 153.04, 748]), u: [1, 0, 0], v: [0, 0, -1], svg: slotLabelSvg, normal: [0, 1, 0], fade: [0.02, 0.2] });

// tiket: kertas di atas alas kantong, meluncur keluar dari celah
const TICKET = { x: -50, y: 12, w: 100, d: 130, z0: 691, z1: 692.4 };
const paper = T.prism({ name: "tiket.kertas", group: tiket, layer: body, plan: rect(TICKET.x, TICKET.y, TICKET.w, TICKET.d, 2), z: m(TICKET.z0), h: m(TICKET.z1 - TICKET.z0), steps: 2, tone: "hi", crease: "faint", bevel: 0.15 });
const ticketSvg = () => {
  const W = 100;
  const t = (x, y, size, weight, fill, text, anchor = "start") => `<text x="${x}" y="${y}" font-family="Noto Sans, Segoe UI, Arial, sans-serif" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${text}</text>`;
  const row = (y, a, b) => t(6, y, 4.6, 400, "#52525b", a) + t(W - 6, y, 4.6, 700, "#09090b", b, "end");
  return `<g transform="scale(${M})">
    <rect width="${W}" height="${TICKET.d}" fill="#ffffff"/>
    <rect width="${W}" height="14" fill="#0f47a1"/>
    ${t(W / 2, 8.6, 6.4, 700, "#ffffff", "TransJakarta Lega", "middle")}
    ${t(W / 2, 21, 4.4, 400, "#52525b", "Tiket Rencana Perjalanan", "middle")}
    <path d="M6 25 H94" stroke="#d4d4d8" stroke-width="0.6" stroke-dasharray="2 1.6"/>
    ${row(33, "Dari", "Bundaran HI")}${row(41, "Ke", "Blok M")}${row(49, "Berangkat", "08:30")}${row(57, "Estimasi", "24 menit")}${row(65, "Transit", "Langsung")}
    <path d="M6 71 H94" stroke="#d4d4d8" stroke-width="0.6" stroke-dasharray="2 1.6"/>
    <rect x="6" y="77" width="3" height="20" rx="1.2" fill="#ee6a00"/>
    ${t(13, 82, 5, 700, "#09090b", "Koridor 1 · Bus TJ")}${t(13, 90, 4.4, 400, "#52525b", "Naik di Bundaran HI")}${t(13, 97, 4.4, 400, "#52525b", "Turun di Blok M")}
    <path d="M6 106 H94" stroke="#d4d4d8" stroke-width="0.6" stroke-dasharray="2 1.6"/>
    ${t(W / 2, 116, 3.8, 400, "#52525b", "Jam bersifat perkiraan. Selamat jalan!", "middle")}
    <rect x="${W - 14}" y="${TICKET.d - 4}" width="8" height="2" fill="#ee6a00"/>
  </g>`;
};
T.plane({ part: paper, o: w3([TICKET.x, TICKET.y, TICKET.z1 + 0.05]), u: [1, 0, 0], v: [0, 1, 0], svg: ticketSvg(), normal: [0, 0, 1], fade: [0.02, 0.2] });

floor();
const verify = argv.includes("--verify");
const out = T.build({ statics: R.items, poses, verify });
A.settle(R, P);
const layerOf = (name) => R.items.filter((item) => item.layer === name).sort((a, b) => a.key - b.key).map((item) => item.svg);
const BACK = [`<path class="iso-halo" d="${k.haloOf(rect(...BASE), -m(BASE_H) - m(18), m(BASE_H), P)}"/>`, ...layerOf("back")];
if (argv.includes("--audit")) {
  A.auditOrExit(R, P);
  TA.orbitOrExit(T, R, P, {
    sweep: { at: (x) => follow({ kiosk: x }), from: 0, to: 360, frame: 0.3 },
    clips: [{ name: "cetak", at: (t) => follow({ kiosk: 20 + 8 * t, tiket: printAt(t) * m(TICKET_TRAVEL) }), from: 0, to: 7, frame: 1 / 60 }],
    quick: argv.includes("--quick"),
    only: argv.find((a) => a.startsWith("--only="))?.slice(7).split(",") ?? null,
    log: argv.includes("--verbose") ? (text) => console.log(`  … ${text}`) : null,
  });
}

const LABEL = "Kiosk TransJakarta Lega berdiri di atas piringan putar: badan putih dengan layar sentuh miring berbingkai oranye dan slot receipt tempat tiket tercetak meluncur keluar.";
const backSvg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: LABEL, body: BACK });
const stage = `<div class="iso-stage iso-turn ks-stage" tabindex="0" role="slider" aria-label="Kiosk: seret untuk memutar, panah kiri kanan juga memutar, tombol P mencetak tiket" aria-valuemin="0" aria-valuemax="359" aria-valuenow="0" aria-valuetext="kiosk menghadap depan">${backSvg}${out.layerSvg("kiosk", { width: WIDTH, height: HEIGHT })}</div>`;
const DATA = { turn: out.data, travel: m(TICKET_TRAVEL), travelMm: TICKET_TRAVEL };
const FOLLOW = `const follow = ${follow.toString()};\nconst printAt = ${printAt.toString()};`;
const CSS = out.css + "\n" + readFileSync(join(HERE, "kiosk.css"), "utf8");
const LIVE = readFileSync(join(HERE, "live.js"), "utf8").replace("__DATA__", JSON.stringify(DATA)).replace("const follow = null;", FOLLOW);
const content = k.plateHtml({
  fig: "Gbr 3D",
  title: "Kiosk TransJakarta Lega",
  hint: "Seret untuk memutar · P cetak tiket",
  readout: "kiosk 0° · tiket 0%",
  keys: [
    { mark: "raised", label: "Badan kiosk dan piringan: satu grup putar" },
    { mark: "lit", label: "Tiket yang meluncur keluar" },
  ],
  caption: "Layar menampilkan beranda aplikasi kiosk. Setelah rencana dipilih, tiket tercetak keluar dari slot di muka kabinet, lalu diambil penumpang.",
  body: `<style>${CSS}</style>${stage}`,
});
const page = k.pageHtml({ title: "Kiosk TransJakarta Lega", theme, body: content, script: turnScript() + (verify ? `window.__isoVerify = ${JSON.stringify(out.verify)};\n` : "") + LIVE, width: 640 });
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const name = `kiosk${verify ? "-verify" : ""}${theme === "dark" ? "-gelap" : ""}.html`;
  writeFileSync(join(HERE, name), page);
  console.log(`wrote ${name} · ${(page.length / 1024).toFixed(0)} KB · ${out.report.parts} parts · ${out.report.layers.map((l) => `${l.name}: ${l.planar} planes, ${l.dynamic} dynamic`).join(" · ")} · build ${out.report.seconds.toFixed(1)} s`);
}
export { out };
