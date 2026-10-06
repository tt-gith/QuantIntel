// Fareyi izleyen küçük bilgi kutusu (grafik sütunları ve yörünge haritası için).
const el = () => document.getElementById("tip");

export function showTip(html, x, y) {
  const tip = el();
  tip.innerHTML = html;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = `${Math.max(8, Math.min(innerWidth - r.width - 8, x - r.width / 2))}px`;
  tip.style.top = `${Math.max(8, y - r.height - 14)}px`;
}

export const hideTip = () => { el().hidden = true; };
