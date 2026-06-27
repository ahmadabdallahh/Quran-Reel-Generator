# 🚀 Future Feature Roadmap

## Vision

The Quran Reels Generator now focuses on **audio + background video** production. The text-on-video rendering feature has been removed to deliver a cleaner, more reliable app.

This roadmap outlines the next set of enhancements to improve video quality and viewer experience.

---

## 📋 Priority Matrix

| Priority | Features | Rationale |
|----------|----------|----------|
| **P0**   | Ayah number sticker; Audio crossfades | Cheap to build, high viewer value |
| **P0**   | SRT subtitles (optional translations) | Unlocks international users |
| **P1**   | Background pool upgrades; Surah cards | Visible quality jump |
| **P2**   | WebSocket progress; Video preview | Polished UX for power users |
| **P2**   | Job queue; Graceful shutdown | Production stability |

---

## 🔥 P0 Features (High Impact, Low Effort)

### 1. Ayah Number Watermark

**What:** Small sticker (surah name + ayah number) in a corner using ffmpeg `drawtext`.

**Why:** Viewer can immediately know which ayah is playing without extra mental load.

**Implementation:**
- Pre-render text with a Latin font (no Arabic shaping needed)
- Use ffmpeg `drawtext` filter during segment muxing
- Configurable position, size, opacity

**Effort:** 1–2 hours
**Tools:** ffmpeg filter expressions

---

### 2. Audio Crossfade Between Segments

**What:** Replace abrupt audio cuts with smooth crossfade transitions using ffmpeg `afade` or `acrossfade`.

**Why:** Audio quality is the primary complaint; crossfade makes the experience more professional.

**Implementation:**
- Detect segment boundaries (1.8s Bismillah, ayah ends)
- Insert `acrossfade` filter for N-second fade between segments
- Configurable fade duration (default 0.2s)

**Effort:** 2–3 hours
**Tools:** ffmpeg filters (`acrossfade`)

---

## 🎯 P1 Features (Medium Impact, Medium Effort)

### 3. Smart Background Video Pool

**What:** Curated, high-quality backgrounds from Pexels/Pixabay API; style-specific playlists.

**Why:** Current local library is limited; external API gives access to thousands of 9:16 vertical videos.

**Implementation:**
- Integrate Pexels API with caching (limit rate, avoid free tier issues)
- Style-based categorization: nature, islamic, masjid, night
- Auto-filter by aspect ratio (9:16) and minimum resolution
- Local fallback if API fails

**Effort:** 4–6 hours
**Tools:** API client, image caching logic

---

### 4. Surah Intro / Outro Cards

**What:** Enhanced Bismillah with centered surah name + ayah range + zoom animation.

**Why:** More structured lead-in helps with narrative flow.

**Implementation:**
- Reuse `_build_bismillah_segment` but add centered title text
- Optional background music snippet
- Smooth 0.5s zoom-in animation
- Can be toggled on/off via UI

**Effort:** 2–4 hours
**Tools:** Pillow text rendering, ffmpeg animation filters

---

## ⚡ P2 Features (Lower Impact, Higher Effort)

### 5. WebSocket Real‑time Progress

**What:** Replace polling `/api/progress` with Socket.IO for instant updates.

**Why:** Better UX, reduces server load, enables more advanced UI features.

**Implementation:**
- Add Socket.IO to Flask
- Emit progress events from build threads
- Auto-reconnect handling
- Replace polling UI component

**Effort:** 6–12 hours
**Tools:** Socket.IO, event handling

---

### 6. Persistent Job Queue

**What:** Survive server restarts; queue multiple generation requests.

**Why:** Supports batch processing; more reliable production usage.

**Implementation:**
- Redis or SQLite job storage
- Worker threads process queue
- HTTP endpoints to manage queue

**Effort:** 6–10 hours
**Tools:** Background workers, job storage

---

## 📊 Summary & Recommendations

### Quick Wins (Deploy First)

1. **Ayah number watermark** (2 hours)
2. **Audio crossfade** (3 hours)

### Foundation Upgrades

3. **Background pool** (6 hours) – optional extra funding for API usage
4. **Surah cards** (4 hours) – builds on top of Bismillah enhancement

### Future Enhancements

5. **WebSocket progress** (8 hours) – after core features stable
6. **Job queue** (10 hours) – for power users

---

## 📝 Notes

- All timestamps are **approximate** and based on a single developer.
- API costs for Pexels are ~\$0.001 per request; estimate $10/month for 10k requests.
- Time estimates assume familiarity with the codebase (2–4 hours per day of work).
- Any P1/P2 feature could be split into smaller tasks.

---

## 🔄 Next Steps

1. **Implement P0 features** (ayah watermark, audio crossfade)
2. **Test and gather feedback** from beta users
3. **Plan P1/P2 features** with resource estimates

The remaining roadmap positions the app for its next evolution: professional‑grade audio‑visual Quran content delivery.
