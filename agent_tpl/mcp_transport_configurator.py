"""
Configure MCP transport protocol

Create or update `.vscode/mcp.json` for the VS Code MCP extension using
settings from `mcp_settings.py`.

Implementation details (path handling, placeholders, and examples) are
documented in the `configure_mcp()` and `path_difference()` docstrings.

@author: GUU8HC
"""

import json
import os
import sys
from pathlib import Path
from mcp_settings import SETTINGS, STDIO, SSE, PROTOCOL, PORT, MCP_NAME

def path_difference(base, target):
    """
    Return the relative path from `base` to `target`, or ``None``.

    If `target` is a subpath of `base` returns a relative path string;
    otherwise returns ``None``.
    """

    try:
        return str(Path(target).relative_to(base))
    except ValueError:
        return None

def configure_mcp():
    """
    Create or update `.vscode/mcp.json` for the current workspace.

    Merges the current agent into the `servers` mapping and writes the file.
    """
    # Step 1: Use current working directory (cwd) as the base for .vscode
    try:
        _project_root = os.getcwd()
        _vscode_dir = os.path.join(_project_root, '.vscode')
        os.makedirs(_vscode_dir, exist_ok=True)
    except Exception:
        _vscode_dir = '.vscode'

    mcp_json_path = os.path.join(_vscode_dir, 'mcp.json')
    agent_name = SETTINGS[MCP_NAME]
    
    # Step 2: Load existing mcp.json or start fresh
    if os.path.exists(mcp_json_path):
        try:
            with open(mcp_json_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read {mcp_json_path}: {e}. Creating new config.")
            config = {"servers": {}}
    else:
        config = {"servers": {}}
    
    # Ensure servers key exists
    if "servers" not in config:
        config["servers"] = {}
    
    # Step 3: Check if agent already registered (idempotent)
    if agent_name in config["servers"]:
        print(f"Agent '{agent_name}' already configured in {mcp_json_path}. Skipping.")
        return
    
    # Step 4: Build agent configuration based on protocol
    if SETTINGS[PROTOCOL] == SSE:
        agent_config = {
            "type": "sse",
            "url": f"http://127.0.0.1:{SETTINGS[PORT]}/sse"
        }
        protocol_info = f"SSE transport on port {SETTINGS[PORT]}"
    else:
        # SETTINGS[PROTOCOL] == STDIO
        # Build command using the `${workspaceFolder}` placeholder and forward
        # slashes so VS Code expands consistently across platforms.
        if os.name == 'nt' or sys.platform.startswith('win'):
            python_cmd = '${workspaceFolder}/.venv/Scripts/python.exe'
        else:
            python_cmd = '${workspaceFolder}/.venv/bin/python'

        dir_difference = path_difference(os.getcwd(), os.path.dirname(os.path.abspath(__file__)))

        if dir_difference is not None:
            # Use relative path from {workspaceFolder} to agent script
            agent_path = os.path.join('${workspaceFolder}', dir_difference, 'mcp_server.py')
        else:
            # Fallback to absolute path if relative path not possible
            agent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mcp_server.py')

        agent_config = {
            'command': python_cmd,
            'args': [agent_path],
            'env': {
                'PYTHONPATH': '${workspaceFolder}'
            }
        }
        protocol_info = "STDIO transport"
    
    # Step 5 & 6: Merge agent config into servers and write to file
    config["servers"][agent_name] = agent_config
    with open(mcp_json_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    # Step 7: Print status
    print(f"Configured agent '{agent_name}' for {protocol_info}")
    print(f"Updated {mcp_json_path}")

if __name__ == "__main__":
    configure_mcp()
