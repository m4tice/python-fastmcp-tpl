"""
MCP Server
@author: GUU8HC
"""

from fastmcp import FastMCP

from mcp_util import get_precise_time
from mcp_settings import SETTINGS, PROTOCOL, STDIO, SSE, PORT
from mcp_transport_configurator import configure_mcp


# create application
app = FastMCP()


# Tool listing
@app.tool()
def mcp_get_precise_time():
    """
    MCP wrapper
    """
    return get_precise_time()


if __name__ == "__main__":
    # Reconfigure mcp.json
    configure_mcp()

    # Run server
    if SETTINGS[PROTOCOL] == SSE:
        # SSE
        app.run(transport=SSE, port=SETTINGS[PORT])
    else:
        # STDIO
        app.run()
