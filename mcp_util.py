"""
Utilities
Meant for implementing users own functions
Behold, my field unto which I grow my fucks.
Notice that it is barren, for I have no fucks to give.
@author: GUU8HC
"""

import json
from pathlib import Path
from datetime import datetime
from difflib import get_close_matches

from sie_settings import (
    DIFFLIB_NUMBER_OF_RESULTS,
    DIFFLIB_CUTOFF,
    RAPIDFUZZ_NUMBER_OF_RESULTS,
    RAPIDFUZZ_CUTOFF
)

def get_all_paramdef_files():
    """
    Get all param definition JSON files in the workspace
    """
    workspace_root = Path(__file__).resolve().parents[1]
    files = list(workspace_root.glob("**/*paramdef*.json"))
    return files

def get_keys(data):
    """Recursively get all keys in a nested dictionary."""
    keys = set()
    if isinstance(data, dict):
        for key, value in data.items():
            keys.add(key)
            keys.update(get_keys(value))
    elif isinstance(data, list):
        for item in data:
            keys.update(get_keys(item))
    return keys

def get_precise_time():
    """
    Get the precise time up to microsecond precision
    """
    return datetime.now()

def get_definition(keyword: str, return_path: bool = False):
    """
    Search all param definition JSON files in the workspace for a given key.

    If return_path is True, returns the path to the first file that contains the key (searching keys, not values) as a string.
    If return_path is False, returns the data object.
    If nothing is found returns None.
    """
    paramdefs = get_all_paramdef_files()

    if not paramdefs:
        return None
    
    # Normalize matching by comparing lowercase forms of keys and keyword.
    lower_keyword = keyword.lower()

    def key_exists(obj, key):
        if isinstance(obj, dict):
            # Check direct keys using case-insensitive comparison
            for k in obj.keys():
                if k.lower() == key:
                    return True
            # Recurse into values
            return any(key_exists(v, key) for v in obj.values())
        if isinstance(obj, list):
            return any(key_exists(i, key) for i in obj)
        return False
    
    for paramdef in paramdefs:
        try:
            data = json.loads(paramdef.read_text())
        except Exception:
            continue
    if key_exists(data, lower_keyword):
            if return_path:
                return str(paramdef)
            return data
    return None

def find_path(data, target_key, path=None):
    """Recursively search for the target key and return its full path as a list.

    Matching is done case-insensitively by comparing lowercase forms, but the
    returned path preserves the original key casing from the data.
    """
    if path is None:
        path = []

    # Ensure target_key is normalized for comparison
    target_lower = target_key.lower()

    for key, value in data.items():
        new_path = path + [key]
        if key.lower() == target_lower:
            return new_path
        elif isinstance(value, dict):
            result = find_path(value, target_key, new_path)
            if result:
                return result
    return None

def get_definition_path_difflib(keyword: str):
    """
    Get the path to the definition of a given keyword
    from param definition JSON files
    using difflib for fuzzy matching.
    """
    paths = []
    paramdefs = get_all_paramdef_files()
    for paramdef in paramdefs:
        try:
            data = json.loads(paramdef.read_text())
        except Exception:
            continue
        
        # Get keys from JSON data
        keys = get_keys(data)
        close_matches = get_close_matches(keyword, keys, n=DIFFLIB_NUMBER_OF_RESULTS, cutoff=DIFFLIB_CUTOFF)

        print(f"Close_matches: {close_matches}")

        if close_matches:
            for match in close_matches:
                path = find_path(data, match)
                if path:
                    paths.append({
                        "file": str(paramdef),
                        "definition_path": "/".join(path)
                    })
    return paths

def get_definition_path_rapidfuzz(keyword: str):
    """
    Get the path to the definition of a given keyword
    from param definition JSON files
    using RapidFuzz for fuzzy matching.
    """
    from rapidfuzz import process, fuzz

    paths = []
    paramdefs = get_all_paramdef_files()
    for paramdef in paramdefs:
        try:
            data = json.loads(paramdef.read_text())
        except Exception:
            continue
        
        # Get keys from JSON data
        keys = list(get_keys(data))
        close_matches = process.extract(
            keyword,
            keys,
            scorer=fuzz.WRatio,
            limit=RAPIDFUZZ_NUMBER_OF_RESULTS,
            score_cutoff=int(RAPIDFUZZ_CUTOFF * 100)
        )

        print(f"Close_matches: {close_matches}")

        if close_matches:
            for match, score, _ in close_matches:
                path = find_path(data, match)
                if path:
                    paths.append({
                        "file": str(paramdef),
                        "definition_path": "/".join(path),
                        "similarity_score": score / 100.0
                    })
    return paths

# Example usage
if __name__ == "__main__":
    target = "Generl"
    get_definition_path_difflib(target)
    get_definition_path_rapidfuzz(target)
