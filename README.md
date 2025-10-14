[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/m4tice-python-fastmcp-tpl-badge.png)](https://mseep.ai/app/m4tice-python-fastmcp-tpl)

# Python FastMCP Template

A template for creating Model Context Protocol (MCP) servers using Python and FastMCP.

## Overview

This template provides a foundation for building MCP servers with support for two transport protocols:
- **STDIO** (default) - Standard input/output communication
- **SSE** - Server-Sent Events over HTTP

## Features

- Easy configuration switching between STDIO and SSE protocols
- Automatic `mcp.json` configuration generation
- Example tool implementation (`mcp_get_precise_time`)
- Clean project structure with modular components

## File Structure

```
├── mcp_server.py                    # Main MCP server application
├── mcp_settings.py                  # Configuration settings
├── mcp_transport_configurator.py    # Auto-configures mcp.json
├── mcp_util.py                      # Utility functions (add your tools here)
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure transport protocol:**
   Edit `mcp_settings.py` to choose your transport protocol:
   ```python
   SETTINGS = {
       PROTOCOL : STDIO,  # or SSE
       PORT     : "5500"  # only used for SSE
   }
   ```

## Transport Protocols

### STDIO (Default)
- Uses standard input/output for communication
- Suitable for direct integration with clients that support process spawning
- Configuration is automatically generated for VS Code MCP extension

### SSE (Server-Sent Events)
- HTTP-based communication using Server-Sent Events
- Runs on configurable port (default: 5500)
- Suitable for web-based integrations or when firewall restrictions apply

## Running the Server

### Method 1: Direct execution (Recommended)
```bash
python mcp_server.py
```
This will:
1. Automatically configure the appropriate `mcp.json` file
2. Start the server with the selected transport protocol

### Method 2: Configuration only
To just update the `mcp.json` configuration without starting the server:
```bash
python mcp_transport_configurator.py
```

## Configuration Files

The server automatically generates `.vscode/mcp.json` based on your protocol choice:

### STDIO Configuration
```json
{
    "servers": {
        "my-mcp-server": {
            "command": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
            "args": ["mcp_server.py"],
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        }
    }
}
```

### SSE Configuration
```json
{
    "servers": {
        "my-sse-mcp-server": {
            "type": "sse",
            "url": "http://127.0.0.1:5500/sse"
        }
    }
}
```

## Adding Your Own Tools

1. Implement your functions in `mcp_util.py`
2. Add MCP tool wrappers in `mcp_server.py` using the `@app.tool()` decorator

Example:
```python
# In mcp_util.py
def my_custom_function(param1, param2):
    """Your custom logic here"""
    return f"Result: {param1} + {param2}"

# In mcp_server.py
@app.tool()
def my_custom_tool(param1: str, param2: str):
    """
    Description of what this tool does
    """
    return my_custom_function(param1, param2)
```

## Troubleshooting

### Common Issues

1. **Port already in use (SSE mode):**
   - Change the port in `mcp_settings.py`
   - Check if another service is using the port

2. **Python path issues (STDIO mode):**
   - Ensure you're using a virtual environment
   - Verify the Python path in the generated `mcp.json`

3. **Module import errors:**
   - Check that all dependencies are installed
   - Verify PYTHONPATH is set correctly

### Logs and Debugging

- STDIO mode: Check VS Code MCP extension logs
- SSE mode: Server logs are printed to console

## Sample prompt

```Tell me the precise time (using MCP Tools).```

## License

This template is provided as-is for educational and development purposes.

## Author

GUU8HC
