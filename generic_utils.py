"""
@author guu8hc
Utilities
"""

import json

from rapidfuzz import process, fuzz


def info(message):
    """
    print with [INFO] prefix in cyan
    """
    print(f"\033[96m[INFO]  {message}\033[0m")

def debug(message):
    """
    print with [DEBUG] prefix in dark yellow
    """
    print(f"\033[93m[DEBUG] {message}\033[0m")

def error(message):
    """
    print with [ERROR] prefix in red
    """
    print(f"\033[91m[ERROR] {message}\033[0m")

def export2json(filename, data, indent: int = 2, use_tabs: bool = False):
    # Convert VersionObject instances to dictionaries for JSON serialization
    if isinstance(data, list):
        result_dict = [item.model_dump() if hasattr(item, 'model_dump') else item for item in data]
    else:
        result_dict = data.model_dump() if hasattr(data, 'model_dump') else data
    
    # Export history to JSON file
    with open(filename, "w") as f:
        if not use_tabs:
            json.dump(result_dict, f, indent=indent)
        else:
            # Preferred: pass a tab string as indent (Python 3.11+ supports string indent)
            try:
                json.dump(result_dict, f, indent="\t")
            except TypeError:
                # Fallback for older Python: dump with numeric indent then replace leading spaces
                s = json.dumps(result_dict, indent=indent)
                import re

                def _spaces_to_tabs(match):
                    spaces = match.group(0)
                    count = len(spaces)
                    tabs = count // indent
                    rem = count % indent
                    return "\t" * tabs + " " * rem

                s = re.sub(r'(?m)^( +)', _spaces_to_tabs, s)
                f.write(s)
    info(f"Exported successfully to {filename}")

def get_keys(data: dict) -> set:
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

def get_close_matches_rapidfuzz(keyword: str, keys: list, n: int, cutoff: float):
    close_matches = process.extract(
            keyword,
            keys,
            scorer=fuzz.WRatio,
            limit=n,
            score_cutoff=int(cutoff * 100)
        )
    
    # Sorting from highest to lowest score
    return sorted(close_matches, key=lambda x: (-x[1], x[0]))

def test_utils():
    info("This is an info message.")
    debug("This is a debug message.")
    error("This is an error message.")

if __name__ == "__main__":
    test_utils()