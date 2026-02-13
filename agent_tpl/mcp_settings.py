"""
MCP settings
@author: GUU8HC
"""

# <DO NOT CHANGE> ========================================
STDIO = "stdio"                    # IMPORTANT # IMPORTANT               
SSE = "sse"                        # IMPORTANT # IMPORTANT
MCP_NAME = "MCP_NAME"              # IMPORTANT # IMPORTANT
PROTOCOL = "PROTOCOL"              # IMPORTANT # IMPORTANT
PORT = "PORT"                      # IMPORTANT # IMPORTANT
# </DO NOT CHANGE> =======================================


#=========================================================
#========== FEEL FREE TO MODIFY BELOW THIS LINE ==========
#=========================================================

# MCP settings
SETTINGS = {
    MCP_NAME : "agent_tpl",
    PROTOCOL : STDIO,
    PORT     : 5501
}

# Database path - set to None to use environment variable WORKUNIT_DB_PATH
# Or provide absolute path to .db3 file
DATABASE_PATH = None

# Other settings
DEBUG = True
EXPORT_JSON = True
