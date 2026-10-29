const DATA = __DATA__;
const follow = null;
const stage = document.querySelector(".ks-stage");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const SWING = 38;
let angle = 0;
let target = 0;
let shown = null;
let frame = 0;
let last = 0;
let visible = false;
let touring = !still.matches;
let idle = 0;
let clock = 0;
let ticket = 0;
let manual = null;
let drawn = null;
let own = false;
const wrap = (deg) => ((deg % 360) + 360) % 360;
const describe = () => {
  const deg = Math.round(wrap(target));
  stage.setAttribute("aria-valuenow", String(deg));
  stage.setAttribute("aria-valuetext", deg < 20 || deg > 340 ? "kiosk menghadap depan" : `kiosk diputar ${deg} derajat`);
};
const show = () => {
  const text = `kiosk ${Math.round(wrap(angle))}° · tiket ${Math.round(ticket * 100)}%`;
  if (readout.textContent !== text) readout.textContent = text;
};
const hold = () => {
  touring = false;
  clearTimeout(idle);
  idle = setTimeout(() => {
    touring = !still.matches;
    run();
  }, 4200);
};
const controller = TURN.mount(stage, DATA.turn, {
  follow,
  onHold: () => {
    touring = false;
    clearTimeout(idle);
  },
  onFrame: (turned) => {
    if (!own) {
      angle = target = turned.values.kiosk ?? angle;
      ticket = (turned.values.tiket ?? 0) / DATA.travel;
      describe();
    }
    show();
  },
});
const draw = () => {
  own = true;
  controller.set({ kiosk: angle, tiket: ticket * DATA.travel });
  own = false;
  drawn = [angle, ticket];
};
// Satu putaran cetak: tiket keluar, ditahan, lalu diambil.
const ease = (x) => x * x * (3 - 2 * x);
const printing = () => {
  if (manual === null) return null;
  const t = manual;
  return ease(Math.min(1, t / 1.5)) * (1 - ease(Math.min(1, Math.max(0, (t - 4) / 1.1))));
};
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  const calm = still.matches;
  if (calm) {
    touring = false;
    clearTimeout(idle);
  }
  if (touring) {
    clock += dt;
    target = SWING * Math.sin(clock * 0.45);
  }
  angle = calm ? target : angle + (target - angle) * (1 - Math.exp(-dt / 0.12));
  if (Math.abs(target - angle) < 1e-3) angle = target;
  let want = ticket;
  if (manual !== null) {
    manual += dt;
    want = printing();
    if (manual >= 5.1) manual = null;
  } else if (touring && !calm) want = printAt(clock);
  const next = calm ? ticket : manual !== null ? want : touring ? ticket + (want - ticket) * (1 - Math.exp(-dt / 0.06)) : ticket;
  const moved = Math.abs(next - ticket) > 1e-5;
  ticket = next;
  if (moved || drawn === null || Math.abs(angle - drawn[0]) > 1e-4) draw();
  const settled = !touring && manual === null && angle === target;
  frame = visible && !settled ? requestAnimationFrame(tick) : 0;
}
const run = () => {
  if (!frame && visible) {
    last = 0;
    frame = requestAnimationFrame(tick);
  }
};
new IntersectionObserver(
  (entries) => {
    visible = entries[entries.length - 1].isIntersecting;
    if (visible) run();
    else if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }
  },
  { rootMargin: "120px 0px" },
).observe(stage);
const printNow = () => {
  hold();
  if (still.matches) {
    // Gerak dikurangi: tiket muncul atau hilang sebagai gambar diam.
    ticket = ticket > 0.5 ? 0 : 1;
    draw();
    show();
    return;
  }
  manual = manual === null ? 0 : manual;
  run();
};
let drag = null;
stage.addEventListener("pointerdown", (event) => {
  hold();
  drag = { x: event.clientX, base: target, id: event.pointerId, captured: false };
});
stage.addEventListener("pointermove", (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  hold();
  const delta = event.clientX - drag.x;
  if (!drag.captured && Math.abs(delta) > 4) {
    drag.captured = true;
    stage.setPointerCapture(event.pointerId);
    stage.setAttribute("data-drag", "");
  }
  if (!drag.captured) return;
  target = drag.base - delta * 0.6;
  describe();
  run();
});
const release = (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  const tap = !drag.captured;
  drag = null;
  stage.removeAttribute("data-drag");
  try {
    stage.releasePointerCapture(event.pointerId);
  } catch {}
  if (tap && event.type === "pointerup") printNow();
};
stage.addEventListener("pointerup", release);
stage.addEventListener("pointercancel", release);
stage.addEventListener("keydown", (event) => {
  if (event.key === "p" || event.key === "P" || event.key === "Enter") {
    event.preventDefault();
    printNow();
    return;
  }
  const step = event.shiftKey ? 30 : 6;
  let next = null;
  if (event.key === "ArrowRight" || event.key === "ArrowUp") next = target - step;
  if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = target + step;
  if (event.key === "Home") next = 360 * Math.round(target / 360);
  if (next === null) return;
  event.preventDefault();
  hold();
  target = next;
  describe();
  run();
});
if (still.matches) touring = false;
draw();
describe();
