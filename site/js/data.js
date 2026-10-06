// Veri katmanı: manifest, aylık içerik dosyaları ve özetler. Site yalnızca bu dosyaları okur.
//
// İki kip vardır:
//  - Düz (yerel kullanım): data/manifest.json ve items-*.json doğrudan okunur.
//  - Kilitli (yayındaki site): data/lock.json bulunur; dosyalar şifrelidir (.bin) ve
//    parola girilince tarayıcıda çözülür. Yöntem qin/vault.py ile aynıdır:
//    PBKDF2-SHA256 → AES-256-GCM → deflate.
//
// Kilitli sitede ikinci bir parola olabilir (yönetim). O parola data/admin.bin dosyasını açar;
// içinden site anahtarı ve yönetim panelinin gereksindikleri çıkar (bkz. qin/admin.py).
const BASE = "data/";
const KEY_STORE = "qin.key";
const ADMIN_STORE = "qin.admin";
const cache = new Map();
let manifest = null;
let lock = null;      // lock.json içeriği ya da null (düz kip)
let key = null;       // site anahtarı (CryptoKey, kilitli kipte)
let admin = null;     // { key: CryptoKey, info } — yalnızca yönetim parolasıyla girildiyse

const fromB64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
function toB64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

async function getRaw(name) {
  const res = await fetch(BASE + name, { cache: "no-store" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res;
}

// Şifreli dosya düzeni: nonce (12 bayt) + AES-GCM(deflate(JSON)).
async function open(buf, withKey) {
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: buf.slice(0, 12) }, withKey, buf.slice(12));
  const text = await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream("deflate"))).text();
  return JSON.parse(text);
}

async function read(name) {
  const res = await getRaw(name);
  return lock ? open(await res.arrayBuffer(), key) : res.json();
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

// Yönetim anahtarını dener: admin.bin açılırsa içindeki site anahtarıyla siteyi de açar.
async function useAdminBits(bits) {
  if (!lock?.admin) return false;
  const adminKey = await crypto.subtle.importKey("raw", bits, "AES-GCM", false, ["encrypt", "decrypt"]);
  let info;
  try {
    info = await open(await (await getRaw("admin.bin")).arrayBuffer(), adminKey);
  } catch (err) {
    if (err.name === "OperationError") return false;
    throw err;
  }
  if (!(await useKeyBits(fromB64(info.key)))) return false;
  delete info.key;
  admin = { key: adminKey, info };
  return true;
}

function remember(store, bits, persist) {
  try {
    for (const k of [KEY_STORE, ADMIN_STORE]) { localStorage.removeItem(k); sessionStorage.removeItem(k); }
    (persist ? localStorage : sessionStorage).setItem(store, toB64(bits));
  } catch { /* depolama kapalıysa her açılışta parola sorulur */ }
}

// Parolayı dener (site parolası ya da yönetim parolası). Doğruysa true döner;
// "remember" seçiliyse anahtar bu cihazda saklanır.
export async function unlock(password, persist) {
  const pw = new TextEncoder().encode(password.trim().normalize("NFC"));
  const base = await crypto.subtle.importKey("raw", pw, "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: fromB64(lock.salt), iterations: lock.iter }, base, 256);
  if (await useKeyBits(bits)) { remember(KEY_STORE, bits, persist); return true; }
  if (await useAdminBits(bits)) { remember(ADMIN_STORE, bits, persist); return true; }
  return false;
}

// Daha önce girilmiş parolanın anahtarı saklıysa onunla açmayı dener.
export async function unlockFromStore() {
  const saved = (name) => {
    try { return sessionStorage.getItem(name) || localStorage.getItem(name); } catch { return null; }
  };
  try {
    const adminBits = saved(ADMIN_STORE);
    if (adminBits && await useAdminBits(fromB64(adminBits))) return true;
    const bits = saved(KEY_STORE);
    return !!bits && await useKeyBits(fromB64(bits));
  } catch { return false; }
}

export function forgetKey() {
  try {
    for (const k of [KEY_STORE, ADMIN_STORE]) { localStorage.removeItem(k); sessionStorage.removeItem(k); }
  } catch { /* yoksay */ }
}

// Yönetim bilgisi (GitHub bağlantısı, aboneler, son işlem) ya da null.
export const adminInfo = () => admin?.info ?? null;

// admin.bin dosyasını yeniden okur (bir komutun sonucu yayınlandı mı diye bakmak için).
export async function refreshAdminInfo() {
  if (!admin) return null;
  const info = await open(await (await getRaw("admin.bin")).arrayBuffer(), admin.key);
  delete info.key;
  admin.info = info;
  return info;
}

// Yönetim komutunu, iş akışının çözebileceği biçimde şifreler: base64(nonce + AES-GCM(deflate(JSON))).
export async function sealCommand(command) {
  const packed = await new Response(
    new Blob([JSON.stringify(command)]).stream().pipeThrough(new CompressionStream("deflate"))).arrayBuffer();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, admin.key, packed));
  const out = new Uint8Array(12 + sealed.length);
  out.set(iv);
  out.set(sealed, 12);
  return toB64(out);
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

// Günlük ve haftalık özetler (en yeni önce). Dosya ilk istendiğinde yüklenir.
export function loadBriefs() {
  const file = manifest?.briefs?.file;
  if (!file || !manifest.briefs.n) return Promise.resolve([]);
  if (!cache.has(file)) {
    cache.set(file, read(file).then((j) => {
      for (const b of j.briefs) b.date = new Date(b.c);
      return j.briefs;
    }).catch((err) => { cache.delete(file); throw err; }));
  }
  return cache.get(file);
}

const monthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
