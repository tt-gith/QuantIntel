// Arka plandaki yıldız alanı. Yıldızlar aşağı doğru akar (yükseliyoruz); açılışta ve
// hızlı kaydırmada hız artar, yıldızlar çizgiye dönüşür. Hareket azaltma tercihine uyar.
export function initStarfield(canvas) {
  const ctx = canvas.getContext("2d");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let w = 0, h = 0, dpr = 1, stars = [], warp = 1, last = 0, raf = 0, lastScroll = scrollY;

  function resize() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(420, (w * h) / 4200));
    stars = Array.from({ length: n }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      z: 0.15 + Math.random() ** 2 * 0.85,            // derinlik: çoğu uzak ve sönük
      warm: Math.random() < 0.12,
    }));
    if (still) draw(0);
  }

  function draw(dt) {
    ctx.clearRect(0, 0, w, h);
    const speed = 0.006 * warp;                        // px/ms, derinlikle çarpılır
    for (const s of stars) {
      const dy = s.z * speed * dt * 4;
      s.y += dy;
      if (s.y > h + 4) { s.y = -4; s.x = Math.random() * w; }
      const a = 0.25 + s.z * 0.75;
      ctx.strokeStyle = ctx.fillStyle = s.warm ? `rgba(255,214,160,${a})` : `rgba(205,222,255,${a})`;
      const len = Math.min(140, dy * 6 * warp ** 0.35);
      if (len > 2.2) {
        ctx.lineWidth = 0.6 + s.z;
        ctx.beginPath(); ctx.moveTo(s.x, s.y - len); ctx.lineTo(s.x, s.y); ctx.stroke();
      } else {
        const r = 0.35 + s.z * 0.95;
        ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, 6.2832); ctx.fill();
      }
    }
  }

  function frame(now) {
    const dt = Math.min(48, now - (last || now));
    last = now;
    warp += (1 - warp) * Math.min(1, dt / 420);        // hız yavaşça seyir hızına döner
    draw(dt);
    raf = requestAnimationFrame(frame);
  }

  addEventListener("resize", resize);
  resize();
  if (still) return { launch() {} };

  addEventListener("scroll", () => {
    const d = Math.abs(scrollY - lastScroll); lastScroll = scrollY;
    warp = Math.min(26, warp + d * 0.05);
  }, { passive: true });
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf); last = 0;
    if (!document.hidden) raf = requestAnimationFrame(frame);
  });
  raf = requestAnimationFrame(frame);
  return { launch() { warp = 70; } };
}
