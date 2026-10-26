"""FFmpeg rendering primitives for Quran video segments.

This module owns segment composition and crossfade assembly. Runtime paths and
legacy application services are imported lazily inside the entry points to
preserve the existing ``main`` module API without import-time cycles.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

from quran_reels.config import (
    BISMILLAH_DURATION_SEC, QUALITY_PRESETS, SURAH_NAMES, TARGET_H, TARGET_W,
    should_show_bismillah_visual,
)
from quran_reels.services.audio import (
    download_audio, get_audio_duration_ffprobe, get_ayah_text,
)
from quran_reels.services.background import (
    get_next_background, get_preprocessed_bg,
)
from quran_reels.services.text_overlay import render_ayah_text_png
from quran_reels.utils.job import _job_local, current_job
from quran_reels.utils.progress import (
    OperationCancelled, add_log, run_cancellable, raise_if_cancelled,
)

HIGHLIGHT_MAX_LAYERS = 60


def _compute_xfade_pairs(transition_style, n, xfade_d):
    """Return which adjacent ayah clips receive an overlapping transition."""
    if n <= 1:
        return []
    if transition_style in ('cinematic', 'cut'):
        return [False] * (n - 1)
    if transition_style == 'smooth':
        every = max(1, n // 3)
        return [((i + 1) % every == 0) for i in range(n - 1)]
    # Crossfade, fade-through-black, and legacy dynamic all apply at every cut.
    return [True] * (n - 1)


def _split_into_chunks(is_xfade_pair):
    """Group consecutive segment indices into "chunks" separated by xfade
    boundaries.  Each chunk is a list of indices that should be hard-cut
    together (via the concat demuxer) before being xfaded with the next
    chunk.

    Example: is_xfade_pair = [F, T, F, T, F, T] for n=7 segments
             => chunks = [[0, 1], [2, 3], [4, 5], [6]]
    """
    n = len(is_xfade_pair) + 1
    chunks = []
    current = [0]
    for i, is_xfade in enumerate(is_xfade_pair):
        if is_xfade:
            chunks.append(current)
            current = [i + 1]
        else:
            current.append(i + 1)
    chunks.append(current)
    return chunks


def _premerge_chunks(chunk_groups, segment_results, seg_durations):
    """For each chunk of 1 segment, return the original segment path as-is.
    For each chunk of 2+ segments, pre-merge them via the ffmpeg concat
    demuxer into a single mp4 in TEMP_DIR.  Returns:
        (chunk_paths, chunk_durations) where chunk_paths[i] is a string
        file path and chunk_durations[i] is the summed duration.
    """
    from main import FFMPEG_EXE
    chunk_paths = []
    chunk_durations = []
    for ci, chunk in enumerate(chunk_groups):
        chunk_dur = sum(seg_durations[idx] for idx in chunk)
        if len(chunk) == 1:
            # Single-segment chunk — use the original segment file
            chunk_paths.append(segment_results[chunk[0]][1])
            chunk_durations.append(chunk_dur)
            continue
        # Multi-segment chunk: pre-merge via concat demuxer
        list_path = current_job().chunk_list_path(ci)
        with open(list_path, 'w', encoding='utf-8') as f:
            for idx in chunk:
                _, seg_path = segment_results[idx]
                abs_path = os.path.abspath(seg_path).replace(os.sep, '/').replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")
        out_path = current_job().chunk_video_path(ci)
        cmd = [
            FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_path,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '4',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            out_path,
        ]
        res = run_cancellable(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"Chunk pre-merge failed for chunk {ci}: {res.stderr.strip()}"
            )
        chunk_paths.append(out_path)
        chunk_durations.append(chunk_dur)
        logging.info(f"Pre-merged chunk {ci} ({len(chunk)} segments, {chunk_dur:.2f}s) -> {out_path}")
    return chunk_paths, chunk_durations


def _merge_highlight_boxes(boxes, windows):
    """Pair word boxes with timing windows, capping layer count at
    ``HIGHLIGHT_MAX_LAYERS`` by repeatedly merging adjacent entries
    (union bounding box, union time span).  Keeps the FFmpeg graph
    bounded for extreme ayahs; short ayahs pass through untouched."""
    pairs = list(zip(boxes, windows))
    while len(pairs) > HIGHLIGHT_MAX_LAYERS:
        merged = []
        for i in range(0, len(pairs) - 1, 2):
            (b1, w1), (b2, w2) = pairs[i], pairs[i + 1]
            x0 = min(b1["x"], b2["x"])
            y0 = min(b1["y"], b2["y"])
            x1 = max(b1["x"] + b1["w"], b2["x"] + b2["w"])
            y1 = max(b1["y"] + b1["h"], b2["y"] + b2["h"])
            merged.append((
                {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
                (min(w1[0], w2[0]), max(w1[1], w2[1])),
            ))
        if len(pairs) % 2:
            merged.append(pairs[-1])
        pairs = merged
    return pairs


def _video_encoding_args(quality_config):
    return [
        "-c:v", quality_config['codec'],
        "-preset", quality_config['preset'],
        "-b:v", quality_config['bitrate'],
        "-r", str(quality_config['fps']),
        "-threads", "4",
    ]


def build_segment_ffmpeg(bg_paths, audio_path, duration_sec, output_path, is_last=True, ayah_num=None, surah_name=None, text_png_path=None, highlight=None, frame_size=(TARGET_W, TARGET_H), quality='medium'):
    """Build one video segment with FFmpeg — background + audio, with optional ayah number watermark.

    Args:
      bg_paths: Single path or list of background video paths.
      audio_path: Path to the audio file to mux onto the video.
      duration_sec: Target segment duration (matches the audio length).
      output_path: Where to write the final segment .mp4.
      is_last: When False, append a 0.4 s outro fade so the cut to the
        next segment is soft, not a hard jump.  The last segment skips
        the outro fade to avoid a fade-to-black at the very end of the
        video.
      ayah_num: Optional ayah number to display (e.g., "1:2" for Surah 1, ayah 2)
      surah_name: Optional surah name for display (e.g., "Al-Baqarah")
      text_png_path: Optional full-frame transparent PNG (from
        ``quran_reels.services.text_overlay``) composited above the
        background chain and below the outro fade.  Feature 002-ayah-text-sync.
      highlight: Optional dict ``{png, w, h, words, windows}`` enabling
        word-level read-along highlighting (feature 002 US3).  ONE glow
        sprite input is repositioned per word via
        ``enable='between(t,start,end)'`` — never one input per word.
        Requires ``text_png_path``; silently skipped (plain display
        fallback, FR-011) when boxes/windows are missing or mismatched.
    """
    from main import FFMPEG_EXE
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio missing: {audio_path}")
    if os.path.getsize(audio_path) < 1000:
        raise ValueError(f"Audio too small: {os.path.getsize(audio_path)} bytes")

    quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])

    # Preprocess backgrounds
    preprocessed = []
    frame_w, frame_h = frame_size
    for p in (bg_paths if isinstance(bg_paths, (list, tuple)) else [bg_paths]):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Background missing: {p}")
        preprocessed.append(get_preprocessed_bg(p, frame_w, frame_h))

    n = len(preprocessed)
    part_dur = duration_sec / n

    logging.info(
        f"Building segment: {n} BGs, duration={duration_sec:.2f}s, "
        f"part_dur={part_dur:.2f}s, is_last={is_last}"
    )
    logging.info(f"  Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    # Build FFmpeg command
    common_args = ["-y", "-hide_banner", "-loglevel", "error"]
    inputs = []

    for p in preprocessed:
        inputs.extend(["-stream_loop", "-1", "-i", p])

    inputs.extend(["-i", audio_path])

    # Ayah text overlay (feature 002-ayah-text-sync): full-frame transparent
    # PNG — geometry baked in, so a single overlay=0:0 node composites it.
    # Input index is n+1 (after n backgrounds + audio at index n).
    text_idx = None
    text_overlays = []
    if text_png_path:
        text_overlays = (text_png_path if isinstance(text_png_path, list)
                         else [(text_png_path, 0.0, duration_sec)])
        text_idx = n + 1
        for overlay_path, _, _ in text_overlays:
            if not os.path.exists(overlay_path):
                raise FileNotFoundError(f"Text PNG missing: {overlay_path}")
            inputs.extend(["-loop", "1", "-framerate", "30", "-i", overlay_path])

    # Word-level read-along highlight (feature 002 US3): the glow sprite
    # is split into one branch per word; each branch fades in/out around
    # its own timing window (smooth spotlight, no hard pops), then all
    # branches composite ABOVE the text and BEFORE the outro fade.
    # Any inconsistency in meta → plain display (FR-011).
    hl_chain = ""
    hl_final = None
    if text_idx is not None and highlight:
        hl_png = highlight.get("png")
        hl_boxes = highlight.get("words") or []
        hl_windows = highlight.get("windows")
        if (hl_png and os.path.exists(hl_png) and hl_boxes and hl_windows
                and len(hl_windows) == len(hl_boxes)):
            pairs = _merge_highlight_boxes(hl_boxes, hl_windows)
            hl_w, hl_h = int(highlight["w"]), int(highlight["h"])
            hl_idx = text_idx + len(text_overlays)
            # -loop 1: the sprite must be a real timed stream, not a
            # single held frame — time-based fade st/d never advances on
            # a one-frame input (overlay's repeatlast would freeze the
            # fade's initial transparent frame forever).
            inputs.extend(["-loop", "1", "-framerate", "30", "-i", hl_png])
            n_words = len(pairs)
            fades = []
            if n_words == 1:
                fades.append(f"[{hl_idx}:v]format=rgba[hs0]")
            else:
                outs = "".join(f"[hs{i}]" for i in range(n_words))
                fades.append(f"[{hl_idx}:v]split={n_words}{outs}")
            parts = []
            src = "txtv"
            for i, (box, (t0, t1)) in enumerate(pairs):
                span = max(0.0, t1 - t0)
                fade_d = min(0.15, span * 0.25)
                if fade_d >= 0.03:
                    fades.append(
                        f"[hs{i}]format=rgba,"
                        f"fade=t=in:st={t0:.2f}:d={fade_d:.2f}:alpha=1,"
                        f"fade=t=out:st={t1 - fade_d:.2f}:d={fade_d:.2f}:alpha=1"
                        f"[hf{i}]"
                    )
                else:
                    fades.append(f"[hs{i}]format=rgba[hf{i}]")
                out_lbl = f"hl{i}"
                cx = int(box["x"] + (box["w"] - hl_w) / 2)
                cy = int(box["y"] + (box["h"] - hl_h) / 2)
                parts.append(
                    f"[{src}][hf{i}]overlay=x={cx}:y={cy}:"
                    f"enable='between(t,{t0:.2f},{t1:.2f})'[{out_lbl}]"
                )
                src = out_lbl
            if parts:
                hl_chain = ";" + ";".join(fades + parts)
                hl_final = src

    # Outro fade — applied to the final composite so the segment eases
    # out before the next one takes over.  Skipped on the very last
    # segment to avoid a fade-to-black at the very end of the video.
    outro_fade_filter = ""
    last_v = "v"
    if not is_last:
        outro_d = min(0.4, max(0.1, duration_sec / 2))
        outro_st = max(0.0, duration_sec - outro_d)
        outro_fade_filter = f"fade=t=out:st={outro_st:.3f}:d={outro_d:.3f}:alpha=1[v]"
        last_v = "vpre"

    if n == 1:
        filt = f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS,fps={quality_config['fps']}[{last_v}]"
        if text_idx is not None:
            # Text above background, below outro fade — fade eases the
            # composite so text and video leave together.
            for overlay_i, (_, start, end) in enumerate(text_overlays):
                label = ("txtv" if overlay_i == len(text_overlays) - 1
                         else f"txtv{overlay_i}")
                filt += (f";[{last_v}][{text_idx + overlay_i}:v]"
                         f"overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'"
                         f"[{label}]")
                last_v = label
            if hl_chain:
                filt += hl_chain
                last_v = hl_final
        if outro_fade_filter:
            filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
            last_v = "v"
        map_args = ["-map", f"[{last_v}]", "-map", "1:a"]
        cmd = [FFMPEG_EXE] + common_args + inputs + [
            "-filter_complex", filt,
        ] + map_args + [
            "-t", str(duration_sec), *_video_encoding_args(quality_config), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_path
        ]
    else:
        v_parts = ""
        for i in range(n):
            v_parts += f"[{i}:v]trim=duration={part_dur},setpts=PTS-STARTPTS,fps={quality_config['fps']}[v{i}];"
        v_parts += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[bg];"
        filt = v_parts + f"[bg]null[{last_v}]"
        if text_idx is not None:
            for overlay_i, (_, start, end) in enumerate(text_overlays):
                label = ("txtv" if overlay_i == len(text_overlays) - 1
                         else f"txtv{overlay_i}")
                filt += (f";[{last_v}][{text_idx + overlay_i}:v]"
                         f"overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'"
                         f"[{label}]")
                last_v = label
            if hl_chain:
                filt += hl_chain
                last_v = hl_final
        if outro_fade_filter:
            filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
            last_v = "v"
        map_args = ["-map", f"[{last_v}]", "-map", f"{n}:a"]

        cmd = [FFMPEG_EXE] + common_args + inputs + [
            "-filter_complex", filt,
        ] + map_args + [
            "-t", str(duration_sec), *_video_encoding_args(quality_config), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_path
        ]

    try:
        logging.info(f"Running FFmpeg command (timeout=300s): {' '.join(cmd[:8])}...")
        result = run_cancellable(cmd, check=True, capture_output=True, text=True, timeout=300)
        logging.info(f"FFmpeg completed in {result.stderr.count('frame=')} frames")
    except subprocess.TimeoutExpired:
        logging.error(f"FFmpeg timeout after 300s - this may be due to large background video")
        try:
            fallback_cmd = cmd.copy()
            fallback_cmd[-1] = output_path.replace('.mp4', '_fallback.mp4')
            if "-preset" in fallback_cmd:
                idx = fallback_cmd.index("-preset")
                fallback_cmd[idx+1] = "ultrafast"
            if "-crf" not in fallback_cmd:
                fallback_cmd.insert(-1, "-crf")
                fallback_cmd.insert(-1, "35")
            logging.warning("Trying fallback with lower quality...")
            result = run_cancellable(fallback_cmd, check=True, capture_output=True, text=True, timeout=180)
            if os.path.exists(fallback_cmd[-1]):
                shutil.move(fallback_cmd[-1], output_path)
        except OperationCancelled:
            raise
        except Exception as fallback_e:
            logging.error(f"Fallback also failed: {fallback_e}")
            raise RuntimeError(f"FFmpeg processing failed - try using shorter ayahs or different background")
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg failed with exit code {e.returncode}")
        logging.error(f"FFmpeg stderr: {e.stderr}")
        logging.error(f"FFmpeg stdout: {e.stdout}")
        raise RuntimeError(f"FFmpeg failed: {e.stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError(f"FFmpeg output not created: {output_path}")

    logging.info(f"✅ Segment created: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path


def process_single_ayah_ffmpeg(args):
    """Process one ayah: download audio, fetch background, build a video
    segment with the audio muxed onto the background.

    Uses ``BackgroundRotator`` to prevent video repetition.  The first
    element of ``args`` is the :class:`JobContext` for the build —
    passed explicitly so the worker thread (which has its own
    thread-local storage) uses the *parent* build's job_id, not a
    racey global.  See ``bug.md`` Issue 2 P0 #5
    ("ThreadPool race conditions").
    """
    from main import FFMPEG_EXE
    (job, reciter_id, surah, ayah, idx, template, bg_style, quality,
     reciter_speed, is_last, show_text, highlight_words,
     text_position, frame_size, include_bismillah) = args

    # Bind the parent build's JobContext to this worker thread so any
    # nested call to ``current_job()`` (e.g. inside ``download_audio``)
    # returns the same job — otherwise the ThreadPoolExecutor's worker
    # thread would have its own (empty) thread-local and
    # ``current_job()`` would lazily start a *third* job mid-build,
    # splitting the build's files across two job_ids.
    _job_local.ctx = job

    try:
        raise_if_cancelled()
        # Download audio (no trimming, faster)
        audio_path = download_audio(reciter_id, surah, ayah, idx)
        raise_if_cancelled()
        # Feature: reciter_speed — apply ffmpeg atempo to speed up / slow
        # down the recitation without changing pitch.  Done as a separate
        # pre-pass so the rest of the pipeline sees a normal mp3 file and
        # doesn't need to know about tempo.  atempo is limited to [0.5,
        # 2.0] per pass, so values outside that range are clamped.
        if reciter_speed and reciter_speed != 1.0:
            atempo = max(0.5, min(2.0, float(reciter_speed)))
            sped_path = current_job().sped_path(idx)
            cmd = [
                FFMPEG_EXE, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', audio_path,
                '-af', f'atempo={atempo:.3f}',
                '-c:a', 'libmp3lame', '-b:a', '192k',
                sped_path,
            ]
            res = run_cancellable(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(sped_path):
                audio_path = sped_path
                logging.debug(f"Segment {idx}: reciter_speed={reciter_speed} (atempo={atempo:.3f})")
            else:
                logging.warning(f"Segment {idx}: atempo pre-pass failed, using original audio: {res.stderr.strip()}")
        duration = get_audio_duration_ffprobe(audio_path)
        logging.debug(f"Segment {idx}: Audio duration = {duration:.2f}s")

        # Feature 002-ayah-text-sync: render the ayah's exact text onto a
        # transparent full-frame PNG.  Fetch failure = loud job failure
        # (Constitution II / FR-010) — never a silent textless success.
        text_png_path = None
        timed_text_overlays = []
        highlight = None
        # The current audio sources do not provide word timestamps. Enable
        # best-effort character-weighted timing, and label it as estimated.
        use_highlight = bool(show_text and highlight_words)
        bismillah_lead = should_show_bismillah_visual(
            include_bismillah, surah, ayah)
        lead_end = min(BISMILLAH_DURATION_SEC, duration)
        if bismillah_lead:
            bismillah_path = current_job().text_png_path(0)
            render_ayah_text_png(
                "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                bismillah_path, template=template, frame_w=frame_size[0],
                frame_h=frame_size[1], position=text_position)
            timed_text_overlays.append((bismillah_path, 0.0, lead_end))
            add_log("Bismillah: visual lead-in over ayah audio; no added silence")
        if use_highlight:
            add_log(f"highlight: estimated word timing ({surah}:{ayah})")
        if show_text:
            add_log(f"text: fetching ({surah}:{ayah})")
            try:
                ayah_text_str = get_ayah_text(surah, ayah)
            except Exception as exc:
                raise RuntimeError(
                    f"تعذر جلب نص الآية {surah}:{ayah} — تحقق من الاتصال "
                    f"ومصدر النص"
                ) from exc
            meta = render_ayah_text_png(
                ayah_text_str,
                current_job().text_png_path(idx),
                template=template,
                duration_sec=max(0.0, duration - lead_end) if bismillah_lead else duration,
                frame_w=frame_size[0],
                frame_h=frame_size[1],
                with_highlight=use_highlight,
                highlight_path=current_job().highlight_png(idx),
                position=text_position,
            )
            if bismillah_lead:
                timed_text_overlays.append((meta["png"], lead_end, duration))
                text_png_path = timed_text_overlays
            else:
                text_png_path = meta["png"]
            add_log(f"text: rendered ({surah}:{ayah})")
            if use_highlight:
                if meta.get("windows") and meta.get("highlight"):
                    highlight_windows = meta["windows"]
                    if bismillah_lead:
                        highlight_windows = [
                            (round(start + lead_end, 2), round(end + lead_end, 2))
                            for start, end in highlight_windows
                        ]
                    highlight = {
                        "png": meta["highlight"]["png"],
                        "w": meta["highlight"]["w"],
                        "h": meta["highlight"]["h"],
                        "words": meta["words"],
                        "windows": highlight_windows,
                    }
                    add_log(f"highlight: on ({surah}:{ayah}, "
                            f"{len(meta['words'])} words)")
                else:
                    # No audio duration → no reliable word timings:
                    # graceful plain-display fallback (FR-011).
                    add_log(f"highlight: unavailable, plain display "
                            f"({surah}:{ayah})")
        elif bismillah_lead:
            text_png_path = timed_text_overlays
        else:
            add_log(f"text: skipped ({surah}:{ayah})")

        # Select background using rotator to prevent repetition
        bg_path = get_next_background(bg_style, count=1)
        bg_paths = bg_path if isinstance(bg_path, list) else [bg_path]
        logging.debug(f"Segment {idx}: Using background {os.path.basename(bg_paths[0])}")

        segment_out = current_job().segment_path(idx)
        ayah_num = f"{surah}:{ayah}"
        build_segment_ffmpeg(bg_paths, audio_path, duration, segment_out, is_last=is_last, ayah_num=ayah_num, surah_name=SURAH_NAMES[surah-1], text_png_path=text_png_path, highlight=highlight, frame_size=frame_size, quality=quality)

        logging.info(f"✅ Segment {idx} complete: ayah {surah}:{ayah}")
        return (ayah, segment_out)

    except Exception as e:
        logging.error(f"❌ Error processing ayah {surah}:{ayah}: {e}")
        raise
