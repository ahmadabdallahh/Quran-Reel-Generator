# 🚀 Future Feature Roadmap

**Vision**: The Quran Reels Generator now focuses on delivering **professional audio-visual Quran content** without Arabic text overlays. This roadmap outlines the next enhancements to improve video quality, stability, and workflow.

---

## 📋 Priority Matrix

| Priority | Features | Implemented | Overdue Effort |
|----------|----------|-------------|-----------------
| **P0**   | Ayah number watermark; Audio crossfades | ✅ Implemented | |
| **P1**   | Smart Background pool; Surah cards | ⏳ Pending | |
| **P2**   | WebSocket progress; Job queue | ⏳ Pending | |

---

## 🔥 P0 Features (High Impact, Low Effort)

### 1. Ayah Number Watermark ✅ IMPLEMENTED

**What:** Small, semi-transparent sticker displaying "Surah Name [ayah:verse]" (e.g., "Al-Baqarah 2:152") in a corner.

**Why:** Immediate context for viewers; eliminates need to guess which ayah is playing.

**Implementation:**
- **Toolset:** ffmpeg `drawtext` filter
- **Font:** Latin font (e.g., Liberation Sans)
- **Style:** Semi-transparent black box, white text, rounded corners
- **Location:** Bottom-left or top-right corner
- **Effort:** 2 hours (completed)

**Example Filter Expression:**
```ffmpeg
[0:v]drawtext=text='Al-Baqarah 2:152':fontfile=LiberationSans-Regular.ttf:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.7:x=20:y=20
```

---

### 2. Audio Crossfade Between Segments 🔄 IN PROGRESS

**What:** Smooth volume fade between ayah segments instead of abrupt cuts.

**Why:** Audio quality is the primary source of user complaints; crossfade creates professional finish.

**Technical Approach:**
- Use ffmpeg `acrossfade` filter: `afade=type=start:st=0:d=0.2,afade=type=begin:st=0:d=0.2`
- Configurable fade duration (default: 0.2s)
- Applied between all segments except last
- Seamless with existing Bismillah title card

**Effort:** 3 hours  
**Compatibility:** Backwards compatible with current rendering pipeline

---

## 🎯 P1 Features (Medium Impact, Medium Effort)

### 3. Dynamic Background Video Pool

**What:** Curated, high-quality backgrounds from Pexels API; style-specific automatic rotation.

**Why:** Limited local library lacks variety; external API provides thousands of 9:16 vertical videos.

**Implementation Details:**
- **Integration:** Pexels API with caching (rate-limit aware)
- **Styles:** nature, islamic, masjid, night
- **Filters:** Auto-respects aspect ratio (9:16) and minimum resolution (720p)
- **Fallback:** Offline mode if API unavailable
- **API Cost:** ~\$0.001 per request ($10/month estimated for 10k requests)

**Effort:** 4–6 hours  
**Risk:** Moderate (network dependency)

---

### 4. Surah Intro / Outro Cards

**What:** Enhanced Bismillah with centered surah name + ayah range + smooth zoom animation.

**Why:** Better visual narrative; polished lead-in to first ayah.

**Implementation:**
- Build on existing `_build_bismillah_segment()` 
- Add centered text layer using Pillow + ffmpeg overlay
- Smooth 0.5s zoom-in animation
- Toggle via UI checkbox (default: enabled)

**Effort:** 2–4 hours  
**Visual Impact:** High

---

## ⚡ P2 Features (Lower Impact, Higher Effort)

### 5. WebSocket Real‑time Progress

**What:** Replace HTTP polling (`/api/progress`) with Socket.IO for instant UI updates.

**Why:** Better UX; reduces server load; enables more advanced interactive UI.

**Migration Path:**
- Add Socket.IO to existing Flask server
- Emit progress events from worker threads
- Maintain backward compatibility (polling still works)
- Auto-reconnect handling for dropouts

**Effort:** 6–12 hours  
**User Experience:** Significant improvement

---

### 6. Persistent Job Queue

**What:** Survive server restarts; queue multiple generation requests; manage parallel builds.

**Why:** Production reliability; batch processing support; better resource utilization.

**Implementation Options:**
- **Redis:** Fast, robust, supported in Docker
- **SQLite:** Simpler, file-based (suitable for small deployments)
- **Local filesystem:** Custom job store (lightweight)

**Features:**
- Job status tracking (queued, running, completed, failed)
- HTTP admin endpoints for job management
- Retry logic for transient failures

**Effort:** 6–10 hours  
**Production Readiness:** High

---

## 📊 Implementation Timeline & Resource Planning

### Week 1: Quick Wins (P0 Features)

**Day 1–2:** Ayah number watermark
- [ ] Parse ayah numbers from args
- [ ] Integrate `drawtext` filter in `build_segment_ffmpeg`
- [ ] Test with single ayah segment
- [ ] Optimize styling (font size, position, opacity)

**Day 3–4:** Audio crossfade
- [ ] Implement `acrossfade` filter in segment builder
- [ ] Configure fade duration (configurable via env)
- [ ] Test crossfade between multiple segments
- [ ] Validate with existing Bismillah segment

### Week 2: Foundation Upgrades (P1 Features)

**Day 5–7:** Dynamic Background Pool
- [ ] Set up Pexels API client (with caching)
- [ ] Implement automatic background selection per style
- [ ] Add fallback handling for API failures
- [ ] Update `BackgroundRotator` to use new pool

**Day 8–10:** Surah Cards Enhancement
- [ ] Extend `_build_bismillah_segment` with title text
- [ ] Add smooth zoom animation
- [ ] Implement toggle in UI/API
- [ ] Test style consistency

### Week 3: Advanced Features (P2 Features)

**Day 11–14:** WebSocket Progress
- [ ] Add Socket.IO to Flask app
- [ ] Emit progress events from build threads
- [ ] Update UI to use Socket.IO instead of polling
- [ ] Maintain backward compatibility

**Day 15–18:** Job Queue
- [ ] Choose storage solution (Redis recommended)
- [ ] Implement job CRUD operations
- [ ] Add REST endpoints for job management
- [ ] Test persistence across server restarts

---

## 📝 Testing & Validation

### Unit Tests

- **Watermark filter:** Verify correct overlay placement and styling
- **Crossfade:** Validate fade duration and transition smoothness
- **Background API:** Mock failures and test fallback behavior
- **WebSocket:** Test real-time progress updates

### Integration Tests

- **End-to-end:** Complete video generation from ayah selection to final file
- **Ayah range:** Multiple consecutive ayahs with watermark consistency
- **Bismillah + watermark:** Title card with ayah watermarks in sequence
- **Recovery:** Test resume after unexpected server restart

### User Acceptance Criteria

1. **Ayah watermark:** Always visible, readable, positioned in corner, auto-sized
2. **Audio crossfade:** No abrupt cuts, natural transition, fades don't affect video
3. **Background variety:** No repetition within single session, style-appropriate
4. **Surah cards:** Smooth animation, proper text formatting, optional toggle
5. **Progress updates:** Real-time UI updates < 2 seconds latency

---

## 🎯 Recommended Deployment Strategy

### Phase 1: P0 Features (MVP)

1. **Release immediately** with Ayah watermark and audio crossfade
2. **Collect user feedback** within first week
3. **Monitor performance** and stability
4. **Decide on P1** based on user demand

### Phase 2: P1 Features (Value Add)

1. **Deploy Dynamic Background Pool** (after P0 stability confirmed)
2. **Implement Surah Cards** as optional enhancement
3. **A/B test** different watermark styles
4. **Gather analytics** on feature usage

### Phase 3: P2 Features (Enterprise Features)

1. **WebSocket progress** for power users
2. **Job queue** for batch processing
3. **Save settings** feature (user preferences)
4. **API rate limiting** and monitoring

---

## 🔄 Ongoing Maintenance

### Post-Launch Monitoring

- **Logs:** Track build success/failure rates
- **Metrics:** Video generation time, CPU/memory usage
- **Errors:** Monitor ffmpeg crashes and API failures
- **User feedback:** In-app feedback widget

### Adaptive Enhancements

- **Style updates:** Periodic UI/UX improvements
- **Performance tuning:** Optimize ffmpeg commands
- **Bug fixes:** Monthly security patches
- **Feature additions:** Quarterly roadmap review

---

## 📚 References

- **ffmpeg Documentation:** [Official Manual](https://ffmpeg.org/documentation.html)
- **Pexels API:** [Developer Portal](https://www.pexels.com/api/)
- **Flask + Socket.IO:** [Real-time Communication Guide](https://flask-socketio.readthedocs.io/)
- **Arabization Standards:** [Unicode Quranic Text Guidelines](https://www.unicode.org/reports/tr9/)

---

## 🔄 Next Steps

1. **Implement P0** (ayah watermark + audio crossfade) — 48 hours total
2. **Validate** with existing test suite
3. **Deploy to staging** for beta testing
4. **Collect feedback** and prioritize next features

---

*Document last updated: 2026-06-27*
*Version: 1.0*