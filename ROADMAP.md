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
│  → site verisini şifreli üret    │           └───────────────────────────────────┘
│ Arşiv: Releases > "arsiv" (şifreli)│
└──────────────────────────────────┘
```

- **Tek servis:** her şey GitHub'da. Kart, ek hesap ya da kullanıcı sınırı yok.
- **Site statiktir:** tarayıcı yalnızca hazır dosyaları okur. Sunucu bakımı yok, maliyet yok.
- **Gizlilik:** depo ve site adresi herkese açıktır; içerik ve arşiv ortak bir parolayla şifrelenir.
  Kişi bazlı giriş yoktur; birini çıkarmak için parola değiştirilir.
- **Çekme bulutta çalışır:** bilgisayarının açık olması gerekmez. Yerel kurulum geliştirme için kalır.

## Aşamalar

### 1–2. Veri katmanı v2 ve site v1 — tamamlandı (yerelde çalışıyor)
- Tek akış, sol kaynak menüsü, tür sekmeleri, sağ üstte tarih aralığı (varsayılan 7 gün).
- Her öğede tarih ve son bir haftadakilerde "kaç gün önce".
- Popülerlik: Reddit oy/yorum, makale atıfları, çoklu kaynak sayısı, "çok tıklanan" işareti; popülerliğe göre sıralama.
- Çapraz kaynak eşleştirme: adres temizleme + başlık benzerliği; aynı içerik listede bir kez görünür.
- Dil altyapısı: arayüz TR/EN; içerik çevirisi için veri alanı hazır (Aşama 5'te dolacak).
- Beğeni düğmesi: şimdilik yalnızca tarayıcıda (Aşama 4'te ortak olacak).
- Güvertede site tanımı ve "öne çıkanlar" vitrini (Aşama 5'te seçimi ve özetini LLM yapabilir).

### 3. Yayın — dosyaları hazır, kurulum sende
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

### 5. Yapay zekâ desteği (ücretsiz katman)
- **Türkçe içerik:** başlık ve özetlerin çevirisi; `translations` tablosuna yazılır, site TR seçiliyken gösterir.
- **5 dakikalık özet:** günlük ya da haftalık; o dönemin içeriğinden okunabilir bir brifing sayfası.
- Çalışma yeri: günlük iş akışının sonu. Hacim küçük (haftada birkaç yüz kısa metin), ücretsiz katmanlara sığar.
- Sağlayıcı seçimi (Gemini, Groq, Cloudflare Workers AI, GitHub Models) kurulum sırasında güncel
  sınırlara bakılarak yapılacak.

### 6. E-posta aboneliği
- Bir filtreye (ör. "LLM/AI + Araçlar") ya da günlük özete abone ol; her sabah e-posta gelsin.
- İçerik site hazır olunca kararlaştırılacak. Gönderim: günlük iş akışından, ücretsiz bir e-posta servisiyle.

### Sürekli iyileştirme listesi
- Sessiz görünen kaynakların (Systematic Traders, OpenQuant) yerine ya da yanına yenileri.
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
