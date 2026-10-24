"""HTTP handlers for the Quran Reels Flask application.

The handlers import runtime configuration lazily from ``main`` so the
legacy entry point remains the single source of path and app configuration.
"""
from __future__ import annotations

def _validated_api_payload():
    from flask import jsonify, request
    from main import (OUTPUT_FORMATS, QUALITY_PRESETS, RECITERS_MAP, VERSE_COUNTS, get_available_templates)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'الطلب غير صالح؛ أرسل بيانات JSON صحيحة'}), 400)

    try:
        surah = int(data.get('surah', 1))
        start_ayah = int(data.get('startAyah', data.get('ayah', 1)))
        end_value = data.get('endAyah', start_ayah)
        end_ayah = int(end_value) if end_value not in (None, '') else start_ayah
        reciter_id = data.get('reciter')
        speed = float(data.get('reciterSpeed', 1.0))
        raw_duration = data.get('targetDurationSeconds')
        target_duration = (None if raw_duration in (None, '')
                           else int(raw_duration))
    except (TypeError, ValueError):
        return None, (jsonify({'error': 'تحقق من اختيار القارئ والسورة وأرقام الآيات'}), 400)

    if reciter_id not in RECITERS_MAP.values():
        return None, (jsonify({'error': 'اختر قارئاً من القائمة'}), 400)
    if surah not in VERSE_COUNTS:
        return None, (jsonify({'error': 'رقم السورة يجب أن يكون بين 1 و114'}), 400)
    if not 1 <= start_ayah <= VERSE_COUNTS[surah]:
        return None, (jsonify({'error': 'آية البداية خارج نطاق السورة المختارة'}), 400)
    if not start_ayah <= end_ayah <= VERSE_COUNTS[surah]:
        return None, (jsonify({'error': 'آية النهاية يجب أن تساوي آية البداية أو تليها ضمن السورة'}), 400)
    if not 0.5 <= speed <= 2.0:
        return None, (jsonify({'error': 'سرعة التلاوة يجب أن تكون بين 0.5 و2.0'}), 400)
    if target_duration is not None and target_duration < 1:
        return None, (jsonify({'error': 'المدة القصوى يجب أن تكون ثانية واحدة على الأقل'}), 400)

    quality = data.get('quality', 'medium')
    format_type = data.get('format', 'reels')
    template = data.get('template', 'normal')
    transition_style = data.get('transitionStyle') or None
    if quality not in QUALITY_PRESETS:
        return None, (jsonify({'error': 'جودة الفيديو المختارة غير صالحة'}), 400)
    if format_type not in OUTPUT_FORMATS:
        return None, (jsonify({'error': 'تنسيق الفيديو المختار غير صالح'}), 400)
    if template not in get_available_templates():
        return None, (jsonify({'error': 'القالب المختار غير صالح'}), 400)
    if transition_style not in (None, 'cinematic', 'dynamic', 'smooth', 'cut'):
        return None, (jsonify({'error': 'أسلوب الانتقال المختار غير صالح'}), 400)

    return {
        'data': data,
        'reciter': reciter_id,
        'surah': surah,
        'startAyah': start_ayah,
        'endAyah': end_ayah,
        'speed': speed,
        'targetDurationSeconds': target_duration,
        'quality': quality,
        'format': format_type,
        'template': template,
        'transitionStyle': transition_style,
    }, None


def serve_ui():
    import os
    from flask import send_file
    from main import UI_PATH
    if os.path.exists(UI_PATH):
        return send_file(UI_PATH)
    return f"Error: UI.html not found at {UI_PATH}", 404


def serve_css():
    from flask import send_from_directory
    from main import BUNDLE_DIR
    return send_from_directory(BUNDLE_DIR, 'style.css')


def serve_generated_css():
    from flask import send_from_directory
    from main import BUNDLE_DIR
    return send_from_directory(BUNDLE_DIR, 'tailwind.generated.css')


def serve_js():
    from flask import send_from_directory
    from main import BUNDLE_DIR
    return send_from_directory(BUNDLE_DIR, 'main.js')


def serve_asset(filename):
    import os
    from flask import send_from_directory
    from main import EXEC_DIR
    return send_from_directory(os.path.join(EXEC_DIR, 'assets'), filename)


def generate_video():
    import threading
    from flask import jsonify
    from main import (HIGHLIGHT_WORDS_DEFAULT, SHOW_TEXT_DEFAULT, TEXT_POSITION_DEFAULT, TEXT_POSITIONS, _validated_api_payload, build_video, current_progress, reset_progress)
    if current_progress.is_running:
        return jsonify({'error': 'عملية إنشاء فيديو قيد التنفيذ بالفعل'}), 400

    payload, error = _validated_api_payload()
    if error:
        return error
    data = payload['data']
    reciter_id = payload['reciter']
    surah = payload['surah']
    start_ayah = payload['startAyah']
    end_ayah = payload['endAyah']
    quality = payload['quality']
    format_type = payload['format']
    template = payload['template']
    person_name = data.get('personName', '')
    target_duration_seconds = payload['targetDurationSeconds']
    include_bismillah = data.get('includeBismillah', False)
    reciter_speed = payload['speed']
    transition_style_override = payload['transitionStyle']
    show_text = bool(data.get('showText', data.get('show_text', SHOW_TEXT_DEFAULT)))
    highlight_words = bool(data.get(
        'highlightWords', data.get('highlight_words', HIGHLIGHT_WORDS_DEFAULT)))
    text_position = str(data.get(
        'textPosition', data.get('text_position', TEXT_POSITION_DEFAULT))
        or TEXT_POSITION_DEFAULT).lower()
    if text_position not in TEXT_POSITIONS:
        text_position = TEXT_POSITION_DEFAULT

    reset_progress()
    current_progress.set(is_running=True, is_complete=False, error=None)

    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality,
              format_type, template, person_name, target_duration_seconds,
              include_bismillah, reciter_speed, transition_style_override,
              show_text, highlight_words, text_position),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True, 'message': 'بدأ إنشاء الفيديو'})


def get_progress():
    from flask import jsonify
    from main import current_progress
    return jsonify(current_progress.to_dict())


def preview_video():
    """Generate a preview of the first ayah (one verse)."""
    import threading
    from flask import jsonify
    from main import (HIGHLIGHT_WORDS_DEFAULT, SHOW_TEXT_DEFAULT, TEXT_POSITION_DEFAULT, TEXT_POSITIONS, _validated_api_payload, build_video, current_progress, reset_progress)
    if current_progress.is_running:
        return jsonify({'error': 'عملية أخرى قيد التنفيذ'}), 400

    payload, error = _validated_api_payload()
    if error:
        return error
    data = payload['data']
    reciter_id = payload['reciter']
    surah = payload['surah']
    ayah = payload['startAyah']
    template = payload['template']
    show_text = bool(data.get('showText', data.get('show_text', SHOW_TEXT_DEFAULT)))
    highlight_words = bool(data.get(
        'highlightWords', data.get('highlight_words', HIGHLIGHT_WORDS_DEFAULT)))
    text_position = str(data.get(
        'textPosition', data.get('text_position', TEXT_POSITION_DEFAULT))
        or TEXT_POSITION_DEFAULT).lower()
    if text_position not in TEXT_POSITIONS:
        text_position = TEXT_POSITION_DEFAULT

    reset_progress()
    current_progress.set(is_running=True, is_complete=False, error=None)
    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, ayah, ayah, 'low', 'reels', template, '', None,
              False, 1.0, None, show_text, highlight_words, text_position),
        daemon=True
    )
    thread.start()
    return jsonify({'success': True, 'message': 'بدأ إنشاء المعاينة'})


def get_config():
    import os
    from flask import jsonify, url_for
    from main import (APP_VERSION, BACKGROUND_VIDEO_EXTENSIONS, OUTPUT_FORMATS, QUALITY_PRESETS, RECITERS_MAP, SURAH_NAMES, TEMPLATE_LABELS, VERSE_COUNTS, VISION_DIR, get_available_templates)
    themes = []
    for key, config in get_available_templates().items():
        style = config['bg_style']
        style_dir = os.path.join(VISION_DIR, style)
        if not os.path.isdir(style_dir):
            continue
        files = sorted(
            (name for name in os.listdir(style_dir)
             if os.path.isfile(os.path.join(style_dir, name))
             and name.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)),
            key=str.casefold,
        )
        if not files:
            continue
        themes.append({
            'key': key,
            'label': TEMPLATE_LABELS.get(key, key.replace('_', ' ').title()),
            'previewUrl': url_for('serve_vision', filename=f'{style}/{files[0]}'),
            'videoCount': len(files),
        })
    return jsonify({
        'version': APP_VERSION,
        'surahs': SURAH_NAMES,
        'verseCounts': VERSE_COUNTS,
        'reciters': RECITERS_MAP,
        'qualityPresets': list(QUALITY_PRESETS.keys()),
        'outputFormats': list(OUTPUT_FORMATS.keys()),
        'templates': [theme['key'] for theme in themes],
        'themes': themes,
    })


def serve_vision(filename):
    from flask import send_from_directory
    from main import VISION_DIR
    return send_from_directory(VISION_DIR, filename)


def serve_output(filename):
    from flask import send_from_directory
    from main import OUT_DIR
    return send_from_directory(OUT_DIR, filename)



def register_routes(app):
    """Register handlers while retaining the original Flask endpoint names."""
    routes = (
        ('/', 'serve_ui', ('GET',)),
        ('/style.css', 'serve_css', ('GET',)),
        ('/tailwind.generated.css', 'serve_generated_css', ('GET',)),
        ('/main.js', 'serve_js', ('GET',)),
        ('/assets/<path:filename>', 'serve_asset', ('GET',)),
        ('/api/generate', 'generate_video', ('POST',)),
        ('/api/progress', 'get_progress', ('GET',)),
        ('/api/preview', 'preview_video', ('POST',)),
        ('/api/config', 'get_config', ('GET',)),
        ('/vision/<path:filename>', 'serve_vision', ('GET',)),
        ('/outputs/<path:filename>', 'serve_output', ('GET',)),
    )
    handlers = globals()
    for rule, endpoint, methods in routes:
        app.add_url_rule(rule, endpoint=endpoint, view_func=handlers[endpoint], methods=list(methods))
