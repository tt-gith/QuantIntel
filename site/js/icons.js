// Satır içi SVG ikonlar (16px ızgara, currentColor).
const svg = (body, vb = "0 0 16 16") =>
  `<svg class="ico" viewBox="${vb}" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const ICONS = {
  up: svg(`<path d="M8 13V3.5M3.8 7.5 8 3.2l4.2 4.3"/>`),
  comment: svg(`<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>`),
  cite: svg(`<path d="M3 11.5V8a3 3 0 0 1 3-3M9.5 11.5V8a3 3 0 0 1 3-3"/><path d="M3 11.5h3v-3H3zM9.5 11.5h3v-3h-3z" fill="currentColor" stroke="none"/>`),
  eye: svg(`<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="1.8"/>`),
  multi: svg(`<circle cx="6" cy="8" r="3.6"/><circle cx="10" cy="8" r="3.6"/>`),
  hot: svg(`<path d="M8 14c2.6 0 4.3-1.8 4.3-4.2 0-2-1.2-3.2-2-4.6-.5 1-1 1.5-1.8 1.8C8.8 5 8.3 3.300 6.800 2c.1 1.8-.8 2.900-1.700 4C4.400 6.800 3.700 7.900 3.700 9.600 3.700 12.200 5.400 14 8 14z"/>`),
  heart: svg(`<path d="M8 13.300S2.500 10 2.500 6.300A2.800 2.800 0 0 1 8 5.200a2.800 2.800 0 0 1 5.500 1.100C13.500 10 8 13.300 8 13.300z"/>`),
  search: svg(`<circle cx="7" cy="7" r="4.200"/><path d="m10.200 10.200 3.300 3.300"/>`),
  calendar: svg(`<rect x="2.500" y="3.500" width="11" height="10" rx="1.500"/><path d="M2.500 6.500h11M5.500 2v3M10.500 2v3"/>`),
  close: svg(`<path d="m4 4 8 8M12 4l-8 8"/>`),
  filter: svg(`<path d="M2.500 4h11M4.500 8h7M6.500 12h3"/>`),
  lock: svg(`<rect x="3.5" y="7.5" width="9" height="6" rx="1.2"/><path d="M5.5 7.5V5.5a2.5 2.5 0 0 1 5 0v2"/>`),
  tool: svg(`<path d="M9.500 2.500a3.200 3.200 0 0 0-3 4.300L2.500 10.800v2.700h2.700l4-4a3.200 3.200 0 0 0 4.300-3l-2 .700-1.700-1.700z"/>`),
};

export const icon = (name) => ICONS[name] ?? "";
