# Clipboard AI — macOS

`?` ile başlayan bir metni kopyaladığınızda Ollama'ya gönderilir ve cevap
otomatik olarak panonuza yazılır. Menü çubuğundan durumu görür, kısayolla
hızlı soru sorabilirsiniz.

## Tek komutla kurulum

```bash
cd macos
./install.sh
```

Kurulum betiği sizin yerinize:

1. Homebrew yoksa kurar
2. **Ollama**'yı kurar ve servisini başlatır
3. Modeli indirir (varsayılan `qwen2.5:7b`)
4. İzole bir Python `venv` oluşturup bağımlılıkları kurar
5. Oturum açılışında otomatik başlaması için bir **LaunchAgent** kurar
6. Uygulamayı **hemen başlatır** — kurulur kurulmaz menü çubuğunda 🟢 görünür

Farklı model için:

```bash
OLLAMA_MODEL=llama3.1:8b ./install.sh
```

## Kullanım

- **Pano yolu:** Başına `?` koyduğunuz bir metni kopyalayın
  (ör. `?bu cümleyi İngilizceye çevir: merhaba dünya`). Cevap panonuza yazılır,
  `Cmd+V` ile yapıştırın.
- **Hızlı soru:** `Cmd+Alt+Space` ile açılan kutuya sorunuzu yazın.
- **Menü çubuğu:** 🟢 bekliyor · 🟡 işleniyor · 🔴 hata. Son soru/cevap ve log
  buradan erişilebilir.

### Görünmeden yazma (otomatik daktilo)

`config.json` içinde `"auto_type": true` yaparsanız cevap panoya değil,
o an odaklı olan alana doğrudan yazılır. Ayar dosyası:

```
~/Library/Application Support/ollama-clipboard/config.json
```

## Erişilebilirlik izni (önemli)

Kısayol ve otomatik yazma için macOS izni gerekir:

**Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik** listesine
şu python'u ekleyip açın:

```
~/Library/Application Support/ollama-clipboard/venv/bin/python
```

## Kaldırma

```bash
cd macos
./uninstall.sh
```

Ollama ve indirilen modeller silinmez (isterseniz
`brew uninstall ollama`).

## Notlar

- Windows sürümü kök dizindeki `monitor.py` dosyasındadır. macOS sürümü,
  `keyboard`/`pystray`/`winreg` yerine yerel `pynput` + `rumps` + LaunchAgent
  kullanır.
- Ayarlar, loglar ve venv tek bir yerde toplanır:
  `~/Library/Application Support/ollama-clipboard/`
