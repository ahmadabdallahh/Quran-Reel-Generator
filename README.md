# 📖 Quran Reels Generator | أداة عمل ريلز القرآن الكريم

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FFmpeg-6.0+-green.svg" alt="FFmpeg 6.0+">
  <img src="https://img.shields.io/badge/Flask-3.0+-orange.svg" alt="Flask 3.0+">
  <img src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg" alt="License">
</p>

<p align="center">
  <strong>English</strong> | <a href="#arabic">العربية</a>
</p>

---

## 🌍 English

An automated AI-powered tool to create professional Quranic Reels/Shorts video content. It synchronizes Quranic recitation audio with beautiful animated background videos — perfect for Instagram Reels, TikTok, and YouTube Shorts — with the recited ayah's exact Uthmani text rendered on each segment.

### ✨ Key Features

#### 📖 Ayah Text Sync (spec `specs/002-ayah-text-sync/`)
- **Read-along display**: every segment shows the complete text of the ayah being recited, entering/exiting exactly at segment boundaries; `show_text` toggle (default on) reproduces the textless pipeline when off
- **Correct Arabic shaping**: Pillow + RAQM rendering (connected letterforms, tashkeel) in the bundled Quranic font `assets/fonts/ScheherazadeNew-Regular.ttf`, with system-font fallback chain
- **Always legible**: measured auto-fit wrap (never clipped, legibility floor kept), semi-transparent backing box with automatic ≥4.5:1 contrast guard, per-template accent profiles (`ramadan`, `normal`, `masjid`, `islamic`)
- **Text position**: lower-center or vertically-centered block (`text_position: lower | middle`, default `lower`)
- **Loud failures**: a text-fetch failure aborts the job with a clear error — never a silent textless "success"
- **Word highlighting** (experimental, default off): karaoke-style gold spotlight advancing word-by-word with proportional timing, capped at 60 overlay layers for long ayahs, clean fallback to plain display when timings are unavailable

### ✨ Key Features

#### 🎥 Video Production
- **Full Automation**: Automatically fetches Quranic recitation audio from online sources
- **High Quality**: 1080×1920 (9:16) vertical format optimized for social media platforms
- **Multiple Formats**: Reels, Story, and Post formats supported
- **Smart Audio**: Automatic silence trimming for perfect synchronization between ayahs
- **Fast Processing**: FFmpeg stream copy for instant segment merging without quality loss
- **Background Variety**: Smart rotation system prevents repeating the same video per ayah
- **Progressive Crossfades**: Smooth transitions between ayah segments

#### 🎙️ Supported Reciters
12+ famous reciters including multiple quality options:
- Sheikh AbdulBasit AbdulSamad (Murattal, Mujawwad, 64/128kbps)
- Sheikh Abdurrahman As-Sudais
- Sheikh Muhammad Siddiq Al-Minshawy (Mujawwad)
- Sheikh Saud Ash-Shuraym
- Sheikh Mahmoud Khalil Al-Husary
- Sheikh Mahmoud Ali Al-Banna
- Sheikh Ahmed Neana
- Sheikh Ali Jaber
- Sheikh Mohammad Al-Tablawi
- Sheikh Mustafa Ismail

#### 🎨 Design & Customization
- **Smart Backgrounds**: Organized by style (Nature, Islamic, Masjid, Night) with progressive crossfade transitions
- **Visual Templates**: 4 professional themes (Ramadan, Normal, Masjid, Islamic) driving background style and video transitions
- **Automatic Brightness Detection**: Backgrounds intelligently selected to match audio dynamics

#### ⚙️ Advanced Settings
- **Ayah Selection**: Smart validation prevents invalid selections
- **Quality Levels**: Low (fast), Medium, High (slow/best quality)
- **Progress Tracking**: Real-time logs and percentage completion via `GET /api/progress`
- **Preview**: `POST /api/preview` renders a single ayah at low quality; the built-in player offers play/pause, 0.5–2× speed, fullscreen, and a time label
- **Modern UI**: Glassmorphism design with premium aesthetics and dark theme
- **Background Selection**: Intelligently adapted to audio dynamics
- **Crossfade Transitions**: Smooth segment-to-segment transitions
- **Request fields**: `show_text` (default `true`), `highlight_words` (default `false`), `text_position` (`lower`|`middle`, default `lower`) — `camelCase` aliases accepted; see `specs/002-ayah-text-sync/contracts/generate-api.md`

### 🚀 Quick Start

#### Prerequisites
- Python 3.11 or higher
- Windows 10/11 or Linux/macOS
- 4GB+ RAM (8GB recommended for 1080p)
- 2GB free disk space
- FFmpeg 6.0+ (download from ffmpeg.io or package manager)

#### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Quran-Reels-Generator

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\\Scripts\\activate

# Activate (Linux/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Add your backgrounds (optional but recommended)
# Place .mp4 videos in: vision/nature/, vision/islamic/, vision/masjid/, vision/night/

# Run the server
python main.py

# Open browser at http://localhost:5000
```

#### Usage

1. **Add Backgrounds**: Place .mp4 files in `vision/` subdirectories (nature, islamic, masjid, night)
2. **Run Server**: Execute `python main.py` and wait for initialization
3. **Open UI**: Visit `http://localhost:5000` in your browser
4. **Create Video**:
   - Select reciter from dropdown
   - Search and select Surah (use the search box)
   - Set start and end ayah numbers (default: 1-7)
   - Choose quality and template
   - Optionally add your name
   - Use the Bismillah checkbox to start with a title card (silent)
   - Keep "Show ayah text" checked (or pick text position: bottom / middle)
   - Optionally enable experimental word highlighting
   - Set maximum duration (optional)
   - Set recitation speed (0.5× slower to 2.0× faster)
   - Choose transition style between ayahs
   - Click "Preview" for a fast single-ayah check, or "Generate Video"

### 📁 Project Structure

```
Quran-Reels-Generator/
├── main.py              # Flask routes + video build pipeline (build_video, segments)
├── UI.html              # Web interface (single-page application)
├── main.js              # Frontend logic, API calls, preview player
├── style.css            # Glassmorphism theme + player styles
├── requirements.txt     # Python dependencies
├── AGENTS.md            # Contributor notes (commands, traps, architecture)
├── quran_reels/         # Backend package (leaf modules, no import of main)
│   ├── config.py        # Templates, presets, reciters, text-render constants
│   └── services/
│       ├── audio.py     # Recitation download, ayah text fetch (api.alquran.cloud)
│       ├── background.py# Background rotator + cache (lazy imports of main)
│       └── text_overlay.py # RAQM ayah renderer, word boxes/timings, highlight sprite
├── assets/fonts/        # Bundled Quranic font (Scheherazade New, OFL)
├── specs/               # Feature specs + API contracts (see 002-ayah-text-sync/)
├── .archify/            # System architecture diagram (HTML)
├── vision/              # Background video library
│   ├── nature/          # Nature scenery videos
│   ├── islamic/         # Islamic art/pattern videos
│   ├── masjid/          # Mosque/prayer videos
│   └── night/           # Night/evening ambience videos
├── outputs/             # Generated content
│   └── video/           # Final rendered videos
├── cache/               # Audio + preprocessed background cache
└── temp/                # Temporary working files (auto-cleanup)
```

### 🔧 Configuration

#### Templates
Edit `TEMPLATES` in `quran_reels/config.py` (background style + transition; text styling lives in `TEXT_STYLE_PROFILES`):

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'transition': 'fade', 'transition_style': 'cinematic'},
    'normal':  {'bg_style': 'nature', 'transition': 'fade', 'transition_style': 'cinematic'},
    'masjid':  {'bg_style': 'masjid', 'transition': 'fade', 'transition_style': 'cinematic'},
    'islamic': {'bg_style': 'islamic', 'transition': 'wipe', 'transition_style': 'cinematic'},
}

TEXT_STYLE_PROFILES = {
    'ramadan': {'accent': '#FFD98A', 'backing_opacity': 0.62},
    'normal':  {'accent': '#FFFFFF', 'backing_opacity': 0.58},
    ...
}
TEXT_POSITIONS = ("lower", "middle")  # TEXT_POSITION_DEFAULT = "lower"
```

#### Quality Presets
```python
QUALITY_PRESETS = {
    'low':    {'fps': 24, 'preset': 'ultrafast', 'bitrate': '4M'},
    'medium': {'fps': 30, 'preset': 'fast', 'bitrate': '8M'},
    'high':   {'fps': 30, 'preset': 'fast', 'bitrate': '12M'}
}
```

#### Transitions
Segment transitions come from `VIDEO_TRANSITIONS` in `quran_reels/config.py`
(`fade`, `dissolve`, `wipe`, `slide`, `cross_zoom`, `pixelate`); the UI's
transition-style select (`cinematic`, `dynamic`, `smooth`, `cut`) controls how
they are applied between ayahs.
```python
VIDEO_TRANSITIONS = {
    'fade': {'type': 'fade', 'duration': 0.5},
    'dissolve': {'type': 'dissolve', 'duration': 0.5},
}
```

### 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| FFmpeg not found | Ensure `ffmpeg`/`ffprobe` are on PATH (`QURAN_FFMPEG_EXE` in `.env.example` is not wired — see AGENTS.md) |
| Arabic text not showing | Confirm RAQM support: `python -c "from PIL import features; print(features.check('raqm'))"` must print `True`; bundled font is `assets/fonts/ScheherazadeNew-Regular.ttf` |
| Audio download fails | Check internet connection; verify reciter ID exists at everyayah.com |
| Video generation slow | Use 'low' quality; process fewer ayahs; close other applications |
| Out of memory errors | Reduce quality; process in smaller batches; increase RAM |
| Corrupted cache files | Files are auto-detected and removed; restart generation |

### 📚 Documentation

- **Contributor notes**: See [AGENTS.md](AGENTS.md) for commands, config, and known traps
- **Feature spec**: See [specs/002-ayah-text-sync/](specs/002-ayah-text-sync/) for the text-sync spec, tasks, and API contract
- **System architecture**: See [Quran Reels architecture](.archify/architecture-quran-reels-20261016-151521/quran-reels-architecture.html) (interactive diagram: UI → Flask → build worker → FFmpeg, text/audio/background services)
- **Architecture**: Flask + FFmpeg + Pillow/RAQM

### 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Commit with clear messages (`git commit -m 'Add amazing feature'`)
5. Push to branch (`git push origin feature/amazing-feature`)
6. Submit a pull request

### 📝 License

Apache 2.0 - See [LICENSE](LICENSE) file for details

### 🙏 Attribution

- **Quran Text**: [Quran.com API](https://quran.com)
- **Audio**: [EveryAyah.com](https://everyayah.com)
- **Fonts**: User-provided (ensure proper licensing)
- **Backgrounds**: User-provided (ensure proper licensing)

---

<a name="arabic"></a>

## 🇪🇬 العربية

أداة ذكية ومؤتمتة لإنشاء مقاطع فيديو احترافية (ريلز/قصيرة) للقرآن الكريم. تقوم بمزامنة التلاوات العطرة فوق خلفيات متحركة خلابة — مثالية لريلز إنستغرام وتيك توك وقصص يوتيوب — مع عرض نص الآية بالرسم العثماني أثناء تلاوتها.

### ✨ المميزات الرئيسية

#### 📖 مزامنة نص الآيات
- **عرض مصاحب للتلاوة**: كل مقطع يعرض النص الكامل للآية التي تُتلى، ويظهر/يختفي عند حدود المقاطع؛ خيار `show_text` (مفعّل افتراضياً)
- **تشكيل عربي صحيح**: عرض عبر Pillow + RAQM بالخط القرآني المرفق `assets/fonts/ScheherazadeNew-Regular.ttf`
- **وضوح دائم**: التفاف تلقائي محسوب، صندوق خلفية شفاف بتباين ≥4.5:1، وألوان مميزة لكل قالب
- **موضع النص**: أسفل الفيديو أو وسطه (`text_position`)
- **تظليل الكلمات** (تجريبي): إضاءة ذهبية تتنقل كلمةً كلمة مع التلاوة، وتعود للعرض العادي عند غياب التوقيتات

### ✨ المميزات الرئيسية

#### 🎥 إنتاج الفيديو
- **أتمتة كاملة**: جلب النصوص والتسجيلات تلقائياً من المصادر المتاحة
- **جودة عالية**: دقة 1080×1920 (9:16) مثالية للسوشيال ميديا
- **تنسيقات متعددة**: دعم ريلز وستوري وبوست
- **صوت ذكي**: إزالة الصمت تلقائياً للتزامن المثالي بين الآيات
- **معالجة سريعة**: استخدام تقنية FFmpeg للدمج اللحظي بدون فقدان الجودة
- **تنوع الخلفيات**: نظام دورة ذكي يمنع تكرار نفس الفيديو لكل آية

#### 🎙️ القراء المدعومون
12+ قارئ مشهور بجودات مختلفة:
- الشيخ عبدالباسط عبدالصمد (مرتل، مجود، 64/128كب/ث)
- الشيخ عبدالرحمن السديس
- الشيخ محمد صديق المنشاوي (مجود)
- الشيخ سعود الشريم
- الشيخ محمود خليل الحصري
- الشيخ محمود علي البنا
- الشيخ أحمد نعينع
- الشيخ علي جابر
- الشيخ محمد الطبلاوي
- الشيخ مصطفى إسماعيل

#### 🎨 التصميم والتخصيص
- **خلفيات منظمة**: مصنفة حسب النمط (طبيعة، إسلامي، مساجد، ليل) مع تدوير ذكي يمنع التكرار
- **قوالب جاهزة**: 4 أنماط احترافية (رمضان، افتراضي، مساجد، إسلامي) تتحكم بالخلفية والانتقالات وألوان النص
- **بحث سريع**: مربع بحث للعثور على السورة بسرعة
- **مشغّل معاينة**: تشغيل/إيقاف، سرعة 0.5–2×، ملء الشاشة، ومؤشر الوقت

#### ⚙️ إعدادات متقدمة
- **اختيار الآيات**: تحقق ذكي يمنع الاختيارات غير الصالحة
- **مستويات الجودة**: منخفضة (سريع)، متوسطة، عالية (أفضل جودة)
- **تتبع التقدم**: سجلات لحظية ونسبة إنجاز
- **واجهة حديثة**: تصميم زجاجي (Glassmorphism) بمظهر متميز ووضع داكن
- **حركات**: تأثيرات حركة سلسة للنص والانتقالات بين المقاطع

### 🚀 البدء السريع

#### المتطلبات الأساسية
- بايثون 3.11 أو أعلى
- ويندوز 10/11 أو لينكس/ماك
- 4 جيجابايت رام (8 جيجابايت مستحسنة للفيديو 1080p)
- 2 جيجابايت مساحة فارغة

#### التثبيت

```bash
# استنساخ المستودع
git clone <repository-url>
cd Quran-Reels-Generator

# إنشاء بيئة افتراضية
python -m venv .venv

# تفعيل (ويندوز)
.venv\Scripts\activate

# تفعيل (لينكس/ماك)
source .venv/bin/activate

# تثبيت المتطلبات
pip install -r requirements.txt

# إضافة خلفياتك (اختياري لكن مستحسن)
copy *.mp4 vision/nature/

# تشغيل الخادم
python main.py

# فتح المتصفح على http://localhost:5000
```

#### طريقة الاستخدام

1. **إضافة خلفيات**: ضع ملفات .mp4 في مجلدات `vision/` (nature، islamic، masjid، night)
2. **تشغيل الخادم**: نفذ `python main.py` وانتظر التهيئة
3. **فتح الواجهة**: زر `http://localhost:5000` في المتصفح
4. **إنشاء فيديو**:
   - اختر القارئ من القائمة
   - ابحث واختر السورة (استخدم مربع البحث)
   - حدد أرقام آيات البداية والنهاية
   - اختر الجودة والقالب
   - أضف اسمك اختيارياً
   - فعّل البسملة وخيار إظهار النص (واختر موضع النص)
   - اضغط "معاينة" لفحص سريع أو "إنشاء الفيديو"

### 📁 هيكل المشروع

```
Quran-Reels-Generator/
├── main.py              # خادم الواجهة الخلفية ومحرك معالجة الفيديو
├── UI.html              # واجهة الويب (تطبيق صفحة واحدة)
├── main.js              # منطق الواجهة الأمامية وطلبات API ومشغّل المعاينة
├── style.css            # التنسيقات الزجاجية وأنماط المشغّل
├── quran_reels/         # حزمة الواجهة الخلفية (الإعدادات + الخدمات)
│   ├── config.py        # القوالب والجودات والقراء وثوابت النص
│   └── services/        # الصوت، الخلفيات، عرض النص العربي
├── assets/fonts/        # الخط القرآني المرفق (Scheherazade New)
├── specs/               # مواصفات الميزات وعقود API
├── .archify/            # مخطط معمارية النظام (HTML تفاعلي)
├── vision/              # مكتبة خلفيات الفيديو
│   ├── nature/          # فيديوهات المناظر الطبيعية
│   ├── islamic/         # فيديوهات الفنون الإسلامية
│   ├── masjid/          # فيديوهات المساجد والصلاة
│   └── night/           # فيديوهات الأجواء الليلية
├── outputs/             # المحتوى المُنتج
│   └── video/           # الفيديوهات النهائية
├── cache/               # تخزين الصوت والخلفيات
└── temp/                # ملفات العمل المؤقتة (تنظيف تلقائي)
```

### 🔧 الإعدادات

#### القوالب
عدل `TEMPLATES` في `quran_reels/config.py` (الخلفية والانتقال؛ تنسيق النص في `TEXT_STYLE_PROFILES`):

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'transition': 'fade', 'transition_style': 'cinematic'},
    'normal':  {'bg_style': 'nature', 'transition': 'fade', 'transition_style': 'cinematic'},
    'masjid':  {'bg_style': 'masjid', 'transition': 'fade', 'transition_style': 'cinematic'},
    'islamic': {'bg_style': 'islamic', 'transition': 'wipe', 'transition_style': 'cinematic'}
}
```

#### مستويات الجودة
```python
QUALITY_PRESETS = {
    'low':    {'fps': 24, 'preset': 'ultrafast', 'bitrate': '4M'},
    'medium': {'fps': 30, 'preset': 'fast', 'bitrate': '8M'},
    'high':   {'fps': 30, 'preset': 'fast', 'bitrate': '12M'}
}
```

#### الحركات والانتقالات
انتقالات المقاطع من `VIDEO_TRANSITIONS` في `quran_reels/config.py`
(`fade`، `dissolve`، `wipe`، `slide`، `cross_zoom`، `pixelate`)؛ وقائمة أسلوب
الانتقال في الواجهة (`cinematic`، `dynamic`، `smooth`، `cut`) تتحكم في تطبيقها.
```python
VIDEO_TRANSITIONS = {
    'fade': {'type': 'fade', 'duration': 0.5},
    'dissolve': {'type': 'dissolve', 'duration': 0.5},
}
```

### 🛠️ حل المشكلات

| المشكلة | الحل |
|---------|------|
| FFmpeg غير موجود | تأكد أن `ffmpeg`/`ffprobe` على PATH النظام |
| النص العربي لا يظهر | تحقق من دعم RAQM عبر `python -c "from PIL import features; print(features.check('raqm'))"` (يجب أن يطبع `True`) |
| فشل تحميل الصوت | تأكد من اتصال الإنترنت؛ تحقق من معرف القارئ في everyayah.com |
| بطء إنشاء الفيديو | استخدم جودة 'منخفضة'؛ عالج آيات أقل؛ أغلق التطبيقات الأخرى |
| أخطاء نفاد الذاكرة | قلل الجودة؛ عالج على دفعات أصغر؛ زِد الرام |
| ملفات cache معطوبة | يتم اكتشافها وإزالتها تلقائياً؛ أعد التشغيل |

### 📚 التوثيق

- **ملاحظات المساهمين**: راجع [AGENTS.md](AGENTS.md) للأوامر والإعدادات والتنبيهات
- **مواصفة الميزة**: راجع [specs/002-ayah-text-sync/](specs/002-ayah-text-sync/) للمواصفة والمهام وعقد API
- **معمارية النظام**: راجع [مخطط المعمارية](.archify/architecture-quran-reels-20261016-151521/quran-reels-architecture.html) (مخطط تفاعلي)
- **البنية**: Flask + FFmpeg + Pillow/RAQM

### 🤝 المساهمة

1. انسخ المستودع
2. أنشئ فرعاً للميزة (`git checkout -b feature/amazing-feature`)
3. قم بتغييراتك
4. ارتكب برسائل واضحة (`git commit -m 'Add amazing feature'`)
5. ادفع للفرع (`git push origin feature/amazing-feature`)
6. أرسل طلب دمج

### 📝 الترخيص

Apache 2.0 - راجع ملف [LICENSE](LICENSE) للتفاصيل

### 🙏 الإسناد

- **نص القرآن**: [Quran.com API](https://quran.com)
- **الصوت**: [EveryAyah.com](https://everyayah.com)
- **الخطوط**: يوفرها المستخدم (تأكد من الترخيص)
- **الخلفيات**: يوفرها المستخدم (تأكد من الترخيص)

---

<p align="center">
  صدقة جارية | Continuous Charity | Made with ❤️ for the Ummah
</p>

