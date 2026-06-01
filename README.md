# 📖 Quran Reels Generator | أداة عمل ريلز القرآن الكريم

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FFmpeg-6.0+-green.svg" alt="FFmpeg 6.0+">
  <img src="https://img.shields.io/badge/Flask-2.3+-orange.svg" alt="Flask 2.3+">
  <img src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg" alt="License">
</p>

<p align="center">
  <strong>English</strong> | <a href="#arabic">العربية</a>
</p>

---

## 🌍 English

An automated AI-powered tool to create professional Quranic Reels/Shorts video content. It synchronizes Quranic text (Uthmani script) with high-quality recitations over beautiful animated backgrounds—perfect for Instagram Reels, TikTok, and YouTube Shorts.

### ✨ Key Features

#### 🎥 Video Production
- **Full Automation**: Automatically fetches Quranic text and audio recitations from online sources
- **High Quality**: 1080×1920 (9:16) vertical format optimized for social media platforms
- **Multiple Formats**: Reels, Story, and Post formats supported
- **Smart Audio**: Automatic silence trimming for perfect synchronization between ayahs
- **Fast Processing**: FFmpeg stream copy for instant segment merging without quality loss
- **Background Variety**: Smart rotation system prevents repeating the same video per ayah

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
- **Dynamic Fonts**: Auto-detection of all .ttf/.otf fonts in `fonts/` folder with caching
- **Smart Backgrounds**: Organized by style (Nature, Islamic, Masjid, Night)
- **Visual Templates**: 4 professional themes (Ramadan, Normal, Masjid, Islamic)
- **Arabic Text Rendering**: Proper tashkeel and RTL support using arabic-reshaper
- **Text Search**: Quick surah finder with real-time filtering
- **Dynamic Text Color**: Auto-adjusts based on background brightness for readability

#### ⚙️ Advanced Settings
- **Ayah Selection**: Smart validation prevents invalid selections
- **Quality Levels**: Low (fast), Medium, High (slow/best quality)
- **Progress Tracking**: Real-time logs and percentage completion
- **Modern UI**: Glassmorphism design with premium aesthetics and dark theme
- **Animations**: Smooth text animations and video transitions

### 🚀 Quick Start

#### Prerequisites
- Python 3.11 or higher
- Windows 10/11 or Linux/macOS
- 4GB+ RAM (8GB recommended for 1080p)
- 2GB free disk space

#### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Quran-Reels-Generator

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Add your backgrounds (optional but recommended)
copy *.mp4 vision/nature/

# Run the server
python main.py

# Open browser at http://localhost:5000
```

#### Usage

1. **Add Backgrounds**: Place .mp4 files in `vision/` subdirectories (nature, islamic, masjid, night)
2. **Add Fonts** (Optional): Place .ttf/.otf Arabic fonts in `fonts/` folder
3. **Run Server**: Execute `python main.py` and wait for initialization
4. **Open UI**: Visit `http://localhost:5000` in your browser
5. **Create Video**:
   - Select reciter from dropdown
   - Search and select Surah (use the search box)
   - Set start and end ayah numbers
   - Choose quality and template
   - Optionally add your name
   - Click "Generate Video"

### 📁 Project Structure

```
Quran-Reels-Generator/
├── main.py              # Backend server & video processing engine
├── UI.html              # Web interface (single-page application)
├── main.js              # Frontend logic and API calls
├── requirements.txt     # Python dependencies
├── skills.md            # Technical documentation and API reference
├── LICENSE              # Apache 2.0 License
├── fonts/               # Arabic font files (.ttf, .otf)
│   └── _cache/          # Font cache for compatibility
├── vision/              # Background video library
│   ├── nature/          # Nature scenery videos
│   ├── islamic/         # Islamic art/pattern videos
│   ├── masjid/          # Mosque/prayer videos
│   └── night/           # Night/evening ambience videos
├── outputs/             # Generated content
│   ├── video/           # Final rendered videos
│   └── bg_cache/        # Pre-processed background cache
├── temp/                # Temporary working files (auto-cleanup)
└── bin/                 # Binary executables
    └── ffmpeg/          # FFmpeg and FFprobe
```

### 🔧 Configuration

#### Templates
Edit `TEMPLATES` in `main.py`:

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'text_color': 'gold', 'font_size_mult': 1.2},
    'normal':  {'bg_style': 'nature', 'text_color': 'white', 'font_size_mult': 1.0},
    'masjid':  {'bg_style': 'masjid', 'text_color': 'white', 'font_size_mult': 1.1},
    'islamic': {'bg_style': 'islamic', 'text_color': 'white', 'font_size_mult': 1.1}
}
```

#### Quality Presets
```python
QUALITY_PRESETS = {
    'low':    {'fps': 24, 'preset': 'ultrafast', 'bitrate': '4M'},
    'medium': {'fps': 30, 'preset': 'fast', 'bitrate': '8M'},
    'high':   {'fps': 30, 'preset': 'fast', 'bitrate': '12M'}
}
```

#### Animations & Transitions
```python
TEXT_ANIMATIONS = {
    'fade_in': {'type': 'fade', 'duration': 0.5},
    'slide_up': {'type': 'slide', 'duration': 0.5, 'direction': 'up'},
    'typewriter': {'type': 'typewriter', 'duration': 0.03},
}

VIDEO_TRANSITIONS = {
    'fade': {'type': 'fade', 'duration': 0.5},
    'dissolve': {'type': 'dissolve', 'duration': 0.5},
}
```

### 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| FFmpeg not found | Ensure `bin/ffmpeg/ffmpeg.exe` exists or add FFmpeg to system PATH |
| Arabic text not showing | Add Arabic fonts to `fonts/` folder and restart server |
| Audio download fails | Check internet connection; verify reciter ID exists at everyayah.com |
| Video generation slow | Use 'low' quality; process fewer ayahs; close other applications |
| Out of memory errors | Reduce quality; process in smaller batches; increase RAM |
| Corrupted cache files | Files are auto-detected and removed; restart generation |

### 📚 Documentation

- **Technical Details**: See [skills.md](skills.md) for complete architecture
- **API Reference**: Documented in skills.md
- **Architecture**: Flask + FFmpeg + PIL + Arabic Reshaper

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

أداة ذكية ومؤتمتة لإنشاء مقاطع فيديو احترافية (ريلز/قصيرة) للقرآن الكريم. تقوم بمزامنة النص القرآني بالرسم العثماني مع التلاوات العطرة فوق خلفيات متحركة خلابة—مثالية لريلز إنستغرام وتيك توك وقصص يوتيوب.

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
- **خطوط ديناميكية**: اكتشاف تلقائي لجميع الخطوط في مجلد `fonts/` مع تخزين مؤقت
- **خلفيات منظمة**: مصنفة حسب النمط (طبيعة، إسلامي، مساجد، ليل)
- **قوالب جاهزة**: 4 أنماط احترافية (رمضان، افتراضي، مساجد، إسلامي)
- **عرض عربي**: دعم التشكيل والكتابة من اليمين لليسار
- **بحث سريع**: مربع بحث للعثور على السورة بسرعة
- **لون نص ديناميكي**: يتكيف تلقائياً مع سطوع الخلفية

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
2. **إضافة خطوط** (اختياري): ضع ملفات .ttf/.otf عربية في مجلد `fonts/`
3. **تشغيل الخادم**: نفذ `python main.py` وانتظر التهيئة
4. **فتح الواجهة**: زر `http://localhost:5000` في المتصفح
5. **إنشاء فيديو**:
   - اختر القارئ من القائمة
   - ابحث واختر السورة (استخدم مربع البحث)
   - حدد أرقام آيات البداية والنهاية
   - اختر الجودة والقالب
   - أضف اسمك اختيارياً
   - اضغط "إنشاء الفيديو"

### 📁 هيكل المشروع

```
Quran-Reels-Generator/
├── main.py              # خادم الواجهة الخلفية ومحرك معالجة الفيديو
├── UI.html              # واجهة الويب (تطبيق صفحة واحدة)
├── main.js              # منطق الواجهة الأمامية وطلبات API
├── requirements.txt     # تبعيات بايثون
├── skills.md            # التوثيق الفني ومرجع API
├── LICENSE              # ترخيص Apache 2.0
├── fonts/               # ملفات الخطوط العربية (.ttf, .otf)
│   └── _cache/          # تخزين الخطوط للتوافقية
├── vision/              # مكتبة خلفيات الفيديو
│   ├── nature/          # فيديوهات المناظر الطبيعية
│   ├── islamic/         # فيديوهات الفنون الإسلامية
│   ├── masjid/          # فيديوهات المساجد والصلاة
│   └── night/           # فيديوهات الأجواء الليلية
├── outputs/             # المحتوى المُنتج
│   ├── video/           # الفيديوهات النهائية
│   └── bg_cache/        # تخزين الخلفيات المعالجة مسبقاً
├── temp/                # ملفات العمل المؤقتة (تنظيف تلقائي)
└── bin/                 # الملفات التنفيذية
    └── ffmpeg/          # FFmpeg و FFprobe
```

### 🔧 الإعدادات

#### القوالب
عدل `TEMPLATES` في `main.py`:

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'text_color': 'gold', 'font_size_mult': 1.2},
    'normal':  {'bg_style': 'nature', 'text_color': 'white', 'font_size_mult': 1.0},
    'masjid':  {'bg_style': 'masjid', 'text_color': 'white', 'font_size_mult': 1.1},
    'islamic': {'bg_style': 'islamic', 'text_color': 'white', 'font_size_mult': 1.1}
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
```python
TEXT_ANIMATIONS = {
    'fade_in': {'type': 'fade', 'duration': 0.5},
    'slide_up': {'type': 'slide', 'duration': 0.5, 'direction': 'up'},
    'typewriter': {'type': 'typewriter', 'duration': 0.03},
}

VIDEO_TRANSITIONS = {
    'fade': {'type': 'fade', 'duration': 0.5},
    'dissolve': {'type': 'dissolve', 'duration': 0.5},
}
```

### 🛠️ حل المشكلات

| المشكلة | الحل |
|---------|------|
| FFmpeg غير موجود | تأكد من وجود `bin/ffmpeg/ffmpeg.exe` أو أضف FFmpeg لـ PATH النظام |
| النص العربي لا يظهر | أضف خطوط عربية لمجلد `fonts/` وأعد تشغيل الخادم |
| فشل تحميل الصوت | تأكد من اتصال الإنترنت؛ تحقق من معرف القارئ في everyayah.com |
| بطء إنشاء الفيديو | استخدم جودة 'منخفضة'؛ عالج آيات أقل؛ أغلق التطبيقات الأخرى |
| أخطاء نفاد الذاكرة | قلل الجودة؛ عالج على دفعات أصغر؛ زِد الرام |
| ملفات cache معطوبة | يتم اكتشافها وإزالتها تلقائياً؛ أعد التشغيل |

### 📚 التوثيق

- **التفاصيل الفنية**: راجع [skills.md](skills.md) للبنية الكاملة
- **مرجع API**: موثق في skills.md
- **البنية**: Flask + FFmpeg + PIL + Arabic Reshaper

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

