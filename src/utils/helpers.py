"""Utility functions for text processing and path handling."""

import os
import sys
import re


def parse_string_to_dict(input_string: str) -> dict:
    """Parse JSON string from HTML content.
    
    Args:
        input_string: String containing JSON data.
        
    Returns:
        Parsed dictionary.
    """
    import json
    
    # Clean the input string
    input_string = input_string.replace('\\\\\\\"', "")
    input_string = input_string.replace("\\", "")
    input_string = input_string.replace("u0026", "&")
    
    # Find JSON data boundaries
    json_start_index = input_string.find('{')
    json_end_index = input_string.rfind('}')
    json_data = input_string[json_start_index:json_end_index+1]
    
    # Parse JSON data
    return json.loads(json_data)


def is_not_comment(url: str) -> bool:
    """Check if URL line is not a comment or empty.
    
    Args:
        url: URL string to check.
        
    Returns:
        True if not a comment, False otherwise.
    """
    regex = r"^(?!\/\/|#|^$)"
    pattern = re.compile(regex)
    return bool(re.match(pattern, url))


def get_exe_dir() -> str:
    """Get the directory of the executable or script file (project root).
    
    Returns:
        Directory path as string.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script - return project root (2 levels up from this file)
        current_file = os.path.abspath(__file__)
        src_dir = os.path.dirname(os.path.dirname(current_file))  # src/
        project_root = os.path.dirname(src_dir)  # project root
        return project_root


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource for dev and PyInstaller.
    
    Args:
        relative_path: Relative path to resource.
        
    Returns:
        Absolute path as string.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


def get_full_path(relative_path: str) -> str:
    """Get absolute path based on script location.
    
    Args:
        relative_path: Relative path to file.
        
    Returns:
        Absolute path as string.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, relative_path)
