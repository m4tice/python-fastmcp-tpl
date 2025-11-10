"""
MCP Server
@author: GUU8HC
"""

from fastmcp import FastMCP

from mcp_transport_configurator import configure_mcp
from mcp_settings import SETTINGS, PROTOCOL, STDIO, SSE, PORT
from mcp_util import (
    get_precise_time,
    get_definition,
    get_definition_path_difflib,
    get_definition_path_rapidfuzz
)


# create application
app = FastMCP()


# Tool listing
@app.tool()
def get_precise_time():
    """
    MCP wrapper
    """
    return get_precise_time()

@app.tool(
        description="""
        Get information such as parameter definition, definition path, etc.
        for a given keyword from param definition JSON files.
        """
)
def get_generic_knowledge_from_keyword(keyword: str):
    """
    Get generic knowledge such as parameter definition, definition path, multiplicity, etc.
    for a given keyword from param definition JSON files.
    """
    return get_definition(keyword)

@app.tool(
        description="""
        Get definition path, etc. for a given keyword using DiffLib.
        Number of results and cutoff can be adjusted.
        Default is 1 result, increased number may return multiple close matches.
        Default cutoff 0.6.
        """
)
def get_precise_definition_path_using_difflib(keyword: str):
    """
    Retrieve definition paths and metadata for a given keyword using difflib fuzzy matching.
    
    This function is designed for Model Context Protocol (MCP) integration to provide
    intelligent code navigation and definition lookup capabilities. It performs fuzzy
    string matching to find the most relevant definition paths for the specified keyword.
    
    Args:
        keyword (str): The search term or identifier to find definitions for.
    
    Returns:
        The return value from get_definition_path() containing definition paths and
        associated metadata for the matched keyword(s).
    
    Note:
        This function serves as a user-friendly wrapper around get_definition_path()
        with sensible defaults for MCP tool integration. Adjust number_of_results
        and cutoff parameters based on your use case requirements for precision vs recall.
    """
    return get_definition_path_difflib(keyword)

@app.tool(
        description="""
        Get definition path, etc. for a given keyword using RapidFuzz.
        Number of results and cutoff can be adjusted.
        Default is 1 result, increased number may return multiple close matches.
        Default cutoff 0.6.
        """
)
def get_precise_definition_path_using_rapidfuzz(keyword: str):
    """
    Retrieve definition paths and metadata for a given keyword using RapidFuzz fuzzy matching.
    
    This function is designed for Model Context Protocol (MCP) integration to provide
    intelligent code navigation and definition lookup capabilities. It performs fuzzy
    string matching to find the most relevant definition paths for the specified keyword.
    
    Args:
        keyword (str): The search term or identifier to find definitions for.
    
    Returns:
        The return value from get_definition_path() containing definition paths and
        associated metadata for the matched keyword(s).
    """
    return get_definition_path_rapidfuzz(keyword)

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
