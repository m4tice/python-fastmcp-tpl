"""
Configure MCP transport protocol

This script updates the mcp.json file based on the protocol setting in
`mcp_settings.py`. The configurator writes `.vscode/mcp.json` under the
current working directory (cwd). The README and inline comments explain that
the generated configuration uses the `${cwd}` placeholder so VS Code resolves
paths relative to the directory where the user runs the project. The
configuration generation supports both Windows and macOS/Linux conventions
for virtual environment layout.

Notes:
- The implementation writes to ``./.vscode/mcp.json`` (cwd/.vscode/mcp.json).
- For STDIO mode the generated `command`/`args` will reference the venv
    executable path appropriate for the OS (``.venv\Scripts\python.exe`` on
    Windows, ``.venv/bin/python`` on macOS/Linux).

Only documentation and comments are updated here to describe the behavior.

@author: GUU8HC
"""

import json
import os
import sys
from pathlib import Path
from mcp_settings import SETTINGS, STDIO, SSE, PROTOCOL, PORT, MCP_NAME

def path_difference(base, target):

    try:
        return str(Path(target).relative_to(base))
    except ValueError:
        return None

def configure_mcp():
    """
    Configure the MCP transport protocol in mcp.json
    Merges with existing configuration if present (supports multiple agents)
    
     Steps:
     1. Use the current working directory (cwd) and create ``.vscode`` there if
         missing. The generated `mcp.json` uses `${cwd}` placeholders so VS Code
         resolves paths relative to where the user runs the project.
     2. Load existing mcp.json if it exists; otherwise start with empty servers dict
     3. Check if current agent is already registered in mcp.json
         - If yes: skip (idempotent, avoid duplicates)
         - If no: continue to step 4
     4. Build agent configuration based on PROTOCOL setting:
         - SSE: add type="sse" and url with port from settings
         - STDIO: produce a `command` and `args` that reference `${cwd}` and pick
            the correct virtualenv Python executable for the OS (Windows vs macOS/Linux)
     5. Merge new agent config into existing servers dict
     6. Write updated mcp.json with all registered agents (no conflicts)
     7. Print status: agent name, protocol, and file path updated
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
        # Build paths using os.path.join so they are correct per-OS.
        if os.name == 'nt' or sys.platform.startswith('win'):
            python_cmd = os.path.join('${workspaceFolder}', '.venv', 'Scripts', 'python.exe')
        else:
            python_cmd = os.path.join('${workspaceFolder}', '.venv', 'bin', 'python')

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
