# Siteyi internette yayınlama

Bu adımlar bittiğinde kaynaklar her sabah GitHub'da kendiliğinden çekilir ve site
`https://<kullanıcı-adın>.github.io/quant-intel/` adresinde yayınlanır. Bilgisayarının açık olması gerekmez.
Yalnızca bir GitHub hesabı gerekir; ücretsizdir, kart istemez.

Site adresi ve kod herkese açıktır, ama içerik bir parolayla şifrelenir: parolayı bilmeyen yalnızca
bir giriş ekranı görür.

## 1. Hazırlık

- GitHub hesabı aç: <https://github.com/signup>
- GitHub Desktop'ı kur ve hesabınla giriş yap: <https://desktop.github.com>

## 2. Projeyi GitHub'a gönder

1. GitHub Desktop → **File → Add local repository** → proje klasörünü seç (içinde `run.py` olan klasör).
2. Çıkan uyarıdaki **create a repository** bağlantısına tıkla → **Create repository**.
3. Üstteki **Publish repository** düğmesine bas.
   **Keep this code private** işaretini **kaldır** → **Publish repository**.

Arşivin (`data\` klasörü) ve yerel dosyaların gönderilmez.

## 3. Parolayı belirle

1. <https://github.com> → az önce oluşan `quant-intel` deposu → **Settings**.
2. Sol menü: **Secrets and variables → Actions** → **New repository secret**.
3. **Name:** `SITE_SIFRESI`
   **Secret:** parolan. En az 12 karakter; dört beş kelimelik bir cümle en iyisi
   (ör. `mavi kedi sabah treni kaçırdı`).
4. **Add secret**.

Bu parolayı unutma: hem siteye girişte hem de arşivin açılmasında kullanılır.

## 4. Yayını aç

Aynı **Settings** sayfasında sol menüden **Pages** → **Build and deployment** altında
**Source: GitHub Actions** seç.

## 5. İlk yayını başlat

1. Deponun üst menüsünden **Actions** → soldan **Günlük çekme ve yayın** → sağdaki **Run workflow** →
   yeşil **Run workflow** düğmesi.
2. 3–5 dakika bekle. Çalışmanın yanında yeşil tik çıkınca site yayındadır.
3. Adres: `https://<kullanıcı-adın>.github.io/quant-intel/` (**Settings → Pages** sayfasında da yazar).

Siteyi aç, parolanı gir. Arkadaşlarınla adresi ve parolayı paylaşman yeterli.

## 6. Bilgisayarındaki zamanlanmış görevleri kapat

`gorev_kaldir.bat` dosyasını çalıştır. Çekme artık GitHub'da yapılıyor.
`site_ac.bat` ve `qin` komutları deneme amaçlı çalışmaya devam eder.

---

# Ek özellikler (hepsi isteğe bağlı)

Aşağıdaki üç bölüm birbirinden bağımsızdır; istediğini, istediğin zaman kurabilirsin. Hepsi aynı yere
birer **gizli değer** eklemekten ibarettir: depo → **Settings → Secrets and variables → Actions →
New repository secret**. Tanımlı olmayan özellik sessizce atlanır, site çalışmaya devam eder.
Gizli değer ekledikten sonra etkisini hemen görmek için **Actions → Günlük çekme ve yayın → Run workflow**.

| Gizli değer | Ne işe yarar |
|---|---|
| `GEMINI_API_KEY` | Çeviri ve otomatik günlük/haftalık özet |
| `GROQ_API_KEY` | Yedek LLM (Gemini'ye ulaşılamazsa) |
| `ADMIN_SIFRESI` | Yönetim panelini açan ikinci parola |
| `ADMIN_TOKEN` | Panelin işlemleri kendisi başlatabilmesi |
| `SMTP_USER`, `SMTP_PASSWORD` | Özetlerin abonelere e-postayla gönderilmesi |

## 7. Çeviri ve otomatik özet (ücretsiz LLM)

1. <https://aistudio.google.com/apikey> → Google hesabınla gir → **Create API key** → anahtarı kopyala.
   Kart istemez.
2. Depoda yeni gizli değer: **Name** `GEMINI_API_KEY`, **Secret** kopyaladığın anahtar.
3. İstersen yedek: <https://console.groq.com/keys> → **Create API Key** → gizli değer adı `GROQ_API_KEY`.

Bundan sonra her günlük çalışmada:

- Yeni içeriklerin başlık ve özetleri Türkçeye çevrilir (site TR seçiliyken çeviri, yanında «çeviri» rozetiyle görünür;
  EN'de özgün metin).
- Günün özeti yazılır; her hafta başında bir önceki haftanın (Pzt–Paz) özeti eklenir.
  Sitede **Özetler** sekmesinde durur. Özetteki numaralar ilgili içeriğe götürür.
- LLM'e ulaşılamazsa ya da günlük ücretsiz sınır dolarsa o adım atlanır, kalan iş ertesi güne kalır.

Bilmen gerekenler:

- Modele yalnızca içeriklerin başlık ve özetleri gönderilir (zaten herkese açık metinler). Google, ücretsiz
  katmanda gönderilen metni ürünlerini geliştirmek için kullanabildiğini belirtiyor.
- Özetler bir dil modelinin yazdığı metinlerdir; yanlış anlama ya da eksik olabilir. Önemli bir şey için
  bağlantıdaki kaynağa bak.
- Model adları ve sınırlar zamanla değişir. Ayarlar `config.json` → `llm` altındadır; bir model kaldırılırsa
  listedeki sıradaki denenir.
- Kendi seçtiğin bir modelle (Claude, ChatGPT...) özet hazırlamak için: sitede araç çubuğundaki
  **LLM için dışa aktar** → metni modele yapıştır → çıkan özeti yönetim panelinden ekle (8. bölüm).

## 8. Yönetim paneli (ikinci parola)

Yönetim parolasıyla girildiğinde üst çubukta **Yönetim** düğmesi çıkar. Panelden özet ekler ve düzenler,
abone listesini yönetir, istediğin özeti **Özeti yayınla** ile abonelere e-postalarsın.

**a) Parolayı belirle.** Gizli değer: **Name** `ADMIN_SIFRESI`. En az 16 karakter ve site parolasından
farklı olmalı (ör. beş altı kelimelik bir cümle). Bu parola siteyi de açar; arkadaşlarınla yalnızca
`SITE_SIFRESI`'ni paylaş.

**b) Panelin GitHub anahtarını oluştur.** Site durağan bir sayfadır, kendi başına bir şey kaydedemez;
panel her işlemi şifreli bir komut olarak günlük iş akışına gönderir. Bunu yapabilmesi için yalnızca bu
depoda geçerli, dar yetkili bir anahtar gerekir:

1. GitHub'da sağ üstteki profil resmi → **Settings** → en altta **Developer settings** →
   **Personal access tokens → Fine-grained tokens** → **Generate new token**.
2. **Token name:** `quant-intel panel`. **Expiration:** en uzun süreyi seç (ör. 1 yıl).
3. **Repository access:** **Only select repositories** → `quant-intel`.
4. **Permissions → Repository permissions → Actions:** **Read and write**. Başka izin verme.
5. **Generate token** → `github_pat_...` ile başlayan değeri kopyala.
6. Depoda yeni gizli değer: **Name** `ADMIN_TOKEN`, **Secret** kopyaladığın değer.

Bu adımı atlarsan panel yine çalışır, ama her işlemde sana bir komut metni verir ve onu
**Actions → Run workflow → komut** kutusuna elle yapıştırman gerekir.

**c) İş akışını bir kez çalıştır**, sonra siteyi açıp kilit düğmesiyle çık ve yönetim parolasıyla gir.

Nasıl çalışır, ne kadar güvenli:

- Her işlem (özet ekleme, gönderme, abone ekleme) iş akışını çalıştırır; sonucun sitede görünmesi
  **iki üç dakika** sürer. Panel durumu kendisi izler ve bitince sayfayı yeniler.
- Abone adresleri, GitHub anahtarı ve site anahtarı `admin.bin` adlı dosyada, yönetim parolasıyla
  şifreli olarak sitede durur. Dosya herkese açık adreste olduğu için **parolanın uzun olması tek korumadır**;
  kısa ya da tahmin edilebilir bir parola seçme.
- Abone adresleri arşivde de yönetim parolasıyla ayrıca şifrelidir: site parolasını bilen arkadaşların
  adresleri göremez. Bu yüzden **yönetim parolasını değiştirirsen abone listesi sıfırlanır**; değiştirmeden
  önce listeyi panelden bir yere kopyala, sonra yeniden ekle.
- Bir işlem «tamamlanamadı» görünürse hemen yeniden deneme: sayfayı yenileyip özet listesine bak.
  Aynı taslak iki kez eklenmez ve gönderilmiş bir özet, «Yeniden yayınla» demediğin sürece ikinci kez gitmez.
- Yönetim parolası ele geçerse yapılabilecekler: siteyi okumak, özet ekleyip silmek, abonelere e-posta
  göndermek, iş akışını çalıştırmak. Kod ve arşiv değiştirilemez. Şüphelenirsen `ADMIN_SIFRESI`'ni değiştir
  ve GitHub'da anahtarı sil (**Developer settings → Fine-grained tokens → Delete**).
- Anahtarın süresi dolunca panel «GitHub anahtarı reddedildi» der: (b) adımını yineleyip `ADMIN_TOKEN`'ı güncelle.

## 9. Özetleri e-postayla gönderme

Gönderim için bir e-posta hesabı gerekir. En kolayı bu iş için ayrı bir Gmail hesabı açmaktır:

1. O hesapta **2 Adımlı Doğrulama**'yı aç: <https://myaccount.google.com/security>.
2. <https://myaccount.google.com/apppasswords> → bir ad yaz (ör. `quant-intel`) → **Oluştur** →
   16 harflik uygulama parolasını kopyala.
3. Depoda iki gizli değer: `SMTP_USER` = hesabın adresi, `SMTP_PASSWORD` = uygulama parolası.
4. İş akışını bir kez çalıştır. Panelde **Durum** bölümünde «E-posta gönderimi: Hazır» yazmalı.

Başka bir sağlayıcı kullanacaksan aynı sayfanın **Variables** sekmesinden `SMTP_HOST` ve `SMTP_PORT`
(587 ya da 465) tanımla.

Kullanım:

- **Aboneler** bölümünden adresleri ekle. Liste yalnızca panelde görünür; her aboneye ayrı e-posta gider,
  kimse başkasının adresini görmez.
- **Hiçbir e-posta kendiliğinden gitmez.** Otomatik özetler yalnızca sitede yayınlanır; e-posta yalnızca
  **Özetler → Özeti yayınla** (ya da **Özet yaz → Ekle ve abonelere gönder**) ile, onay verdikten sonra çıkar.
- Yayınlamadan önce **Deneme gönder** ile özeti yalnızca kendi adresine yollayıp nasıl göründüğüne bakabilirsin.
- Ayrılmak isteyen abone e-postayı yanıtlar; sen de panelden adresini çıkarırsın.
- Gmail'in günlük gönderim sınırı birkaç kişilik bir liste için fazlasıyla yeterlidir.

---

## Bundan sonra

- **Günlük güncelleme:** her sabah 08:17 civarında kendiliğinden.
- **Bir şeyi değiştirdiğinde:** GitHub Desktop'ta altta bir not yaz → **Commit to main** → **Push origin**.
  Komut satırından: `git add .` → `git commit -m "not"` → `git push`. Site birkaç dakikada yenilenir.
- **"Bu cihazda hatırla":** işaretliyse parola o tarayıcıda bir daha sorulmaz. Üst çubuktaki kilit
  düğmesi o cihazdaki kaydı siler.

## Parolayı değiştirmek

1. **Settings → Secrets and variables → Actions** → **New repository secret** →
   Name: `SITE_SIFRESI_ESKI`, Secret: şimdiki parola.
2. `SITE_SIFRESI` satırındaki kalem simgesiyle yeni parolayı gir.
3. **Actions → Günlük çekme ve yayın → Run workflow**.
4. Yeşil tik çıkınca `SITE_SIFRESI_ESKI` kaydını silebilirsin. Herkes yeni parolayı yeniden girer.

## Sorun olursa

- **Actions'ta kırmızı çarpı:** çalışmaya tıkla, kırmızı adımın çıktısındaki son satırlara bak.
  "Hiçbir kaynağa ulaşılamadı" geçici bir ağ sorunudur; **Re-run jobs** ile tekrarla.
- **Tek bir kaynak çekilemiyor:** iş yine başarılı sayılır; sitede o kaynağın ışığı kırmızı yanar ve nedeni yazar.
  Reddit'in GitHub sunucularını engellemesi olasıdır.
- **"Arşiv bu parolayla açılamadı":** parola değişmiş ama eski parola verilmemiş. "Parolayı değiştirmek"
  bölümündeki 1. adımı uygula.
- **Parolayı tamamen unuttuysan:** arşiv açılamaz. Deponun **Releases** bölümündeki `arsiv` kaydını sil,
  yeni bir `SITE_SIFRESI` gir ve iş akışını çalıştır; arşiv kaynakların son birkaç haftasıyla yeniden başlar.
- **Özetler sekmesi boş:** `GEMINI_API_KEY` tanımlı mı? Yönetim panelinde **Durum** bölümü son LLM
  çalışmasının ne yaptığını ve varsa hata iletisini gösterir. Panel yoksa: Actions'taki son çalışmada
  «Çevir ve özetle (LLM)» adımının çıktısına bak.
- **Yönetim parolası kabul edilmiyor:** `ADMIN_SIFRESI` ekledikten sonra iş akışı en az bir kez çalışmış
  olmalı. Parola 16 karakterden kısaysa ya da site parolasıyla aynıysa iş akışı ilk adımda kırmızı verir.
- **«Özeti yayınla» düğmesi soluk:** e-posta ayarlı değil ya da abone yok; düğmenin üzerine gelince nedeni yazar.
- **E-posta gitmedi:** panelde işlemin sonucunda hata iletisi görünür. Gmail'de en sık neden, hesap
  parolasının uygulama parolası yerine girilmesidir.
- **Arşiv nerede:** **Releases → arsiv**. `quant_intel.db.enc` güncel, `onceki.db.enc` bir önceki günün
  kopyasıdır; ikisi de şifrelidir.
