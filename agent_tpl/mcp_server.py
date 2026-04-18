"""
MCP Server
@author: GUU8HC
"""

from fastmcp import FastMCP

from mcp_util import (
    get_precise_time,
    tool_model_stats,
    tool_fuzzy_search,
    tool_search_by_type,
    tool_search_by_path,
    tool_list_containers,
)
from mcp_settings import SETTINGS, PROTOCOL, STDIO, SSE, PORT
from mcp_transport_configurator import configure_mcp


# create application
app = FastMCP()


@app.tool()
def mcp_get_precise_time():
    """Get the precise current time up to microsecond precision."""
    return get_precise_time()


@app.tool()
def paramdef_model_stats():
    """
    Get AUTOSAR ParamDef model statistics and startup load performance.

    Returns model stats (modules, containers, parameters, vocabulary) plus
    how the model was loaded:
      - 'snapshot': fast binary deserialize (typically 3–5 ms)
      - 'arxml'   : cold XML parse (tens of milliseconds for small models,
                    minutes for full PVERs with ~100 files)

    Call this first to understand what data is loaded and observe the
    serialization speed advantage.
    """
    return tool_model_stats()


@app.tool()
def paramdef_fuzzy_search(query: str, limit: int = 10):
    """
    Fuzzy search across all container, parameter, and reference short names.

    Use this when you only know an approximate name or a natural-language
    fragment.  Returns ranked matches with similarity scores (0.0–1.0).
    Sub-string matches are boosted.

    Examples:
      query="pdu"       → ComIPdu, PduR, PduRRoutingTable, …
      query="timeout"   → ComMainFunctionRxPeriod, …
      query="nds ecu"   → rba_Nds_EcuInstanceFRef  (fuzzy match)
    """
    return tool_fuzzy_search(query, limit)


@app.tool()
def paramdef_search_by_type(container_type: str, short_name: str = None):
    """
    Search containers by their exact definition type (short name in schema).

    O(1) index lookup — returns full details including all parameters and
    references.  Optionally narrow results to a specific instance short name.

    Examples:
      container_type="ComIPdu"   → all ComIPdu container definitions
      container_type="ComConfig" → the top-level ComConfig container
      container_type="ComSignal", short_name="Sig_ESP_Speed" → one signal
    """
    return tool_search_by_type(container_type, short_name)


@app.tool()
def paramdef_search_by_path(definition_path: str):
    """
    Search containers by full or partial slash-separated definition path.

    Use this when you have a definition path from an RQ1 defect entry or
    another structured source.

    Examples:
      "Com/ComConfig/ComIPdu"
      "PduR/PduRRoutingTables/PduRRoutingTable"
    """
    return tool_search_by_path(definition_path)


@app.tool()
def paramdef_list_containers(module_name: str = None):
    """
    List top-level containers grouped by module.

    Use for discovery when you don't yet know which container types exist.
    Optionally filter by module name (e.g., 'Com' or 'PduR').
    Each entry includes parameter count, reference count, and child count.
    """
    return tool_list_containers(module_name)


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
