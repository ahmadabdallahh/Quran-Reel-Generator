"""Video-generation orchestration.

Coordinates ayah downloads, segment rendering, transitions, and final output.
The public entry point remains re-exported from ``main`` for compatibility.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import shutil
import subprocess

from quran_reels.config import (
    BISMILLAH_SKIP_SURAHS,
    HIGHLIGHT_WORDS_DEFAULT, SHOW_TEXT_DEFAULT, TEXT_POSITION_DEFAULT,
    OUTPUT_FORMATS, QUALITY_PRESETS, SURAH_NAMES, TEMPLATES,
    TEXT_POSITIONS, VERSE_COUNTS, VIDEO_TRANSITIONS,
)
from quran_reels.services.text_overlay import resolve_profile
from quran_reels.services.video_rendering import (
    _compute_xfade_pairs, _premerge_chunks, _split_into_chunks,
    _video_encoding_args, process_single_ayah_ffmpeg,
)
from quran_reels.services.audio import (
    estimate_ayah_duration as _estimate_ayah_duration,
    get_audio_duration_ffprobe,
)
from quran_reels.services.background import init_background_rotator
from quran_reels.utils.job import current_job, start_new_job
from quran_reels.utils.progress import (
    add_log, current_progress, update_progress,
)
from quran_reels.services.themes import get_available_templates



def _render_ayah_segments(ayah_args, max_workers, total, surah, include_bismillah):
    """Render ayah segments concurrently and return them in Quran order."""
    # Process in parallel
    add_log('Processing ayat in parallel...')

    # Bismillah is an opt-in visual lead-in rendered over the first
    # ayah's audio. It does not create a synthetic silent segment.
    segment_results = []
    if include_bismillah and surah in BISMILLAH_SKIP_SURAHS:
        add_log(f"Skipping Bismillah for surah {surah} (in BISMILLAH_SKIP_SURAHS)")

    if max_workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_single_ayah_ffmpeg, a): a for a in ayah_args}
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                ayah_num, seg_path = future.result()
                segment_results.append((ayah_num, seg_path))
                update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')
    else:
        for i, args in enumerate(ayah_args, 1):
            ayah_num, seg_path = process_single_ayah_ffmpeg(args)
            segment_results.append((ayah_num, seg_path))
            update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')

    # Sort by ayah number
    segment_results.sort(key=lambda x: x[0])
    return segment_results


def _write_concat_list(segment_results):
    """Write an FFmpeg concat manifest scoped to the current render job."""
    list_path = current_job().concat_list_path()
    with open(list_path, "w", encoding="utf-8") as manifest:
        for _, segment_path in segment_results:
            absolute_path = os.path.abspath(segment_path).replace(os.sep, '/')
            absolute_path = absolute_path.replace("'", "'\\''")
            manifest.write(f"file '{absolute_path}'\n")
    return list_path


def _simple_concat_command(list_path, video_encode_args, output_path):
    """Build the hard-cut concat command used for single segments and fallbacks."""
    from main import FFMPEG_EXE
    return [
        FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        *video_encode_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]


def _probe_segment_durations(segment_results):
    """Read each segment duration, retaining the existing five-second fallback."""
    durations = []
    for _, segment_path in segment_results:
        try:
            duration = get_audio_duration_ffprobe(segment_path)
        except Exception as exc:
            logging.warning(
                f"ffprobe failed for {segment_path}: {exc}; defaulting to 5.0s"
            )
            duration = 5.0
        durations.append(duration)
    logging.info(f"Segment durations: {[f'{duration:.2f}' for duration in durations]}")
    return durations


def _build_xfade_filter(segment_results, durations, transition_name,
                        transition_duration, xfade_pairs):
    """Build the video crossfade graph and continuous audio concat graph."""
    chunk_groups = _split_into_chunks(xfade_pairs)
    chunk_paths, chunk_durations = _premerge_chunks(
        chunk_groups, segment_results, durations,
    )
    segment_results = [(index, path) for index, path in enumerate(chunk_paths)]
    durations = chunk_durations

    filters = []
    for index, (_, segment_path) in enumerate(segment_results):
        duration = durations[index]
        filters.append(
            f"[{index}:v]trim=duration={duration:.3f},setpts=PTS-STARTPTS[v{index}];"
            f"[{index}:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a{index}]"
        )

    cumulative = 0.0
    for index in range(len(segment_results) - 1):
        cumulative += durations[index]
        offset = max(0.0, cumulative - (index + 1) * transition_duration)
        filters.append(
            f"[v{index}][v{index + 1}]xfade=transition={transition_name}:"
            f"duration={transition_duration}:offset={offset:.3f}[v{index + 1}]"
        )

    last_video = f"v{len(segment_results) - 1}"
    audio_inputs = "".join(f"[a{index}]" for index in range(len(segment_results)))
    video_extension = transition_duration * max(0, len(segment_results) - 1)
    filters.append(
        f"[{last_video}]tpad=stop_mode=clone:"
        f"stop_duration={video_extension:.3f},null[outv];"
        f"{audio_inputs}concat=n={len(segment_results)}:v=0:a=1[outa]"
    )
    input_args = [arg for _, path in segment_results for arg in ("-i", path)]
    return segment_results, input_args, ';'.join(filters)


def _xfade_concat_command(segment_results, template_config,
                          video_encode_args, output_path):
    """Build the configured transition command, or hard-cut when disabled."""
    from main import FFMPEG_EXE
    durations = _probe_segment_durations(segment_results)
    transition_style = template_config.get('transition_style', 'crossfade')
    transition_key = (
        transition_style if transition_style in ('crossfade', 'fadeblack')
        else template_config.get('transition', 'crossfade')
    )
    transition = VIDEO_TRANSITIONS.get(
        transition_key, VIDEO_TRANSITIONS['crossfade'],
    )
    transition_name = transition['type']
    transition_duration = transition.get('duration', 0.5)
    pairs = _compute_xfade_pairs(
        transition_style, len(segment_results), transition_duration,
    )
    logging.info(
        f"Using transition style: {transition_style!r} "
        f"({sum(pairs)}/{len(segment_results) - 1} pairs will xfade "
        f"with {transition_name})"
    )
    if not any(pairs):
        return None

    segment_results, input_args, filter_complex = _build_xfade_filter(
        segment_results, durations, transition_name, transition_duration, pairs,
    )
    command = [FFMPEG_EXE, "-y"] + input_args + [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        *video_encode_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]
    return command


def _prepare_concat_command(segment_results, template_config,
                            video_encode_args, list_path, output_path):
    """Choose a crossfade command and retain the existing hard-cut fallback."""
    if len(segment_results) <= 1:
        return _simple_concat_command(list_path, video_encode_args, output_path)
    try:
        command = _xfade_concat_command(
            segment_results, template_config, video_encode_args, output_path,
        )
        if command is None:
            return _simple_concat_command(list_path, video_encode_args, output_path)
        return command
    except Exception as exc:
        logging.warning(f"Crossfade setup failed, using simple concat: {exc}")
        return _simple_concat_command(list_path, video_encode_args, output_path)


def _run_concat_with_fallback(command, list_path, video_encode_args, output_path):
    """Run concat with stream-copy and re-encode fallbacks on FFmpeg errors."""
    from main import FFMPEG_EXE
    try:
        if command is None:
            raise ValueError("No concat command generated")
        logging.info(f"Running Concat: {' '.join(command)}")
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        logging.error("FFmpeg Concat Failed with crossfade effects!")
        logging.error(f"STDOUT: {exc.stdout}")
        logging.error(f"STDERR: {exc.stderr}")
        logging.info("Trying fallback without fade effects...")
        fallback = [
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", "-movflags", "+faststart", output_path,
        ]
        try:
            logging.info(f"Running Fallback: {' '.join(fallback)}")
            subprocess.run(fallback, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.CalledProcessError as fallback_error:
            logging.error("Fallback also failed!")
            logging.error(f"Fallback STDERR: {fallback_error.stderr}")
            logging.info("Last resort: re-encoding all segments...")
            last_resort = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                *video_encode_args,
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                output_path,
            ]
            subprocess.run(
                last_resort, check=True, capture_output=True, text=True, timeout=600,
            )


def _concatenate_segments(segment_results, template_config, video_encode_args,
                          temp_output_path):
    """Write the concat manifest, prepare the command, and encode the result."""
    add_log('Concatenating segments with crossfade transitions...')
    update_progress(85, 'جاري دمج المقاطع مع انتقالات احترافية...')
    list_path = _write_concat_list(segment_results)
    command = _prepare_concat_command(
        segment_results, template_config, video_encode_args,
        list_path, temp_output_path,
    )
    _run_concat_with_fallback(
        command, list_path, video_encode_args, temp_output_path,
    )


def _prepare_render_config(reciter_id, surah, start_ayah, end_ayah, quality,
                           format_type, template, target_duration_seconds,
                           transition_style_override):
    """Resolve render presets, validate the ayah range, and initialize assets."""
    quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])
    video_encode_args = _video_encoding_args(quality_config)
    frame_size = tuple(OUTPUT_FORMATS.get(format_type, OUTPUT_FORMATS['reels'])['size'])
    template_config = get_available_templates().get(template, TEMPLATES['normal'])
    if transition_style_override:
        template_config = {
            **template_config,
            'transition_style': transition_style_override,
        }
    bg_style = template_config['bg_style']

    text_profile = resolve_profile(template)
    logging.info(f"Text profile for job: {template} → {text_profile}")
    if surah not in VERSE_COUNTS:
        raise ValueError(f"Invalid surah: {surah}")

    max_ayah = VERSE_COUNTS[surah]
    start_ayah = max(1, min(start_ayah, max_ayah))
    last_ayah = min(start_ayah + 9, max_ayah) if end_ayah is None else min(end_ayah, max_ayah)
    if last_ayah < start_ayah:
        last_ayah = start_ayah

    total = last_ayah - start_ayah + 1
    if total > 50:
        last_ayah = start_ayah + 49
        total = 50

    if target_duration_seconds and target_duration_seconds > 0:
        cumulative = 0.0
        new_last = start_ayah - 1
        for ayah in range(start_ayah, last_ayah + 1):
            duration = _estimate_ayah_duration(reciter_id, surah, ayah)
            if new_last >= start_ayah and cumulative + duration > target_duration_seconds:
                break
            cumulative += duration
            new_last = ayah
        if new_last < start_ayah:
            new_last = start_ayah
        if new_last < last_ayah:
            trimmed = last_ayah - new_last
            add_log(
                f"target_duration_seconds={target_duration_seconds}s capped last_ayah "
                f"({last_ayah} -> {new_last}, dropped {trimmed} ayahs, "
                f"~{cumulative:.1f}s)"
            )
            last_ayah = new_last
            total = last_ayah - start_ayah + 1

    add_log(
        f'Building {total} ayat from {start_ayah} to {last_ayah} '
        f'(job_id={current_job().job_id})'
    )
    update_progress(10, f'جاري تحضير {total} آيات...')
    init_background_rotator(bg_style)
    logging.info(f"Background rotator initialized for style: {bg_style}")
    max_workers = total if total <= 3 else 4
    logging.info(f"Using {max_workers} workers ({total} ayat total)")
    video_transition = template_config.get('transition', 'fade')
    logging.info(f"Using transition: {video_transition}")

    return {
        'video_encode_args': video_encode_args,
        'frame_size': frame_size,
        'template_config': template_config,
        'bg_style': bg_style,
        'start_ayah': start_ayah,
        'last_ayah': last_ayah,
        'total': total,
        'max_workers': max_workers,
    }


def _build_ayah_args(job, reciter_id, surah, start_ayah, last_ayah, template,
                     bg_style, quality, reciter_speed, show_text,
                     highlight_words, text_position, frame_size,
                     include_bismillah):
    """Create the stable, job-scoped worker arguments for each ayah."""
    if text_position not in TEXT_POSITIONS:
        text_position = TEXT_POSITION_DEFAULT
    total = last_ayah - start_ayah + 1
    # Ayah clips stay visually complete here; the concat stage applies the
    # selected boundary transition once, avoiding doubled fades to black.
    return [
        (job, reciter_id, surah, ayah, index, template, bg_style, quality,
         reciter_speed, True, show_text, highlight_words,
         text_position, frame_size, include_bismillah)
        for index, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)
    ]


def _build_output_paths(surah, start_ayah, last_ayah, quality, template,
                        person_name):
    """Create unique temporary and user-facing output paths for this render."""
    from main import VIDEO_DIR
    clean_name = (
        person_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        if person_name else 'User'
    )
    temp_filename = (
        f"{clean_name}_Surah{surah}_Ayah{start_ayah}-{last_ayah}_"
        f"{quality}_{template}.mp4"
    )
    temp_output_path = current_job().temp_output_path(temp_filename)

    surah_number = f"{surah:03d}"
    ayah_range = f"{start_ayah}-{last_ayah}"
    user_part = f"_{clean_name}" if clean_name else ""
    surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
    surah_name = surah_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    filename = (
        f"Quran_Surah{surah_number}_{surah_name}_Ayah{ayah_range}"
        f"{user_part}_{quality}.mp4"
    )
    output_path = current_job().final_output_path(filename)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    return temp_output_path, output_path


def build_video(reciter_id, surah, start_ayah, end_ayah=None,
                quality='medium', format_type='reels', template='normal',
                person_name='', target_duration_seconds=None,
                include_bismillah=False, reciter_speed=1.0,
                transition_style_override=None,
                show_text=SHOW_TEXT_DEFAULT,
                highlight_words=HIGHLIGHT_WORDS_DEFAULT,
                text_position=TEXT_POSITION_DEFAULT):
    """Main video builder.

    Downloads each ayah's recitation, muxes it onto a background video
    (selected from a rotating pool to avoid repetition), and concatenates
    the segments into a single mp4.  With ``show_text`` (feature
    002-ayah-text-sync) each segment additionally composites the exact
    Uthmani text of its ayah; with it disabled the output is identical
    to the audio + background pipeline.

    Args:
      reciter_id:        Reciter identifier (key of ``RECITERS_MAP``).
      surah:             Surah number (1..114).
      start_ayah:        First ayah to include.
      end_ayah:          Last ayah to include (defaults to ``start_ayah + 9``).
      quality:           One of ``QUALITY_PRESETS`` keys.
      format_type:       One of ``OUTPUT_FORMATS`` keys.
      template:          One of ``TEMPLATES`` keys (drives background style).
      person_name:       Optional string for the output filename.
      target_duration_seconds: Optional cap on the total video length.
      include_bismillah: If True and the surah is not in
                         ``BISMILLAH_SKIP_SURAHS``, show an unsynchronized
                         1.8 s visual lead-in over the first ayah's audio.
      reciter_speed:     0.5..2.0; tempo multiplier applied via ffmpeg atempo.
      transition_style_override: Optional key of ``VIDEO_TRANSITIONS`` to
                                 override the template's default.

    Returns:
        str | None: Absolute ``output_path`` of the final mp4 on success,
        or ``None`` on failure.  Progress and errors are also reported
        via ``current_progress`` so the existing
        ``threading.Thread(target=build_video, ...)`` callers in the API
        routes continue to work unchanged.
    """
    try:
        # Start a fresh job context: gives every temp file a unique
        # ``job_id`` so this build cannot collide with any previous
        # build's leftovers or a parallel build's running files (see
        # ``bug.md`` Issue 2 P0 #1 and #2).  Also resets the
        # per-build circuit-breaker counters that may have tripped on
        # a previous run.
        start_new_job()
        current_progress.set(is_running=True, is_complete=False, error=None)

        settings = _prepare_render_config(
            reciter_id, surah, start_ayah, end_ayah, quality, format_type,
            template, target_duration_seconds, transition_style_override,
        )
        video_encode_args = settings['video_encode_args']
        frame_size = settings['frame_size']
        template_config = settings['template_config']
        bg_style = settings['bg_style']
        start_ayah = settings['start_ayah']
        last_ayah = settings['last_ayah']
        total = settings['total']
        max_workers = settings['max_workers']

        job = current_job()
        ayah_args = _build_ayah_args(
            job, reciter_id, surah, start_ayah, last_ayah, template, bg_style,
            quality, reciter_speed, show_text, highlight_words, text_position,
            frame_size, include_bismillah,
        )
        temp_output_path, output_path = _build_output_paths(
            surah, start_ayah, last_ayah, quality, template, person_name,
        )

        segment_results = _render_ayah_segments(
            ayah_args, max_workers, total, surah, include_bismillah,
        )
        _concatenate_segments(
            segment_results, template_config, video_encode_args, temp_output_path,
        )
        if os.path.exists(temp_output_path):
            shutil.move(temp_output_path, output_path)


        # Success
        add_log('Done!')
        update_progress(100, 'تم بنجاح!')
        current_progress.set(is_complete=True, output_path=output_path)

        if os.path.isfile(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logging.info(f"Output: {output_path} ({size_mb:.2f} MB)")

        return output_path

    except Exception as e:
        logging.exception("Error in build_video")
        current_progress.set(error=str(e))
        add_log(f'[ERROR] {str(e)}')
        update_progress(0, f'خطأ: {str(e)}')
        return None
    finally:
        current_progress.set(is_running=False)
