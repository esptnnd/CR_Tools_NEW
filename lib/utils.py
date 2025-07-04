# Utility functions 

import re
import os
import json

def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text) 

def get_debug_mode():
    # Try to cache the value for performance
    if not hasattr(get_debug_mode, '_cached'):
        settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.json')
        debug_mode = 'SILENT'
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                debug_mode = settings.get('DEBUG_MODE', 'SILENT')
        except Exception:
            pass
        get_debug_mode._cached = debug_mode
    return get_debug_mode._cached

def debug_print(*args, **kwargs):
    if get_debug_mode() == 'DEBUG':
        print(*args, **kwargs) 