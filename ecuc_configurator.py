"""
@author GUU8HC
"""

import json
from pathlib import Path

from generic_utils import info, debug, error, export2json
from sie_settings import DEBUG

class ECUCConfigurator:
    """
    A generator class for ECUC configuration generation in JSON format.
    """
    def __init__(self):
        pass

    def __decide_name(self, part, names):
        """
        Decide the name for a given part based on provided names dictionary.
        If the part exists in names, use the corresponding name;
        otherwise, use the part itself
        """
        if part in names.keys():
            name = names[part]
            if DEBUG:
                debug(f"Found name '{name}' for part '{part}'")
        else:
            name = part
            if DEBUG:
                debug(f"No name found for part '{part}', using default '{name}'")
        return name

    def configure(self, path: str, names: dict):
        parts = list(filter(None, path.split('/')))[::-1]
        dict = {}

        # Traverse parts in reverse order
        # Build nested structure bottom-up so children become values of parents
        current = {}
        for idx, part in enumerate(parts):
            # Check if part exists in given names (rename leafs if mapping provided)
            name = self.__decide_name(part, names)

            # create node for this part
            node = {name: {"type": part}}

            # if we already have a child subtree, attach it under this node
            if current:
                # merge existing subtree into this node's value
                node[name].update(current)

            # current becomes the newly created node for next iteration
            current = node

        # wrap under top-level 'ecuc' key to match samples.json structure
        if current:
            dict = {"ecuc": current}

        # return the ecuc root directly
        return dict

    def _deep_merge(self, a: dict, b: dict) -> dict:
        """Merge dict b into a recursively and return the result (a mutated).

        For keys present in both dicts:
        - if both values are dicts, merge recursively
        - otherwise, b's value overwrites a's
        """
        for k, v in b.items():
            if k in a and isinstance(a[k], dict) and isinstance(v, dict):
                self._deep_merge(a[k], v)
            else:
                a[k] = v
        return a

    def save_or_merge(self, filename: str, config: dict) -> None:
        """Save `config` to `filename`. If the file exists, load and merge first."""
        out_path = Path(filename)
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
            except Exception as e:
                error(f"Failed to read existing JSON '{out_path}': {e}")
                existing = {}

            merged = self._deep_merge(existing, config)
            export2json(filename, merged, use_tabs=True)
        else:
            export2json(filename, config, use_tabs=True)


if __name__ == "__main__":
    json_filename = "ecuc_config.json"
    configurator = ECUCConfigurator()
    config = configurator.configure("/com/comconfig/comipdu", {"comipdu": "ESP_19", "comconfig": "ComConfig_0"})
    # error(config)

    # Save or merge generated config into the JSON file
    configurator.save_or_merge(json_filename, config)