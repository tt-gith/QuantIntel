// Veri katmanı: manifest ve aylık içerik dosyaları. Site yalnızca bu dosyaları okur.
//
// İki kip vardır:
//  - Düz (yerel kullanım): data/manifest.json ve items-*.json doğrudan okunur.
//  - Kilitli (yayındaki site): data/lock.json bulunur; dosyalar şifrelidir (.bin) ve
//    parola girilince tarayıcıda çözülür. Yöntem qin/vault.py ile aynıdır:
//    PBKDF2-SHA256 → AES-256-GCM → deflate.
const BASE = "data/";
const KEY_STORE = "qin.key";
const cache = new Map();
let manifest = null;
let lock = null;      // lock.json içeriği ya da null (düz kip)
let key = null;       // CryptoKey (kilitli kipte)

const fromB64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const toB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));

async function getRaw(name) {
  const res = await fetch(BASE + name, { cache: "no-store" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res;
}

async function read(name) {
  const res = await getRaw(name);
  if (!lock) return res.json();
  const buf = await res.arrayBuffer();
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: buf.slice(0, 12) }, key, buf.slice(12));
  const text = await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream("deflate"))).text();
  return JSON.parse(text);
}

// Sitenin kilitli olup olmadığını öğrenir.
export async function detectLock() {
  try { lock = await (await getRaw("lock.json")).json(); } catch { lock = null; }
  return !!lock;
}

export const isLocked = () => !!lock;

async function useKeyBits(bits) {
  key = await crypto.subtle.importKey("raw", bits, "AES-GCM", false, ["decrypt"]);
  try {
    manifest = await read(`manifest.bin`);
    return true;
  } catch (err) {
    key = null;
    if (err.name === "OperationError") return false;       // yanlış anahtar
    throw err;                                               // dosya yok, ağ sorunu vb.
  }
}

// Parolayı dener. Doğruysa true döner; "remember" seçiliyse anahtar bu cihazda saklanır.
export async function unlock(password, remember) {
  const pw = new TextEncoder().encode(password.trim().normalize("NFC"));
  const base = await crypto.subtle.importKey("raw", pw, "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: fromB64(lock.salt), iterations: lock.iter }, base, 256);
  if (!(await useKeyBits(bits))) return false;
  try {
    localStorage.removeItem(KEY_STORE); sessionStorage.removeItem(KEY_STORE);
    (remember ? localStorage : sessionStorage).setItem(KEY_STORE, toB64(bits));
  } catch { /* depolama kapalıysa her açılışta parola sorulur */ }
  return true;
}

// Daha önce girilmiş parolanın anahtarı saklıysa onunla açmayı dener.
export async function unlockFromStore() {
  let saved = null;
  try { saved = sessionStorage.getItem(KEY_STORE) || localStorage.getItem(KEY_STORE); } catch { /* yoksay */ }
  if (!saved) return false;
  try { return await useKeyBits(fromB64(saved)); } catch { return false; }
}

export function forgetKey() {
  try { localStorage.removeItem(KEY_STORE); sessionStorage.removeItem(KEY_STORE); } catch { /* yoksay */ }
}

export async function loadManifest() {
  if (!lock) manifest = await read("manifest.json");
  return manifest;                                           // kilitli kipte unlock sırasında yüklendi
}

// from/to: Date ya da null (sınırsız). Aralığa giren ayların dosyalarını yükler.
export async function loadRange(from, to) {
  const lo = from ? monthKey(from) : "0000-00";
  const hi = to ? monthKey(to) : "9999-99";
  const wanted = manifest.months.filter((m) => m.m >= lo && m.m <= hi);
  const chunks = await Promise.all(wanted.map((m) => {
    if (!cache.has(m.file)) {
      cache.set(m.file, read(m.file).then((j) => {
        for (const it of j.items) it.date = new Date(it.d);   // bir kez ayrıştır
        return j.items;
      }));
    }
    return cache.get(m.file);
  }));
  const lower = from ? from.getTime() : -Infinity;
  const upper = to ? to.getTime() : Infinity;
  return chunks.flat().filter((it) => it.date >= lower && it.date <= upper);
}

const monthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
