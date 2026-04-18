[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/m4tice-python-fastmcp-tpl-badge.png)](https://mseep.ai/app/m4tice-python-fastmcp-tpl)

# AUTOSAR ParamDef MCP Server

An MCP (Model Context Protocol) server for querying AUTOSAR ECUC parameter definitions via GitHub Copilot. Combines FastMCP transport with high-performance binary serialization and indexed search over AUTOSAR configuration models.

## Overview

This project demonstrates how binary snapshots enable fast startup and sub-millisecond queries:

- **Cold start** (first run): Parse ARXML files (~20–30 ms for small models, minutes for full PVERs)
- **Warm start** (subsequent runs): Load binary snapshot (~10 ms), with fingerprint-based cache invalidation
- **Query latency**: Sub-millisecond indexed searches (O(1) type/path, O(vocabulary) fuzzy)

Designed for integration with GitHub Copilot to enable LLM-driven AUTOSAR configuration inspection.

## Features

- High-performance binary serialization with gzip compression (46× smaller than XML)
- Automatic fingerprint-based snapshot validation
- O(1) type/path lookups via pre-built indexes
- Fuzzy search for discovery by approximate name
- STDIO/SSE transport protocols
- Automatic `mcp.json` configuration generation

## Project Structure

```
agent_tpl/
├── mcp_server.py                  # MCP server (FastMCP + tool registration)
├── mcp_settings.py                # Configuration (STDIO/SSE, port, settings)
├── mcp_transport_configurator.py  # Auto-generates .vscode/mcp.json
├── mcp_util.py                    # Tool implementations + snapshot engine
├── paramdef_manager.py            # Serialization, parsing, search engine (LOCAL COPY)
└── __pycache__/                   # (auto-generated)

confrules/
├── Com_EcucParamDef.arxml         # Sample ARXML: Com module
├── PduR_EcucParamDef.arxml        # Sample ARXML: PduR module
└── paramdef.snapshot.bin          # Auto-generated binary snapshot

README.md                            # This file
requirements.txt                     # Python dependencies (fastmcp)
```

## Getting Started

### Prerequisites

- Python 3.9+
- pip

### Installation

1. **Clone or download the project:**
   ```bash
   cd python-fastmcp-tpl
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment:**
   - Windows: `.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the MCP Server

### Start the Server

```bash
python agent_tpl/mcp_server.py
```

This will:
1. Load the ParamDef model from `confrules/*.arxml` (or `paramdef.snapshot.bin` if available)
2. Auto-generate `.vscode/mcp.json` configuration
3. Start the MCP server in STDIO mode (default) or SSE mode

The model stays in memory for the lifetime of the server process.

### Configuration

Edit `agent_tpl/mcp_settings.py` to customize:

```python
SETTINGS = {
    MCP_NAME : "agent_tpl",
    PROTOCOL : STDIO,  # or SSE for HTTP
    PORT     : 5501    # only used if PROTOCOL=SSE
}
```

## MCP Tools

The server exposes 5 tools to GitHub Copilot:

### 1. `paramdef_model_stats`

Get model statistics and load performance.

**Returns:**
- `load_source`: "snapshot" (fast path) or "arxml" (cold start)
- `load_time_ms`: Milliseconds to load the model
- `snapshot_exists`: Whether the binary cache file exists
- `model.stats()`: Containers, parameters, vocabulary size, etc.

**Use case:** Understand the serialization advantage—compare load_source values across server restarts.

### 2. `paramdef_fuzzy_search`

Fuzzy search across all container, parameter, and reference short names.

**Parameters:**
- `query` (str): Search term (e.g., "pdu", "timeout", "nds ecu")
- `limit` (int, default 10): Max results to return

**Returns:**
- `results[]`: Array of `{term, score}` sorted by similarity (0.0–1.0)
- `search_time_us`: Microseconds to execute

**Use case:** Discover container names when you only know an approximation.

```
Examples:
  "pdu"      → ComIPdu, PduR, PduRRoutingTable, …
  "timeout"  → ComMainFunctionRxPeriod, …
  "nds ecu"  → rba_Nds_EcuInstanceFRef (fuzzy match)
```

### 3. `paramdef_search_by_type`

O(1) index lookup by container definition type (short name).

**Parameters:**
- `container_type` (str): Container type name (e.g., "ComConfig", "ComIPdu")
- `short_name` (str, optional): Narrow results to a specific instance

**Returns:**
- Full container details: parameters, references, sub-containers, multiplicity
- `search_time_us`: Query latency (typically < 10 µs)

### 4. `paramdef_search_by_path`

Search by full or partial slash-separated definition path.

**Parameters:**
- `definition_path` (str): Path segment(s) (e.g., "Com/ComConfig/ComIPdu")

**Returns:**
- Containers matching the path (bottom-up index, O(1) lookup on last segment)

**Use case:** When you have a definition path from an RQ1 defect entry or other structured source.

### 5. `paramdef_list_containers`

Browse top-level containers grouped by module (discovery tool).

**Parameters:**
- `module_name` (str, optional): Filter by module (e.g., "Com", "PduR")

**Returns:**
- List of containers with parameter count, reference count, child count
- Useful when you don't yet know which container types exist

## Working with paramdef_manager.py

`agent_tpl/paramdef_manager.py` is a standalone CLI tool for parsing, serializing, and querying AUTOSAR models.

### CLI Usage

#### 1. Parse ARXML and Create Snapshot

```bash
python agent_tpl/paramdef_manager.py parse confrules/Com_EcucParamDef.arxml confrules/PduR_EcucParamDef.arxml -o confrules/paramdef.snapshot.bin
```

**Options:**
- `files`: One or more `.arxml` file paths
- `-o, --output`: Output snapshot path (default: `paramdef_snapshot.bin`)
- `--no-compress`: Skip gzip compression (default: enabled)

**Output:**
- Parsed model statistics (modules, containers, parameters, vocabulary)
- Snapshot file with compression ratio and serialization time

#### 2. Load and Inspect a Snapshot

```bash
python agent_tpl/paramdef_manager.py load confrules/paramdef.snapshot.bin --tree --depth 2
```

**Options:**
- `snapshot`: Snapshot file path
- `--tree`: Print container hierarchy tree
- `--depth`: Max tree depth to display (default: full tree)

#### 3. Search by Container Type

```bash
python agent_tpl/paramdef_manager.py search confrules/paramdef.snapshot.bin --type ComConfig
```

**Options:**
- `--type`: Container type name
- `--name`: Instance short name (optional filter)
- `--path`: Definition path (alternative to --type)

**Examples:**
```bash
# Find all ComIPdu containers
python agent_tpl/paramdef_manager.py search confrules/paramdef.snapshot.bin --type ComIPdu

# Find a specific signal
python agent_tpl/paramdef_manager.py search confrules/paramdef.snapshot.bin --type ComSignal --name Sig_ESP_Speed
```

#### 4. Fuzzy Search

```bash
python agent_tpl/paramdef_manager.py fuzzy confrules/paramdef.snapshot.bin --query "pdu timeout" --limit 20
```

**Options:**
- `--query`: Search term
- `--limit`: Max results (default: 10)

#### 5. Benchmark: Parse vs Deserialize

```bash
python agent_tpl/paramdef_manager.py benchmark confrules/Com_EcucParamDef.arxml confrules/PduR_EcucParamDef.arxml --runs 5
```

**Output:**
- XML parse time (average and min)
- Binary deserialize time (average and min)
- Speedup factor (parse_time / deserialize_time)
- Snapshot compression ratio

**Example output:**
```
  source_files        2
  source_size_kb      777.4
  snapshot_size_kb    16.8
  compression_ratio   46.3
  parse_avg_ms        19.2
  deserialize_avg_ms  3.5
  speedup_factor      5.5
```

#### 6. Compute File Fingerprint

```bash
python agent_tpl/paramdef_manager.py fingerprint confrules/Com_EcucParamDef.arxml confrules/PduR_EcucParamDef.arxml
```

**Output:**
- SHA-256 fingerprint over sorted file contents (used for cache invalidation)

### Understanding the Serialization

**Cold start (no snapshot):**
1. `ParamDefParser.parse_files(...)` reads and parses ARXML files
2. Builds in-memory model + indexes (type index, name index, vocabulary)
3. `serialize(model, output_path)` writes:
   - 8-byte magic: `"ARSNAP01"`
   - 4-byte version: `0x00000001`
   - gzip-compressed pickle of the model

**Warm start (snapshot exists):**
1. `deserialize(snapshot_path)` reads magic + version + decompresses
2. Computes fingerprint of current ARXML files
3. Compares with snapshot's fingerprint:
   - Match → fast path, deserialize in ~10 ms
   - Mismatch → cold start (files changed)

**Fingerprint validation:**
- Prevents stale snapshots from being used after ARXML changes
- Ensures correctness without explicit timestamp tracking

## Advanced: Integration with mcp_util

The `_ParamDefEngine` singleton in `mcp_util.py` automates the snapshot strategy:

```python
class _ParamDefEngine:
    def initialize(self):
        # 1. Try snapshot (fast path)
        if snapshot_path.exists():
            candidate = deserialize(snapshot_path)
            if candidate.fingerprint == current_fingerprint:
                return candidate  # Success: ~10 ms
        
        # 2. Parse ARXML (cold start)
        model = parser.parse_files(arxml_paths)
        serialize(model, snapshot_path)  # Auto-save for next startup
        return model
```

This ensures:
- **First startup**: Parse ARXML, auto-save snapshot
- **Subsequent startups**: Load snapshot (fast)
- **Automatic invalidation**: If ARXML files change, cold start is triggered

## Transport Protocols

### STDIO (Default)
- Standard input/output for local process integration
- Suitable for VS Code MCP extension
- Configuration is auto-generated in `.vscode/mcp.json`

### SSE (Server-Sent Events)
- HTTP-based communication
- Change `PROTOCOL: SSE` in `mcp_settings.py`
- Useful for remote clients or cross-platform testing

## Project Independence

This project is self-contained:
- ✅ All Python modules are local (in `agent_tpl/`)
- ✅ No external file references
- ✅ Can be relocated to any directory without breaking imports
- ✅ All paths use `Path(__file__).resolve().parent` for portability

## Sample Workflow

1. **Start the server:**
   ```bash
   python agent_tpl/mcp_server.py
   ```
   Output:
   ```
   Load source: snapshot
   Load time: 10.57 ms
   Snapshot: True
   ```

2. **In VS Code with Copilot MCP extension enabled:**
   ```
   @agent_tpl
   What parameters does the Com module have?
   ```
   Copilot calls: `paramdef_list_containers("Com")`

3. **Copilot discovers container names:**
   ```
   Com/ComConfig - 3 children, 28 params
   ```

4. **Query specific containers:**
   ```
   @agent_tpl
   Show me all ComIPdu containers and their parameters.
   ```
   Copilot calls: `paramdef_search_by_type("ComIPdu")`

5. **Fuzzy discovery:**
   ```
   @agent_tpl
   What's the timeout parameter called?
   ```
   Copilot calls: `paramdef_fuzzy_search("timeout")`

## Troubleshooting

### Snapshot not being used

**Symptom:** `load_source: "arxml"` on every startup

**Solution:** Check the fingerprint:
```bash
python agent_tpl/paramdef_manager.py fingerprint confrules/*.arxml
```
Compare with the snapshot's fingerprint (visible via `paramdef_model_stats`).
If different, the source files changed → re-create the snapshot.

### "No .arxml files found"

**Symptom:** Error during startup

**Solution:** Ensure ARXML files are in `confrules/` directory:
```bash
ls confrules/*.arxml
```

### Import errors

**Symptom:** `ModuleNotFoundError: No module named 'paramdef_manager'`

**Solution:** `paramdef_manager.py` must be in `agent_tpl/` (local copy). Verify:
```bash
ls agent_tpl/paramdef_manager.py
```

### Port already in use (SSE mode)

**Solution:** Change `PORT` in `agent_tpl/mcp_settings.py`.

## Performance Metrics

Typical performance on small models (2 modules, 44 containers):

| Operation | Time |
|-----------|------|
| XML parse (cold start) | ~20 ms |
| Snapshot deserialize | ~10 ms |
| Type search (indexed) | < 10 µs |
| Path search (indexed) | < 10 µs |
| Fuzzy search (100 terms) | ~1–2 ms |

Snapshot file size: ~17 KB compressed (46× compression vs ARXML)

## References

- [AUTOSAR Standard](https://www.autosar.org/)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jloong/fastmcp)
- [GitHub Copilot Extensions](https://docs.github.com/en/copilot/managing-copilot/managing-copilot-business/enabling-copilot-business-in-your-organization)

## License

This project is provided as-is for educational and development purposes.

## Authors

- **GUU8HC** — FastMCP template foundation
- **Nguyen Duc Tuan** — ParamDef serialization, indexing, and MCP integration
