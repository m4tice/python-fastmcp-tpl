# Software Requirements & Architecture Documentation

## Project Overview

**AUTOSAR ParamDef MCP Server** is a Python-based integration tool that enables GitHub Copilot to query AUTOSAR ECUC (Electronic Control Unit Configuration) parameter definitions efficiently. It combines Model Context Protocol (MCP) standards with high-performance binary serialization to provide sub-millisecond indexed searches over AUTOSAR configuration models.

### Key Innovation
The project solves a critical performance problem: traditional ARXML parsing is slow (20-30 ms for small files, minutes for full AUTOSAR models). This solution uses binary snapshots with automatic fingerprint-based cache invalidation, achieving:
- **Cold start** (~30 ms): Parse ARXML files once
- **Warm start** (~10 ms): Load binary snapshot on subsequent runs
- **Query latency**: Sub-millisecond indexed lookups (O(1) for type/path search, O(vocabulary size) for fuzzy search)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Copilot                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              MCP Server (FastMCP)                                 │
│  - Registered Tools (6 functions exposed via MCP)               │
│  - Tool Registration & Request Routing                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│           MCP Tool Implementations (mcp_util.py)                │
│  - In-memory Engine with snapshot-first loading strategy       │
│  - Tool adapters that call ParamDefModel search functions      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│     ParamDef Model & Search Engine (paramdef_manager.py)        │
│  - Serialization/Deserialization (binary snapshots)            │
│  - ARXML Parsing (with recursive container extraction)         │
│  - Indexed Search (type/path/fuzzy)                            │
│  - Configuration Models (ParamDef, ContainerDef, ModuleDef)   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              Configuration Files (confrules/)                    │
│  - Com_EcucParamDef.arxml (AUTOSAR Com module)                 │
│  - PduR_EcucParamDef.arxml (AUTOSAR PduR module)               │
│  - paramdef.snapshot.bin (Auto-generated binary snapshot)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Organization & Responsibilities

### `mcp_server.py`
**Purpose:** Entry point for the MCP server. Registers tool handlers and launches the server.

**Key Functions:**
- `mcp_get_precise_time()` - Returns current time in microsecond precision
- `paramdef_model_stats()` - Returns model statistics and load performance info
- `paramdef_fuzzy_search(query, limit)` - Fuzzy search across all short names
- `paramdef_search_by_type(container_type, short_name)` - O(1) type-based search
- `paramdef_search_by_path(definition_path)` - Slash-separated path search
- `paramdef_list_containers(module_name)` - Browse top-level containers by module

**Design Pattern:** Each function is decorated with `@app.tool()` to expose it to the MCP client (GitHub Copilot). The functions delegate to implementations in `mcp_util.py`.

---

### `mcp_settings.py`
**Purpose:** Centralized configuration management for the MCP server.

**Configuration Options:**
- `MCP_NAME`: Server name ("agent_tpl")
- `PROTOCOL`: Transport mode ("stdio" or "sse")
- `PORT`: Server port (5501, only used for SSE)
- `DEBUG`: Debug mode flag
- `DATABASE_PATH`: Optional database path (currently unused)
- `EXPORT_JSON`: JSON export flag

**Design:** Settings are stored in a `SETTINGS` dictionary as constants to prevent accidental modification.

---

### `mcp_transport_configurator.py`
**Purpose:** Auto-generates `.vscode/mcp.json` configuration for VS Code MCP extension integration.

**Key Function:** `configure_mcp()`
- Reads current settings from `mcp_settings.py`
- Creates or updates `.vscode/mcp.json`
- Handles both STDIO and SSE transport protocols
- Uses workspace-relative paths with `${workspaceFolder}` placeholder
- Idempotent: skips if agent already registered

**Auxiliary Function:** `path_difference(base, target)`
- Computes relative paths from base to target
- Returns `None` if target is not under base

---

### `mcp_util.py`
**Purpose:** Bridge between MCP server tools and the ParamDef model. Implements the engine singleton pattern for efficient model loading.

**Classes:**
- `_ParamDefEngine` - Singleton that holds the in-memory ParamDefModel
  - **Strategy:** Snapshot-first loading with fingerprint-based invalidation
  - **Initialization:** On first import, loads or parses AUTOSAR data
  - **Auto-save:** After cold parse, saves snapshot for next startup

**Key Functions:**
- `tool_model_stats()` - Returns model statistics and load source info
- `tool_fuzzy_search(query, limit)` - Delegates to `paramdef_manager.fuzzy_search()`
- `tool_search_by_type(container_type, short_name)` - Delegates to `paramdef_manager.search_by_type()`
- `tool_search_by_path(definition_path)` - Delegates to `paramdef_manager.search_by_path()`
- `tool_list_containers(module_name)` - Filters and returns top-level containers
- `get_precise_time()` - Returns current datetime

**Configuration:**
- `_CONFRULES_DIR`: Path to ARXML files (`confrules/`)
- `_SNAPSHOT_PATH`: Path to binary snapshot (`confrules/paramdef.snapshot.bin`)
- `_MAX_RESULTS`: Result capping (20) to keep responses token-friendly

---

### `paramdef_manager.py`
**Purpose:** Core engine for AUTOSAR ParamDef model management. Handles parsing, serialization, indexing, and searching.

#### Data Model Classes

**`ParamDef`** - Represents a single parameter definition
- `short_name`: Parameter identifier
- `param_type`: One of: integer, boolean, enumeration, string, float, function-name, linker-symbol, add-info
- `description`: Semantic description from ARXML
- `default_value`, `min_value`, `max_value`: Value constraints
- `enum_literals`: List of allowed values (for enumerations)
- `multiplicity`: [lower..upper] cardinality bounds

**`ReferenceDef`** - Represents a reference to another container or type
- `short_name`: Reference identifier
- `ref_type`: One of: reference, foreign-reference, choice-reference, symbolic-name, uri-reference, instance-reference
- `dest_ref`: Target reference path
- `dest_type`: Type of the destination

**`ContainerDef`** - Represents a container (the primary organizational unit in AUTOSAR)
- `short_name`: Container name
- `definition_path`: Full path from root (e.g., "Com/ComConfig/ComIPdu")
- `parameters`: List of `ParamDef` objects
- `references`: List of `ReferenceDef` objects
- `sub_containers`: Child containers
- `choice_containers`: Alternative choice containers
- `multiplicity`: Cardinality [lower..upper]
- Methods:
  - `all_children()`: Returns sub_containers + choice_containers
  - `depth()`: Returns distance from root (recursive traversal)
  - `path_segments()`: Splits definition_path into segments

**`ModuleDef`** - Represents an AUTOSAR module (e.g., Com, PduR)
- `short_name`: Module identifier (e.g., "Com")
- `description`: Module purpose
- `category`: AUTOSAR category classification
- `version`: Version from ADMIN-DATA
- `containers`: Top-level containers in this module

**`ParamDefModel`** - The complete parsed model from one or more ARXML files
- `modules`: List of `ModuleDef` objects
- `source_files`: Absolute paths to parsed ARXML files
- `fingerprint`: SHA-256 hash of file contents (used for cache validation)
- `parse_time_s`: Time to parse files
- `created_at`: Timestamp of model creation
- Search indexes (built post-parse):
  - `_type_index`: Maps container type → list of containers (O(1) lookup)
  - `_name_index`: Maps short name → containers
  - `_all_containers`: Flat list of all containers
  - `_vocabulary`: Sorted list of all unique short names (for fuzzy search)
- Method: `stats()` - Returns statistics dict with module/container/parameter counts

#### Parser Class

**`ParamDefParser`** - Parses AUTOSAR ECUC ParamDef ARXML files

**Tag Mappings:**
- `PARAM_TAG_MAP`: Maps ARXML parameter types to string identifiers
- `REF_TAG_MAP`: Maps ARXML reference types to string identifiers

**Key Methods:**
- `_text(el, tag)`: Extract text from child element (safe, returns empty string if not found)
- `_desc(el)`: Extract description from DESC/L-2 element
- `_parse_param(el, param_type)`: Recursively parse parameter definition, including enum literals and constraints
- `_parse_reference(el, ref_type)`: Parse reference definition with destination info
- `_parse_container(el, parent_path)`: Recursively parse container with children (sub-containers and choice containers)
- `_parse_module(el)`: Parse top-level ECUC-MODULE-DEF element
- `parse_file(filepath)`: Parse single ARXML file and return list of ModuleDefs
- `parse_files(filepaths)`: Parse multiple files, build indexes, return unified ParamDefModel

**Algorithm:**
1. Open each ARXML file and parse as XML
2. Iterate over all ECUC-MODULE-DEF elements
3. For each module, extract top-level containers recursively
4. For each container, extract parameters and references
5. Build search indexes over the complete model

#### Index Building Functions

**`build_indexes(model)`** - Post-parse index construction
1. Recursively collects all containers into flat list
2. Builds type index: container type (short name) → list of containers
3. Builds name index: instance short name → containers
4. Collects vocabulary: all unique short names (containers, parameters, references)
5. Sets `_parent` references for all containers (bottom-up navigation)

**`_collect_containers(container, parent, out)`** - Helper
- Recursively traverses container tree and sets parent references
- Populates flat list for index building

#### Fingerprinting

**`compute_fingerprint(filepaths)`** - Cache invalidation strategy
- Computes SHA-256 hash over sorted file contents
- Used to detect if source files changed since snapshot was created
- If fingerprint matches, snapshot is valid; otherwise, files are re-parsed

#### Serialization Functions

**`serialize(model, output_path, compress=True)`** - Binary snapshot creation
- Protocol: `MAGIC (8 bytes: "ARSNAP01")` + `VERSION (4 bytes)` + `gzip(pickle(model))`
- Compression: gzip level 6 (good balance between size and speed)
- Returns metadata: serialize_time_s, raw_pickle_bytes, file_bytes, compression_ratio
- Typically achieves 46× compression ratio over raw XML

**`deserialize(input_path)`** - Binary snapshot loading
- Reads and validates magic and version
- Attempts gzip decompression; falls back to raw pickle if invalid
- Rebuilds indexes post-deserialize (parent refs may not survive pickle correctly)
- Returns: (model, metadata) where metadata includes deserialize_time_s

#### Search Engine Functions

**`search_by_type(model, type_name, short_name=None)`** - O(1) type-based search
- Looks up type_name in type_index
- Optionally filters by short_name
- Returns list of matching containers

**`search_by_path(model, definition_path)`** - Slash-separated path search
- Extracts last segment of path
- O(1) lookup in type_index for that segment
- Validates full path by checking `definition_path.endswith()`
- Example: "Com/ComConfig/ComIPdu" matches all ComIPdu containers under ComConfig/Com

**`fuzzy_search(model, query, limit=10, threshold=0.4)`** - Approximate matching
- Iterates over vocabulary
- Exact substring matches get boosted score (0.8–1.0)
- Other matches scored using `SequenceMatcher.ratio()` (difflib)
- Filters by threshold (default 0.4)
- Sorts by score, returns top-N results

#### Display & Analysis Functions

**`get_container_details(container)`** - Formatting for API responses
- Returns dict with all container info: short_name, definition_path, description, multiplicity, depth
- Formatted parameters and references lists
- Sub-containers and choice-containers names

**`print_tree(model, max_depth=-1)`** - Tree visualization
- ASCII tree representation of container hierarchy
- Shows parameter/reference counts per container
- Respects max_depth limit

**`benchmark(filepaths, snapshot_path, runs=5)`** - Performance comparison
- Multiple parse cycles
- Multiple deserialize cycles
- Measures search latency over 20 container types
- Computes speedup factor (parse time / deserialize time)
- Cleanup: removes temporary snapshot file

#### CLI Commands

**`cmd_parse(args)`** - Parse ARXML files and create snapshot
- Usage: `python paramdef_manager.py parse <file1.arxml> [file2.arxml ...] [-o snapshot.bin]`

**`cmd_load(args)`** - Load snapshot and optionally display tree
- Usage: `python paramdef_manager.py load <snapshot.bin> [--tree] [--depth N]`

**`cmd_search(args)`** - Search in snapshot by type/path
- Usage: `python paramdef_manager.py search <snapshot.bin> --type <type> [--name <name>]`
- Or: `python paramdef_manager.py search <snapshot.bin> --path <path>`

**`cmd_fuzzy(args)`** - Fuzzy search
- Usage: `python paramdef_manager.py fuzzy <snapshot.bin> --query <text> [--limit N]`

**`cmd_benchmark(args)`** - Performance benchmark
- Usage: `python paramdef_manager.py benchmark <file1.arxml> [file2.arxml ...] [--runs N]`

**`cmd_fingerprint(args)`** - Display file fingerprint
- Usage: `python paramdef_manager.py fingerprint <file1.arxml> [file2.arxml ...]`

---

## Data Flow & Execution Flow

### Startup Flow (When MCP Server Starts)

```
1. User runs: python mcp_server.py
   │
   ├─→ FastMCP creates app instance
   │
   ├─→ All @app.tool() decorators register MCP tool handlers
   │
   ├─→ mcp_settings.py loads configuration
   │
   ├─→ mcp_util.py is imported → _ParamDefEngine._initialize() is called
   │   │
   │   ├─→ SNAPSHOT_PATH exists? → Check fingerprint
   │   │   │
   │   │   ├─→ Fingerprint matches? → FAST PATH: deserialize snapshot (~10 ms)
   │   │   │
   │   │   └─→ Fingerprint mismatch? → Fall through to cold path
   │   │
   │   └─→ COLD PATH: Parse ARXML files (~30 ms)
   │       │
   │       ├─→ ParamDefParser.parse_files() iterates all .arxml files
   │       ├─→ Each file parsed as XML, modules/containers extracted recursively
   │       ├─→ build_indexes() creates type_index, name_index, vocabulary
   │       │
   │       └─→ Try serialize() to save snapshot for next startup
   │
   ├─→ mcp_transport_configurator.configure_mcp() updates .vscode/mcp.json
   │
   └─→ app.run() starts server
       ├─→ STDIO mode (default): accepts JSON-RPC over stdin/stdout
       └─→ SSE mode: HTTP server on configured port
```

### Query Flow (When Copilot Calls a Tool)

```
GitHub Copilot
   │
   └─→ MCP Client sends JSON-RPC request
       │
       └─→ FastMCP dispatches to registered @app.tool() function
           │
           ├─→ Function in mcp_server.py (e.g., paramdef_search_by_type)
           │   │
           │   └─→ Calls corresponding tool_* function in mcp_util.py
           │       │
           │       └─→ Accesses _engine.model (already loaded in memory)
           │           │
           │           └─→ Calls search/fuzzy/stats functions in paramdef_manager.py
           │               │
           │               └─→ Uses prebuilt indexes for O(1) or O(vocab) lookup
           │
           └─→ Tool returns result dict
               │
               └─→ FastMCP encodes as JSON-RPC response
                   │
                   └─→ Response sent back to Copilot
```

### Example Query: Find all ComIPdu Containers

```python
paramdef_search_by_type(container_type="ComIPdu")
   │
   ├─→ tool_search_by_type() in mcp_util.py
   │   │
   │   └─→ search_by_type(_engine.model, "ComIPdu", None) in paramdef_manager.py
   │       │
   │       ├─→ O(1) index lookup: model._type_index["ComIPdu"]
   │       │   Returns: [ComIPdu#1, ComIPdu#2, ...]
   │       │
   │       └─→ get_container_details() for each result
   │           Returns full details: definition_path, parameters, references, etc.
```

---

## Deployment & Integration

### Quick Start

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Start the server:**
```bash
python agent_tpl/mcp_server.py
```

**3. Verify VS Code integration:**
- Check `.vscode/mcp.json` is created
- VS Code MCP extension should auto-discover the server
- Tools appear in Copilot's available functions

### Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Snapshot-first loading** | Cold start penalty paid once; warm starts are >10× faster |
| **Binary pickle format** | Fast serialization; smaller than XML (46× compression ratio) |
| **Fingerprint validation** | Detects when source files change; automatically invalidates stale snapshots |
| **Pre-built indexes** | O(1) type/path lookups; O(vocabulary) fuzzy search enables sub-millisecond responses |
| **Singleton engine pattern** | Model stays in memory for entire server lifetime; shared across all tool calls |
| **MCP protocol** | Standard for LLM integration; works with any MCP-compatible client (Copilot, Claude Desktop, etc.) |

---

## Error Handling & Edge Cases

### Snapshot Validation
- **Corrupt snapshot:** Caught during deserialization; server falls back to XML parsing
- **Version mismatch:** Snapshot version check prevents incompatible binary format issues
- **Missing fingerprint:** Stale snapshot detected by fingerprint mismatch; forces re-parse

### Search Edge Cases
- **Empty vocabulary:** Fuzzy search with no matches returns empty list
- **Circular parent references:** Avoided by always setting `_parent` correctly during index build
- **Max results capped:** Results truncated at `_MAX_RESULTS` (20) to prevent token explosion in Copilot responses

### Transport Errors
- **STDIO disconnection:** MCP client crash results in server exit
- **SSE timeout:** HTTP timeout handled by FastMCP framework

---

## Extension Points

### Adding New Search Capabilities

To add a new search function (e.g., by parameter name):

1. **In `paramdef_manager.py`:**
   ```python
   def search_by_param_name(model, param_name):
       """Search containers containing a parameter with given name."""
       results = []
       for container in model._all_containers:
           for param in container.parameters:
               if param.short_name == param_name:
                   results.append(container)
                   break
       return results
   ```

2. **In `mcp_util.py`:**
   ```python
   def tool_search_by_param_name(param_name):
       if _engine.model is None:
           return {"error": "Model not loaded"}
       results = pdm.search_by_param_name(_engine.model, param_name)
       return {"param_name": param_name, "count": len(results), "results": [...]}
   ```

3. **In `mcp_server.py`:**
   ```python
   @app.tool()
   def paramdef_search_by_param_name(param_name: str):
       """Find all containers with a specific parameter."""
       return tool_search_by_param_name(param_name)
   ```

### Supporting Multiple Models

Current design loads a single unified model. To support multiple models:

1. Modify `_ParamDefEngine` to maintain a dict of models
2. Add routing based on module name or source file
3. Extend tool signatures to accept model selector parameter

---

## Performance Characteristics

| Operation | Complexity | Typical Time |
|-----------|-----------|--------------|
| XML parse (cold start) | O(file_size) | 20–30 ms (small), minutes (full PVER) |
| Binary deserialize | O(model_size) | 3–5 ms (snapshot load) |
| Type search | O(1) | <1 µs |
| Path search | O(1) + O(depth) | 1–10 µs |
| Fuzzy search | O(vocabulary_size) | 10–100 µs (depending on query specificity) |
| Compression ratio | — | 46× (raw pickle → gzip) |

---

## Testing & Validation

### Manual Testing

**Test 1: Warm start performance**
```bash
# First run (cold start)
time python agent_tpl/mcp_server.py

# Second run (warm start with snapshot)
time python agent_tpl/mcp_server.py
```

**Test 2: Search accuracy**
```bash
# Type search
python agent_tpl/paramdef_manager.py search confrules/paramdef.snapshot.bin --type ComIPdu

# Fuzzy search
python agent_tpl/paramdef_manager.py fuzzy confrules/paramdef.snapshot.bin --query "timeout"
```

**Test 3: Benchmark**
```bash
python agent_tpl/paramdef_manager.py benchmark confrules/*.arxml --runs 5
```

### Unit Testing (Future)

Recommended test cases:
- Parser: Test each ARXML element type parsing
- Indexes: Verify index correctness and O(1) lookup times
- Search: Test exact/fuzzy/path matches against known results
- Serialization: Round-trip model serialization/deserialization
- Transport: MCP protocol compliance

---

## Maintenance & Future Improvements

### Known Limitations

1. **Single model per server:** Cannot query multiple AUTOSAR versions simultaneously
2. **No incremental updates:** Any source change forces full re-parse
3. **STDIO-only persistence:** Server must restart for config changes
4. **No caching of search results:** Identical queries parsed independently

### Recommended Enhancements

1. **Multi-model support:** Load multiple AUTOSAR versions and route queries
2. **Incremental snapshot updates:** Diff-based updates for file changes
3. **Result caching:** Cache frequently-accessed search results
4. **Streaming responses:** Return large result sets progressively instead of all-at-once
5. **Type validation:** Validate container/reference types against schema
6. **Statistics collection:** Track query frequency and latency for optimization

---

## Summary of Functions by Module

### mcp_server.py (6 tools)
- `mcp_get_precise_time()` — Utility time function
- `paramdef_model_stats()` — Model stats and load source
- `paramdef_fuzzy_search()` — Approximate name matching
- `paramdef_search_by_type()` — Exact type search
- `paramdef_search_by_path()` — Hierarchical path search
- `paramdef_list_containers()` — Browse by module

### mcp_util.py (7 functions)
- `_ParamDefEngine.__init__()` — Engine initialization
- `_ParamDefEngine.initialize()` — Load or parse model
- `tool_model_stats()` — Stats wrapper
- `tool_fuzzy_search()` — Fuzzy search wrapper
- `tool_search_by_type()` — Type search wrapper
- `tool_search_by_path()` — Path search wrapper
- `tool_list_containers()` — Container listing wrapper
- `get_precise_time()` — Time utility

### paramdef_manager.py (20+ functions & classes)
- **Data classes:** `ParamDef`, `ReferenceDef`, `ContainerDef`, `ModuleDef`, `ParamDefModel`
- **Parser:** `ParamDefParser` (with 7 methods)
- **Indexing:** `build_indexes()`, `_collect_containers()`
- **Fingerprinting:** `compute_fingerprint()`
- **Serialization:** `serialize()`, `deserialize()`
- **Search:** `search_by_type()`, `search_by_path()`, `fuzzy_search()`
- **Display:** `get_container_details()`, `print_tree()`
- **Benchmarking:** `benchmark()`
- **CLI:** `cmd_parse()`, `cmd_load()`, `cmd_search()`, `cmd_fuzzy()`, `cmd_benchmark()`, `cmd_fingerprint()`, `main()`
- **Utilities:** `_format_table()`

### mcp_settings.py (1 config dict)
- `SETTINGS` — Global configuration

### mcp_transport_configurator.py (2 functions)
- `configure_mcp()` — Generate .vscode/mcp.json
- `path_difference()` — Compute relative paths
