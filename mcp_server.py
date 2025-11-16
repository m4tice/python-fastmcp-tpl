"""
MCP Server
@author: GUU8HC
"""

from fastmcp import FastMCP

from mcp_transport_configurator import configure_mcp
from mcp_settings import SETTINGS, PROTOCOL, STDIO, SSE, PORT
from mcp_util import get_precise_time
from tree_gen import convert_arxml_to_json
from paramdef_utils import (
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
        Provide response instructions for a given prompt.
        """)
def provide_response_instructions():
    """
    Provide response instructions for a given prompt.
    """
    instructions = """
    When responding to prompts, please adhere to the following guidelines:
    1. Clarity: Ensure your responses are clear and easy to understand.
    2. Conciseness: Keep your answers brief and to the point, avoiding unnecessary details.
    3. Relevance: Stay focused on the topic of the prompt and avoid deviating into unrelated areas.
    4. Accuracy: Provide correct and reliable information based on your training data.
    5. Tone: Maintain a professional and respectful tone in all responses.
    6. Structure: Organize your answers logically, using paragraphs or bullet points where appropriate.
    7. Examples: Include examples to illustrate complex points when necessary.
    8. Avoid Jargon: Use simple language and avoid technical jargon unless specifically requested.
    9. Engagement: Encourage further discussion or questions if applicable.
    10. Ethical Considerations: Ensure that your responses adhere to ethical guidelines and do not promote harmful behavior.
    11. Don't return raw JSON unless explicitly asked. Format the response in a user-friendly manner.
    12. When providing code snippets, ensure they are properly formatted and include necessary context for understanding.
    13. Keep the answer simple, but not oversimplified. Provide enough detail to be informative without overwhelming the user.
    14. Don't provide shell commmands unless explicitly asked.
    """
    return instructions

@app.tool(
        description="""
        Get the file contains generic knowledge
        such as parameter definition, definition path, multiplicity, etc.
        for a given keyword from param definition JSON files.
        """
)
def get_definition_file_from_keyword(keyword: str):
    """
    Get the file contains generic knowledge such as parameter definition, definition path, multiplicity, etc.
    for a given keyword from param definition JSON files.
    """
    return get_definition(keyword)

@app.tool(
        description="""
        Parse ARXML file to JSON.
        """
)
def parse_arxml_to_json(file_path: str):
    """
    Parse ARXML file to JSON.
    """
    json_data = convert_arxml_to_json(file_path)
    return json_data

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
