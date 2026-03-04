# 📖 Quran Reels Generator | أداة عمل ريلز القرآن الكريم

[English](#english) | [العربية](#arabic)

---

<a name="arabic"></a>
## 🇪🇬 اللغة العربية

أداة ذكية ومؤتمتة تتيح لك إنشاء مقاطع فيديو قصيرة (Reels/Shorts) للقرآن الكريم بجودة عالية وبضغطة زر واحدة. تقوم الأداة بدمج التلاوة العطرة مع النص القرآني بالرسم العثماني فوق خلفيات طبيعية أو إسلامية خلابة.

### 🚀 المميزات الرئيسية

#### 🎥 **إنتاج الفيديو**
- **أتمتة كاملة:** جلب النصوص والتسجيلات الصوتية تلقائياً من الإنترنت.
- **جودة عالية:** دعم إنتاج فيديو بدقة 1080×1920 (9:16) مثالي للسوشيال ميديا.
- **تنسيقات متعددة:** دعم مختلف صيغ الإخراج (Reels، Story، Post).
- **معالجة ذكية:** قص الصمت تلقائياً من بداية ونهاية كل آية للتزامن المثالي.
- **دمج فائق السرعة:** استخدام تقنية Stream Copy للدمج اللحظي للمقاطع دون فقدان الجودة.

#### 🎙️ **القراء المتاحون**
دعم لمجموعة من مشاهير العالم الإسلامي (يتم تحديثهم ديناميكياً):
- **الشيخ عبدالباسط عبدالصمد** (مجود، مرتل، جودات مختلفة)
- **الشيخ عبدالرحمن السديس**
- **الشيخ محمد صديق المنشاوي** (مجود)
- **الشيخ محمود علي البنا**
- **الشيخ أحمد نعينع**
- **الشيخ مصطفى إسماعيل**
- **الشيخ محمد الطبلاوي**
- **الشيخ علي جابر**
- **الشيخ محمود خليل الحصري**
- **الشيخ سعود الشريم**

#### 🎨 **الخطوط والتصميم**
- **إدارة ديناميكية للخطوط:** دعم تلقائي لجميع خطوط (.ttf و .otf) في مجلد `fonts`.
- **اختيار الخط:** قائمة منسدلة محدثة تظهر الخطوط المتاحة.
- **تحديث يدوي:** زر لتحديث قائمة الخطوط فوراً عند إضافة ملفات جديدة.
- **إدخال مرن:** إمكانية اختيار الخط من القائمة أو استخدامه بشكل عشوائي.
- **خلفيات متطورة:** نظام ذكي لمسح مجلد `vision` دورياً لالتقاط الخلفيات الجديدة فور إضافتها.
- **قوالب مرئية احترافية:** 5 قوالب جاهزة (Ramadan، Normal، Kids، Masjid، Islamic).

#### ⚙️ **إعدادات متقدمة**
- **تحديد دقيق للآيات:** نظام ذكي يمنع اختيار آيات خارج نطاق السورة مع مزامنة طرفي البداية والنهاية.
- **تحكم كامل:** إمكانية كتابة أرقام الآيات يدوياً أو استخدام أزرار التحكم.
- **مستويات جودة:** (Low، Medium، High) مع ضبط تلقائي لمعدل البت والإطارات.

#### 🌐 **الواجهة والاستخدام**
- **واجهة ويب حديثة:** تصميم جذاب بلمسة "Glassmorphism" بتقنية HTML5/CSS3.
- **معاينة مباشرة:** مشغل فيديو مدمج لمشاهدة النتيجة فور انتهاء الرندر.
- **تتبع التقدم:** شريط تقدم وسجل عمليات (Logs) حي يعرض كل تفاصيل المعالجة.

### 🏗️ **هيكل المشروع**

```
Quran-Reels-Generator/
├── main.py                 # الخادم الرئيسي (Flask) ومنطق المعالجة
├── UI.html                 # واجهة المستخدم الحديثة
├── main.js                 # منطق التفاعل في الواجهة
├── requirements.txt        # المكتبات المطلوبة
├── fonts/                 # مجلد الخطوط العربية
├── vision/                # مكتبة الخلفيات الفيديو (ضع فيديوهاتك هنا)
├── bin/                   # المحركات (FFmpeg)
└── outputs/               # الفيديوهات النهائية والمؤقتة
```

---

<a name="english"></a>
## 🌍 English Version

An automated AI tool to create professional Quranic Reels/Shorts. It syncs Quranic text (Uthmani script) with recitations over beautiful backgrounds.

### 🚀 Key Features
- **Fast Concatenation:** Uses FFmpeg stream copy for instant segment merging.
- **Dynamic Reciters:** Dynamic list supporting top reciters like AbdulBasit, Al-Tablawi, and more.
- **Pro Templates:** Choose from 5 themes (Normal, Ramadan, Kids, Masjid, Islamic).
- **Smart Validation:** Prevents invalid ayah selection based on the specific Surah.
- **Dynamic Assets:** Real-time scanning for new background videos placed in the `vision` folder.
- **Manual Font Control:** Easily refresh and select custom fonts from the `fonts` directory.

### 🛠️ Installation & Usage
1. Install requirements: `pip install -r requirements.txt`
2. Run server: `python main.py`
3. Open `http://localhost:5000` (Manual open).
4. Drop your `.mp4` backgrounds in `vision` and `.ttf` fonts in `fonts`.

### 📋 Dependencies
- **Flask & CORS**
- **FFmpeg** (Core Processing)
- **Pillow & Arabic Reshaper** (Text Rendering)
- **Pydub** (Audio Processing)
