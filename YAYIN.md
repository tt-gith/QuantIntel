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

## Bundan sonra

- **Günlük güncelleme:** her sabah 08:17 civarında kendiliğinden.
- **Bir şeyi değiştirdiğinde:** GitHub Desktop'ta altta bir not yaz → **Commit to main** → **Push origin**.
  Site birkaç dakikada yenilenir.
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
- **Arşiv nerede:** **Releases → arsiv**. `quant_intel.db.enc` güncel, `onceki.db.enc` bir önceki günün
  kopyasıdır; ikisi de şifrelidir.
