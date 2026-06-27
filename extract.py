import sys

with open("old_main_utf8.py", "r", encoding="utf-8") as f:
    old_content = f.read()

missing = []

def extract_block(start_str, end_str=None):
    start_idx = old_content.find(start_str)
    if start_idx == -1: return ""
    if end_str:
        end_idx = old_content.find(end_str, start_idx)
        return old_content[start_idx:end_idx]
    return ""

def extract_func(func_name):
    # simple extraction assuming def ... down to next def/comment and not nested
    import re
    match = re.search(r"def\s+" + func_name + r"\s*\(.*?\):.*?(?=(?:\n\w+)|(?:\n# =)|$)", old_content, re.DOTALL)
    if match: return match.group(0)
    return ""

blocks = []

blocks.append("""
# =============================================================================
# RESTORED FUNCTIONS
# =============================================================================
""")

# circuit breaker block
cb_match = re.search(r"# Circuit breaker state.*?def _circuit_breaker.*?(?=\n# =|\ndef get_ayah)", old_content, re.DOTALL | re.IGNORECASE)
if cb_match:
    blocks.append(cb_match.group(0))
else:
    # manual extraction
    blocks.append(extract_func("is_circuit_breaker_open"))
    blocks.append(extract_func("record_download_success"))
    blocks.append(extract_func("record_download_failure"))
    blocks.append(extract_func("download_audio"))
    blocks.append(extract_func("get_audio_duration_ffprobe"))

blocks.append(extract_func("reset_progress"))
blocks.append(extract_func("add_log"))
blocks.append(extract_func("update_progress"))
blocks.append(extract_func("update_ayah_progress"))

# bg cache block
bg_match = re.search(r"BG_CACHE = \{\}.*?(?=\n# ==|\n# NOTE)", old_content, re.DOTALL)
if bg_match:
    blocks.append(bg_match.group(0))
else:
    blocks.append(extract_func("init_bg_cache"))
    blocks.append(extract_func("pick_bg"))
    blocks.append(extract_func("get_preprocessed_bg"))

# actually let's just use the exact text from view_file of old_main_utf8.py 
# we know where they are!

