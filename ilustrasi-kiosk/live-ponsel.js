const DATA = __DATA__;
const stage = document.querySelector(".ks-stage");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const SWING = 38;
let angle = 0;
let target = 0;
let frame = 0;
let last = 0;
let visible = false;
let touring = !still.matches;
let idle = 0;
let clock = 0;
let drawn = null;
let own = false;
const wrap = (deg) => ((deg % 360) + 360) % 360;
const describe = () => {
  const deg = Math.round(wrap(target));
  stage.setAttribute("aria-valuenow", String(deg));
  stage.setAttribute("aria-valuetext", deg < 20 || deg > 340 ? "ponsel menghadap depan" : `ponsel diputar ${deg} derajat`);
};
const show = () => {
  const text = `ponsel ${Math.round(wrap(angle))}°`;
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
  follow: null,
  onHold: () => {
    touring = false;
    clearTimeout(idle);
  },
  onFrame: (turned) => {
    if (!own) {
      angle = target = turned.values.ponsel ?? angle;
      describe();
    }
    show();
  },
});
const draw = () => {
  own = true;
  controller.set({ ponsel: angle });
  own = false;
  drawn = angle;
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
  if (drawn === null || Math.abs(angle - drawn) > 1e-4) draw();
  const settled = !touring && angle === target;
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
  drag = null;
  stage.removeAttribute("data-drag");
  try {
    stage.releasePointerCapture(event.pointerId);
  } catch {}
};
stage.addEventListener("pointerup", release);
stage.addEventListener("pointercancel", release);
stage.addEventListener("keydown", (event) => {
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
