"""
@author: GUU8HC
"""

import os
import sys
import json
# Add parent directory to Python path to import env module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xml.etree.ElementTree as ET

from pathlib import Path

from generic_utils import (
    info,
    debug,
    error,
    get_keys,
    get_close_matches_rapidfuzz
    )

from tree_gen import convert_arxml_to_json
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
    workspace_root = Path(__file__).resolve().parents[0].parent
    info(f"Searching for param definition files in workspace: {workspace_root}")
    files = list(workspace_root.glob("**/*[Pp]aram[Dd]ef*.arxml"))
    return files

def get_definition(keyword: str):
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
    
    matches = []

    for paramdef in paramdefs:
        print("=" * 30, f" {str(paramdef).split('/')[-1]} ")
        try:
            data = convert_arxml_to_json(paramdef)
        except Exception:
            continue
        
        # Get keys from JSON data
        keys = list(get_keys(data))
        close_matches = get_close_matches_rapidfuzz(
            keyword,
            keys,
            n=RAPIDFUZZ_NUMBER_OF_RESULTS,
            cutoff=RAPIDFUZZ_CUTOFF
        )

        matches.extend([[str(paramdef), match, score / 100.0] for match, score, _ in close_matches])

    matches = sorted(matches, key=lambda x: (-x[2], x[1]))

    return matches

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
            # data = json.loads(paramdef.read_text())
            data = convert_arxml_to_json(paramdef)
        except Exception:
            continue
        
        # Get keys from JSON data
        keys = get_keys(data)
        close_matches = get_close_matches(keyword, keys, n=DIFFLIB_NUMBER_OF_RESULTS, cutoff=DIFFLIB_CUTOFF)

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

    paths = []
    paramdefs = get_all_paramdef_files()
    for paramdef in paramdefs:
        try:
            data = convert_arxml_to_json(paramdef)
        except Exception:
            continue
        
        # Get keys from JSON data
        keys = list(get_keys(data))
        close_matches = get_close_matches_rapidfuzz(
            keyword,
            keys,
            n=RAPIDFUZZ_NUMBER_OF_RESULTS,
            cutoff=RAPIDFUZZ_CUTOFF
        )

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

if __name__ == "__main__":
    pass