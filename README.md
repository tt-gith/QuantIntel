# Quant Intelligence Network

Quant kaynaklarını (QuantSeeker, Quantocracy, Systematic Traders, OpenQuant, Quantpedia,
r/algotrading, arXiv q-fin) her gün çeker, tek tek içeriklere ayırır, yerel bir SQLite arşivine
kaydeder ve bunları bir web sitesi olarak sunar. Yol haritası: `ROADMAP.md`. Siteyi internette yayınlamak
(bilgisayar kapalıyken de çalışsın, her yerden erişilsin): `YAYIN.md`.

## Önceki sürümden yükseltme

1. Zip'i mevcut klasörün **üstüne** çıkar (dosyaların üzerine yazılsın). `data\` klasörün, yani arşivin
   olduğu gibi kalır. `config.json` yenilenir; elle değiştirdiğin bir ayar varsa yeniden gir.
2. Klasörde bir komut penceresi aç ve `qin fetch` çalıştır. İlk çalıştırmada arşiv yeni sürüme taşınır
   (bültenler kayıtlı ham veriden yeniden ayrıştırılır; öğe numaraları ve işaretlerin korunur),
   popülerlik verileri çekilir ve site verisi üretilir.
3. `site_ac.bat` ile siteyi aç.

Yeni Python paketi gerekmiyor. Zamanlanmış görevler aynen çalışmaya devam eder; günlük çekme artık
site verisini de günceller.

## İlk kurulum (Windows 10)

1. **Python 3.10+** kurulu değilse <https://www.python.org/downloads/> → kurulumda
   **"Add python.exe to PATH"** kutusunu işaretle.
2. Klasörü kalıcı bir yere çıkar. Sonradan taşırsan `gorev_kur.bat`'ı yeniden çalıştır.
3. **`kurulum.bat`**: sanal ortamı kurar, paketleri yükler, ilk çekmeyi yapar.
4. **`gorev_kur.bat`**: Görev Zamanlayıcı'ya iki görev ekler: her gün 09:05 çekme, her pazartesi 08:45
   çekme ve eski tip haftalık özet. Bilgisayar o saatte kapalıysa açıldığında çalışır.

## Site

**`site_ac.bat`** siteyi bu bilgisayarda açar (<http://localhost:8765>). Pencere açık kaldığı sürece çalışır.

- **Tek akış:** tüm kaynakların içerikleri tek listede; her öğede hangi kaynak(lar)dan geldiği yazar.
  Aynı içerik birden fazla kaynakta geçtiyse listede bir kez görünür.
- **Sol menü:** kaynak seçimi (yörünge haritasındaki noktalara ya da listeye tıkla) ve konu filtresi.
  Kaynağın yanındaki ışık son çekmenin durumunu gösterir; 21 günden uzun sessiz kalan kaynak sarı yanar.
- **Sekmeler:** Akış, Makaleler, Yazılar, Video ve podcast, Araçlar, Etkinlikler, Haberler, Tartışmalar,
  İlanlar. İlanlar yalnızca kendi sekmesinde görünür.
- **Öne çıkanlar (üstte):** seçili aralığın en güçlü içerikleri. Akış sekmesinde her türün
  (araç, makale, yazı, tartışma, video...) en iyisi seçilir; diğer sekmelerde o türün ilk beşi.
  Güç sırası: popülerlik puanı, "çok tıklanan" işareti, özeti olması, yenilik.
- **Tarih aralığı (sağ üst):** 7 gün (varsayılan), 30 gün, 90 gün, Tümü ya da özel aralık.
- **Sıralama:** en yeni ya da en popüler. Popülerlik rozetleri: oy ve yorum (Reddit), atıf (makaleler),
  kaç kaynakta geçtiği, "çok tıklanan" işareti ve 0–100 popülerlik çubuğu.
- **Dil:** arayüz TR/EN. İçerik çevirileri sonraki aşamada eklenecek; altyapısı hazır.
- **Paylaşılabilir görünüm:** seçtiğin sekme, kaynak, tarih ve arama adres çubuğuna yazılır.
- **Beğeni:** şimdilik yalnızca o tarayıcıda tutulur; ortak beğeniler bulut aşamasında gelecek.

## Komutlar

Klasörde bir komut penceresi (`cmd`) açıp `qin` ile çalıştırılır:

```bat
qin fetch                               :: çek + popülerlik verisi + site verisini güncelle
qin fetch --only quantseeker arxiv      :: yalnızca bazı kaynaklar
qin serve                               :: siteyi aç (site_ac.bat ile aynı)
qin export                              :: site verisini arşivden yeniden üret
qin reparse                             :: bültenleri kayıtlı ham veriden yeniden ayrıştır
qin search "LLM AND execution"          :: arşivde tam metin arama
qin mark 123 ilginç --note "dene"       :: öğeyi işaretle (sitede rozet olarak görünür)
qin radar                               :: işaretlediklerini listele
qin stats                               :: arşiv boyutu ve kaynak durumu
qin weekly                              :: çek + eski tip haftalık özet (digests\latest.html)
```

## Proje yapısı

```
config.json          kaynaklar, arXiv anahtar kelimeleri, ayarlar
qin\                 veri katmanı (Python)
  parsers.py           her kaynak türü için ayrıştırıcı
  fetch.py             indirme, kaydetme, yeniden ayrıştırma
  enrich.py            tür, konu etiketi ve araç sinyali kuralları
  metrics.py           dış popülerlik ölçümleri (atıf sayısı)
  cluster.py           aynı içeriğin kopyalarını birleştirme
  export.py            arşiv → site\data\*.json
  storage.py           SQLite şeması
site\                web sitesi (derleme adımı yok; dosyayı değiştir, sayfayı yenile)
  index.html
  css\tokens.css       renkler, yazı tipleri, ölçüler (görünümün tek adresi)
  css\app.css          yerleşim ve bileşenler
  js\config.js         sekmeler, tarih seçenekleri, popülerlik ölçümleri, vitrin grupları
  js\ui\               üst çubuk, güverte (başlık + öne çıkanlar), sol menü, liste
  js\fx\starfield.js   yıldız alanı
  i18n\tr.js, en.js    arayüz metinleri
  data\                qin export'un ürettiği veri (elle düzenlenmez)
data\quant_intel.db  arşiv (yedeklemek için kopyalaman yeterli)
.github\workflows\   GitHub'da her gün çalışan iş akışı (çek, arşivle, şifrele, yayınla)
qin\vault.py          site verisinin ve arşivin parolayla şifrelenmesi
tests\               internet gerektirmeyen testler
```

## Geliştirme rehberi

**Yeni kaynak (Substack, WordPress ya da herhangi bir RSS):** `config.json` → `sources` içine ekle.

```json
"robotwealth": { "enabled": true, "label": "Robot Wealth", "type": "rss", "url": "https://robotwealth.com/feed/" }
```

Türler: `substack` (bülten içindeki linkler ayrı öğelere bölünür), `wordpress` / `rss` (her kayıt tek öğe),
`quantocracy`, `reddit`. Özel yapılı bir kaynak için `qin\parsers.py`'ye bir fonksiyon yazıp `PARSERS`
sözlüğüne eklemek yeterli. Kaynağın rengi kendiliğinden atanır ve kalıcıdır.

**Yeni sekme:** `site\js\config.js` → `TABS` listesine bir satır, `site\i18n\*.js` dosyalarına `tab.<id>` metni.

**Yeni konu etiketi ya da araç kuralı:** `qin\enrich.py` → `TOPICS` ve `_TOOL_*`. Kurallar dışa aktarmada
yeniden hesaplanır; `qin export` sonrası eski içeriklere de yansır.

**Yeni popülerlik ölçümü:** `qin\metrics.py`'de değeri üretip `db.set_metric(...)` ile yaz;
`site\js\config.js` → `METRICS`'e ikonuyla ekle.

**Yeni dil:** `site\i18n\tr.js`'i kopyalayıp çevir, `site\js\config.js` → `LANGS`'e ekle.

**Görünüm:** renk ve yazı tipleri `site\css\tokens.css` içindeki değişkenlerdir.

**Üstteki başlık ve tanıtım cümlesi:** `site\i18n\tr.js` → `deck.title` ve `deck.lead`.

**Vitrindeki gruplar ve sıra:** `site\js\config.js` → `SPOTLIGHT_GROUPS`.

## Yayındaki site ve parola

Yayınlanan sitede içerik dosyaları şifrelidir; site açılışta parolayı sorar ve veriyi tarayıcıda çözer.
Yerelde (`site_ac.bat`) parola yoktur, veri düz yazılır. Şifreleme yalnızca `QIN_SITE_PASSWORD` ortam
değişkeni tanımlıyken devreye girer; GitHub'daki iş akışı bunu `SITE_SIFRESI` gizli ayarından alır.

## Veritabanı

| Tablo | İçerik |
|---|---|
| `posts` | Beslemeden gelen ham kayıt ve ham HTML (yeniden ayrıştırma için saklanır) |
| `items` | Tekil içerikler: başlık, link, yayıncı/yazarlar, bölüm, tür, özet, etiketler, durum, not |
| `metrics` | Öğe başına popülerlik ölçümleri (`up`, `cm`, `cit`, `hot`, ileride `likes`, `views`) |
| `translations` | Öğe başına çeviriler (dil, başlık, özet) |
| `fetch_log` | Her çekmenin sonucu |
| `meta` | Sürüm ve kaynak renk yuvaları |

## Bilinen sınırlar

- Blog yazılarının ve SSRN makalelerinin çoğu için dışarıdan alınabilen bir popülerlik sayısı yok;
  bunlarda yalnızca "kaç kaynakta geçti" sinyali olur. Yeni makalelerin atıf sayısı çoğunlukla 0'dır.
- Reddit oy sayıları için JSON adresi kullanılır; Reddit bunu reddederse RSS'e düşülür ve o çekmede
  oy sayıları güncellenmez (çekme satırında belirtilir).
- Bir bültenin birden çok sayısında geçen içerik, ilk göründüğü sayının tarihini taşır.
- Araç sinyali ve konu etiketleri anahtar kelime kurallarıdır; yanlış eşleşmeler olabilir.
- SSRN ve konferans takvimleri kapsam dışı (API yok).

## Test

```bat
.venv\Scripts\python -m unittest discover tests
```

## Kaldırma

`gorev_kaldir.bat` zamanlanmış görevleri siler; sonra klasörü silebilirsin.

## Lisans notu

`site\fonts\` içindeki Chakra Petch ve IBM Plex Sans yazı tipleri SIL Open Font License 1.1 ile dağıtılır.
