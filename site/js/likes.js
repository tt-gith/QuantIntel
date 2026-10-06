// Beğeni katmanı. Şimdilik yalnızca bu tarayıcıda tutulur (localStorage).
// Bulut aşamasında aynı üç fonksiyon sunucuya bağlanacak; arayüz değişmeyecek.
const KEY = "qin.likes";
let mine = new Set();
try { mine = new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { /* yoksay */ }

export const isLiked = (id) => mine.has(id);

// Sunucu sayımı geldiğinde burası toplam beğeniyi döndürecek.
export const likeCount = (item) => (item.m?.likes ?? 0) + (mine.has(item.id) ? 1 : 0);

export function toggleLike(id) {
  mine.has(id) ? mine.delete(id) : mine.add(id);
  try { localStorage.setItem(KEY, JSON.stringify([...mine])); } catch { /* yoksay */ }
  return mine.has(id);
}
