# Quant Intelligence Network

Quant kaynaklarını (QuantSeeker, Quantocracy, Quantpedia, IBKR Quant, Top Traders Unplugged,
Flirting with Models, r/algotrading, arXiv q-fin) her gün çeker, tek tek içeriklere ayırır, bir SQLite
arşivine kaydeder ve bunları bir web sitesi olarak sunar. İsteğe bağlı olarak içeriği Türkçeye çevirir,
günlük ve haftalık özet yazar, özetleri abonelere e-postalar. Yol haritası: `ROADMAP.md`.
Siteyi internette yayınlamak ve ek özellikleri açmak: `YAYIN.md`.

## Önceki sürümden yükseltme

Site GitHub'da yayındaysa:

1. Zip'i depo klasörünün **üstüne** çıkar (dosyaların üzerine yazılsın). `config.json` yenilenir;
   elle değiştirdiğin bir ayar varsa yeniden gir.
2. Klasörde komut penceresi: `git add .` → `git commit -m "v6"` → `git push`.
   İş akışı kendiliğinden çalışır, site birkaç dakikada yenilenir. Arşive dokunulmaz.
3. Yeni özellikler (çeviri, özet, yönetim paneli, e-posta) gizli değerleri eklenince açılır: `YAYIN.md` 7–9.

Yalnızca bu bilgisayarda kullanıyorsan: zip'i klasörün üstüne çıkar, `qin fetch` çalıştır, `site_ac.bat` ile aç.
Yeni Python paketi gerekmiyor.

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
- **Dil:** arayüz TR/EN. LLM anahtarı tanımlıysa içerik başlık ve özetleri de Türkçeye çevrilir;
  çevrilmiş öğe «çeviri» rozeti taşır, EN seçiliyken özgün metin görünür.
- **Özetler sekmesi:** günlük ve haftalık özetler. Otomatik olanları bir dil modeli yalnızca arşivdeki
  içeriğe dayanarak yazar ve her iddiada içeriğin numarasını verir; numara kaynağa götürür.
  En yeni özet güvertede tek satırlık bir çağrıyla da görünür.
- **LLM için dışa aktar (araç çubuğu):** ekrandaki görünümü (tarih aralığı, sekme, filtreler, arama)
  hazır bir özet isteğiyle birlikte tek metne çevirir; kopyala ya da dosya olarak indir, istediğin modele ver.
- **Yönetim paneli (yalnızca yayındaki sitede, ikinci parolayla):** özet yazma ve düzenleme, abone listesi,
  «Özeti yayınla» ile e-posta gönderimi, kurulum durumu. Kurulum: `YAYIN.md` 8–9.
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
qin llm                                 :: yeni içeriği çevir, dönemi gelen özetleri yaz (API anahtarı gerekir)
qin llm --brief weekly --force          :: haftalık özeti yeniden yazdır
qin brief list                          :: özetleri listele
qin brief add ozet.md --kind weekly     :: Markdown dosyasından özet ekle (ilk satır "# Başlık")
qin brief send 12                       :: 12 numaralı özeti abonelere e-postala
qin sub add ad@ornek.com                :: abone ekle (sub list / sub remove)
```

`qin llm` için anahtar, `qin brief send` için e-posta ayarları ortam değişkeni olarak verilir
(`set GEMINI_API_KEY=...`, `set SMTP_USER=...`, `set SMTP_PASSWORD=...`). Yayındaki sitede bunların
hepsi GitHub'da çalışır; yerel komutlar yalnızca bu bilgisayardaki arşivi etkiler.

## Proje yapısı

```
config.json          kaynaklar, arXiv anahtar kelimeleri, ayarlar
qin\                 veri katmanı (Python)
  parsers.py           her kaynak türü için ayrıştırıcı
  fetch.py             indirme, kaydetme, yeniden ayrıştırma
  enrich.py            tür, konu etiketi ve araç sinyali kuralları
  metrics.py           dış popülerlik ölçümleri (atıf sayısı)
  cluster.py           aynı içeriğin kopyalarını birleştirme
  export.py            arşiv → site\data\* (yayında şifreli)
  storage.py           SQLite şeması
  llm.py               ücretsiz LLM sağlayıcılarına tek arayüz (sırayla dener)
  translate.py         başlık ve özetlerin Türkçeye çevrilmesi
  brief.py             günlük ve haftalık özetlerin yazdırılması
  md.py                özetler için küçük, güvenli Markdown çevirici (e-posta)
  mailer.py            özetlerin abonelere gönderilmesi (SMTP)
  admin.py             yönetim paketi (admin.bin) ve panel komutlarının uygulanması
  private.py           abone adresleri: arşiv içinde yönetim parolasıyla şifreli kayıt
  vault.py             site verisinin ve arşivin parolayla şifrelenmesi
site\                web sitesi (derleme adımı yok; dosyayı değiştir, sayfayı yenile)
  index.html
  css\tokens.css       renkler, yazı tipleri, ölçüler (görünümün tek adresi)
  css\app.css          yerleşim ve bileşenler
  js\config.js         sekmeler, tarih seçenekleri, popülerlik ölçümleri, vitrin grupları
  js\ui\               üst çubuk, güverte, sol menü, liste, özetler (briefs.js), yönetim paneli (admin.js)
  js\md.js             özetler için Markdown çevirici (qin\md.py ile aynı kurallar)
  js\llmexport.js      "LLM için dışa aktar" metni
  js\github.js         panelin iş akışını başlatması ve izlemesi
  js\fx\starfield.js   yıldız alanı
  i18n\tr.js, en.js    arayüz metinleri
  data\                qin export'un ürettiği veri (elle düzenlenmez)
data\quant_intel.db  arşiv (yedeklemek için kopyalaman yeterli)
.github\workflows\   GitHub'da her gün çalışan iş akışı (çek, çevir, özetle, arşivle, şifrele, yayınla)
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

**LLM sağlayıcısı ya da modeli:** `config.json` → `llm.providers`. OpenAI uyumlu her uç nokta eklenebilir
(adres, model listesi, anahtarın ortam değişkeni). Sıradaki ilk yanıt veren kullanılır.

**Özetin üslubu, uzunluğu, bölümleri:** `qin\brief.py` → `SYSTEM`; sayılar `config.json` → `llm.briefs`.
"LLM için dışa aktar"daki hazır istek: `site\i18n\tr.js` → `export.prompt`.

**Görünüm:** renk ve yazı tipleri `site\css\tokens.css` içindeki değişkenlerdir.

**Üstteki başlık ve tanıtım cümlesi:** `site\i18n\tr.js` → `deck.title` ve `deck.lead`.

**Vitrindeki gruplar ve sıra:** `site\js\config.js` → `SPOTLIGHT_GROUPS`.

## Yayındaki site ve parola

Yayınlanan sitede içerik dosyaları şifrelidir; site açılışta parolayı sorar ve veriyi tarayıcıda çözer.
Yerelde (`site_ac.bat`) parola yoktur, veri düz yazılır. Şifreleme yalnızca `QIN_SITE_PASSWORD` ortam
değişkeni tanımlıyken devreye girer; GitHub'daki iş akışı bunu `SITE_SIFRESI` gizli ayarından alır.

İkinci bir parola (`ADMIN_SIFRESI`) tanımlıysa site verisinin yanına `admin.bin` yazılır. Bu parolayla
giren kişi yönetim panelini görür. Panel bir şeyi doğrudan değiştiremez: işlemi yönetim anahtarıyla
şifreleyip günlük iş akışına girdi olarak yollar, iş akışı komutu çözer ve arşive uygular. Abone
adresleri arşivin içinde yönetim parolasıyla ayrıca şifrelenir (`qin\private.py`): site parolasını bilen
biri arşivi açsa da adresleri okuyamaz. Adresler iş akışı günlüklerine de yazılmaz.

## Veritabanı

| Tablo | İçerik |
|---|---|
| `posts` | Beslemeden gelen ham kayıt ve ham HTML (yeniden ayrıştırma için saklanır) |
| `items` | Tekil içerikler: başlık, link, yayıncı/yazarlar, bölüm, tür, özet, etiketler, durum, not |
| `metrics` | Öğe başına popülerlik ölçümleri (`up`, `cm`, `cit`, `hot`, ileride `likes`, `views`) |
| `translations` | Öğe başına çeviriler (dil, başlık, özet) |
| `briefs` | Günlük ve haftalık özetler (otomatik ya da elle), e-postayla gönderilme durumu |
| `fetch_log` | Her çekmenin sonucu |
| `meta` | Sürüm, kaynak renk yuvaları, son LLM çalışması; `private`: abone adresleri ve son yönetim işlemi (yönetim parolasıyla ayrıca şifreli) |

## Bilinen sınırlar

- Blog yazılarının ve SSRN makalelerinin çoğu için dışarıdan alınabilen bir popülerlik sayısı yok;
  bunlarda yalnızca "kaç kaynakta geçti" sinyali olur. Yeni makalelerin atıf sayısı çoğunlukla 0'dır.
- Reddit oy sayıları için JSON adresi kullanılır; Reddit bunu reddederse RSS'e düşülür ve o çekmede
  oy sayıları güncellenmez (çekme satırında belirtilir).
- Bir bültenin birden çok sayısında geçen içerik, ilk göründüğü sayının tarihini taşır.
- Araç sinyali ve konu etiketleri anahtar kelime kurallarıdır; yanlış eşleşmeler olabilir.
- SSRN ve konferans takvimleri kapsam dışı (API yok).
- Çeviri ve özetler bir dil modelinin çıktısıdır; hata içerebilir. Model yalnızca başlık ve özetleri görür,
  içeriğin tam metnini okumaz.
- Yönetim panelindeki her işlem bir iş akışı çalıştırır; sonuç iki üç dakikada görünür.
- Abonelik kendi kendine yapılamaz; adresleri yönetici ekler.

## Test

```bat
.venv\Scripts\python -m unittest discover tests
```

## Kaldırma

`gorev_kaldir.bat` zamanlanmış görevleri siler; sonra klasörü silebilirsin.

## Lisans notu

`site\fonts\` içindeki Chakra Petch ve IBM Plex Sans yazı tipleri SIL Open Font License 1.1 ile dağıtılır.
