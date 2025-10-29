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



def duplicate_session(session_name, existing_sessions):

    """

    Generates a unique session name for a duplicated session.



    Args:

        session_name (str): The name of the session to duplicate.

        existing_sessions (list): A list of existing session names.



    Returns:

        str: A unique name for the duplicated session.

    """

    base_name = session_name

    clone_num = 1

    while True:

        new_name = f"{base_name} CLONE {clone_num}"

        if new_name not in existing_sessions:

            return new_name

        clone_num += 1

 