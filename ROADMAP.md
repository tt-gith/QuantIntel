# Yol haritası

Hedef: Quant kaynaklarını her gün kendiliğinden toplayan, bilgisayar kapalıyken de çalışan,
yalnızca sen ve davet ettiğin birkaç kişinin girebildiği, sürekli geliştirilebilir bir arşiv sitesi.

## Mimari

```
GitHub Actions (her gün)                        GitHub Pages
┌──────────────────────────────────┐           ┌───────────────────────────────────┐
│ qin fetch                        │  yayınla  │ site/ klasörü (herkese açık adres) │
│  → kaynakları çek                │ ────────► │ içerik dosyaları şifreli           │
│  → SQLite arşivini güncelle      │           │ tarayıcı parolayı sorar, çözer     │
│ qin llm                          │           │                                   │
│  → çevir, günlük/haftalık özet   │ ◄──────── │ yönetim paneli (ikinci parola):    │
│  → site verisini şifreli üret    │  şifreli  │ özet ekle, abonelere yayınla       │
│ qin admin (panel komutu gelince) │   komut   └───────────────────────────────────┘
│ Arşiv: Releases > "arsiv" (şifreli)│
└──────────────────────────────────┘
```

- **Tek servis:** her şey GitHub'da. Kart, ek hesap ya da kullanıcı sınırı yok.
- **Site statiktir:** tarayıcı yalnızca hazır dosyaları okur. Sunucu bakımı yok, maliyet yok.
- **Gizlilik:** depo ve site adresi herkese açıktır; içerik ve arşiv ortak bir parolayla şifrelenir.
  Kişi bazlı giriş yoktur; birini çıkarmak için parola değiştirilir.
- **Çekme bulutta çalışır:** bilgisayarının açık olması gerekmez. Yerel kurulum geliştirme için kalır.
- **Yazma işlemleri de iş akışından geçer:** site durağan olduğu için yönetim paneli işlemi şifreli bir
  komut olarak iş akışına yollar; sonuç iki üç dakikada yayına girer.

## Aşamalar

### 1–2. Veri katmanı v2 ve site v1 — tamamlandı (yerelde çalışıyor)
- Tek akış, sol kaynak menüsü, tür sekmeleri, sağ üstte tarih aralığı (varsayılan 7 gün).
- Her öğede tarih ve son bir haftadakilerde "kaç gün önce".
- Popülerlik: Reddit oy/yorum, makale atıfları, çoklu kaynak sayısı, "çok tıklanan" işareti; popülerliğe göre sıralama.
- Çapraz kaynak eşleştirme: adres temizleme + başlık benzerliği; aynı içerik listede bir kez görünür.
- Dil altyapısı: arayüz TR/EN; içerik çevirisi Aşama 5'te eklendi.
- Beğeni düğmesi: şimdilik yalnızca tarayıcıda (Aşama 4'te ortak olacak).
- Güvertede site tanımı ve "öne çıkanlar" vitrini.

### 3. Yayın — tamamlandı (site yayında)
Adım adım rehber: `YAYIN.md`. İş akışı: `.github/workflows/gunluk.yml`.
- Her gün: testler → şifreli arşivi indir ve aç → `qin fetch` → arşivi şifrele ve kaydet → siteyi yayınla.
- Kod gönderildiğinde de aynı iş çalışır; site birkaç dakikada yenilenir.
- Arşiv küçülürse kaydedilmez; bir önceki günün kopyası yedek olarak saklanır.

Bilinen risk: Reddit (ve belki bazı Substack beslemeleri) bulut sunucularından gelen istekleri
engelleyebilir. Sitedeki kaynak ışıkları bunu gösterir. Çözüm sırası: resmi Reddit API anahtarı →
olmazsa o kaynağı yerel bilgisayar besler.

### 4. Ortak beğeniler
- GitHub Pages veri yazamaz; beğeniler için küçük, ücretsiz ve kart istemeyen bir veritabanı servisi eklenecek
  (seçim o aşamada güncel koşullara bakılarak yapılacak).
- Kimlik: site ortak parolayla açıldığı için kişi, ilk beğenide sorulan bir takma adla ya da o servisin
  girişiyle ayırt edilecek.
- Her öğede toplam beğeni ve kimin beğendiği; "arkadaşların beğendikleri" sekmesi.
- Site içi beğeniler popülerlik puanına girer; zamanla en anlamlı sinyal bu olur.
- Arayüz hazır: `site/js/likes.js` içindeki üç fonksiyon o servise bağlanacak.

### 5. Yapay zekâ desteği — tamamlandı (API anahtarı eklenince çalışır)
- **Türkçe içerik:** başlık ve özetler çevrilir; site TR seçiliyken çeviriyi gösterir.
- **Günlük ve haftalık özet:** dönemin en güçlü içerikleri modele numaralı liste olarak verilir; model
  yalnızca bu listeye dayanır ve her iddiada numara verir. Sitede Özetler sekmesi.
- **Sağlayıcı:** Gemini (ücretsiz katman), yedek olarak Groq. GitHub Models 30 Temmuz 2026'da kapatıldığı
  için kullanılamadı. Yeni sağlayıcı `config.json`'a bir kayıt eklemekle bağlanır.
- **Elle özet:** "LLM için dışa aktar" ile görünüm istenen modele verilir, çıkan özet panelden eklenir.

### 6. Yönetim paneli ve özet e-postaları — tamamlandı (gizli değerler eklenince çalışır)
- İkinci parola ile yönetim paneli: özet yaz/düzenle/sil, abone listesi, kurulum durumu.
- "Özeti yayınla": seçilen özet (otomatik ya da elle) abonelere e-postayla gider. Otomatik gönderim yok.

Sırada olabilecekler:
- Otomatik gönderim seçeneği (ör. haftalık özet hazır olunca kendiliğinden gitsin).
- Bir filtreye abonelik (ör. "LLM/AI + Araçlar" içerikleri her sabah e-postayla).
- Abonenin kendi kendine kaydolup ayrılabilmesi (bir form servisi gerektirir).
- Vitrindeki öne çıkanların seçimine LLM desteği.

### Sürekli iyileştirme listesi
- Kaynak listesi: Systematic Traders ve OpenQuant duraklatıldı (aylardır yeni sayı yok, ayrıca substack.com
  adresleri GitHub sunucularını engelliyor). Yerlerine IBKR Quant, Top Traders Unplugged ve
  Flirting with Models eklendi. Etkinlik ve sektör haberi için hâlâ iyi bir kaynak aranıyor.
- Yeni popülerlik ölçümleri: YouTube görüntülenme, Substack beğenileri.
- Etkinlikler için gerçek etkinlik tarihi ve takvim görünümü.
- Konu etiketlerinin iyileştirilmesi; araç sinyalinin yanlış pozitiflerinin azaltılması.

## Popülerlik verisinin bugünkü durumu

| İçerik | Ölçüm | Kaynağı |
|---|---|---|
| Reddit tartışmaları | oy ve yorum sayısı | Reddit |
| arXiv ve SSRN makaleleri | atıf sayısı (yeni makalelerde çoğunlukla 0) | Semantic Scholar |
| Her tür içerik | kaç farklı kaynakta geçtiği | bu sistemin kendi eşleştirmesi |
| QuantSeeker makaleleri | "geçen haftanın en çok tıklananları" işareti | bültenin kendisi |
| Her tür içerik (Aşama 4) | site içi beğeni | sen ve arkadaşların |

Blog yazılarının ve SSRN makalelerinin çoğu için dışarıdan alınabilen bir sayı yok. Bu yüzden farklı
ölçümler tek bir 0–100 puana çevriliyor: her ölçüm kendi türü içinde yüzdelik sıraya göre en çok 60,
her ek kaynak +20, "çok tıklanan" +15 puan getirir.
