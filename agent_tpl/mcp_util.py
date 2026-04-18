"""
Utilities — AUTOSAR ParamDef MCP Tools
@author: GUU8HC
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import from local copy in same directory
import paramdef_manager as pdm

# ---------------------------------------------------------------------------
# Configuration paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # agent_tpl/
_CONFRULES_DIR = _THIS_DIR.parent / "confrules"
_SNAPSHOT_PATH = _CONFRULES_DIR / "paramdef.snapshot.bin"

_MAX_RESULTS = 20  # cap per search call to keep responses token-friendly


# ---------------------------------------------------------------------------
# Engine — loads once at startup, serves all queries from memory
# ---------------------------------------------------------------------------
class _ParamDefEngine:
    """
    Singleton that holds the in-memory ParamDefModel.

    Startup strategy (snapshot-first):
      1. If a snapshot exists and its fingerprint matches the current ARXML files
         → deserialize the snapshot (fast path, typically 3–5 ms).
      2. Otherwise → parse ARXML files (cold start), then auto-save a new snapshot
         so the next startup is fast.

    This is the core serialization advantage: after the first cold start the
    model never needs to be re-parsed from XML unless the source files change.
    """

    def __init__(self) -> None:
        self.model: Optional[pdm.ParamDefModel] = None
        self.load_source: str = "not_loaded"
        self.load_time_ms: float = 0.0
        self._error: Optional[str] = None
        self._snapshot_saved: bool = False

    def initialize(self) -> None:
        arxmls = sorted(_CONFRULES_DIR.glob("*.arxml"))
        if not arxmls:
            self._error = f"No .arxml files found in {_CONFRULES_DIR}"
            return

        arxml_paths = [str(a) for a in arxmls]

        # --- Fast path: try snapshot first ---
        if _SNAPSHOT_PATH.exists():
            try:
                t0 = time.perf_counter()
                candidate, _meta = pdm.deserialize(str(_SNAPSHOT_PATH))
                elapsed_ms = (time.perf_counter() - t0) * 1000

                current_fp = pdm.compute_fingerprint(arxml_paths)
                if candidate.fingerprint == current_fp:
                    self.model = candidate
                    self.load_source = "snapshot"
                    self.load_time_ms = round(elapsed_ms, 2)
                    return
                # Fingerprint mismatch → snapshot is stale, fall through
            except Exception:
                pass  # corrupt / version mismatch → fall through

        # --- Cold path: parse from ARXML, then save snapshot ---
        parser = pdm.ParamDefParser()
        t0 = time.perf_counter()
        self.model = parser.parse_files(arxml_paths)
        self.load_time_ms = round((time.perf_counter() - t0) * 1000, 2)
        self.load_source = "arxml"

        try:
            pdm.serialize(self.model, str(_SNAPSHOT_PATH))
            self._snapshot_saved = True
        except Exception:
            pass  # non-fatal; server still works without snapshot


# Module-level singleton — initialized exactly once when this module is first imported.
# Because the MCP server imports mcp_util at startup, the model is loaded
# before the first tool call arrives.
_engine = _ParamDefEngine()
_engine.initialize()


# ---------------------------------------------------------------------------
# Tool implementations (plain functions, no FastMCP dependency here)
# ---------------------------------------------------------------------------

def tool_model_stats() -> dict[str, Any]:
    """
    Return model statistics and startup load performance.

    The 'load_source' field shows whether the model was loaded from the
    binary snapshot (fast) or re-parsed from ARXML (cold start).
    """
    if _engine.model is None:
        return {"error": _engine._error or "Model not loaded"}

    info: dict[str, Any] = {
        "load_source": _engine.load_source,
        "load_time_ms": _engine.load_time_ms,
        "snapshot_path": str(_SNAPSHOT_PATH),
        "snapshot_exists": _SNAPSHOT_PATH.exists(),
        "confrules_dir": str(_CONFRULES_DIR),
        "model": _engine.model.stats(),
    }
    if _engine.load_source == "arxml" and _engine._snapshot_saved:
        info["note"] = "Snapshot created — next startup will use the fast path"
    return info


def tool_fuzzy_search(query: str, limit: int = 10) -> dict[str, Any]:
    """
    Fuzzy search across all container, parameter, and reference names in the
    in-memory model index.  O(vocabulary_size) scan with SequenceMatcher scoring.
    """
    if _engine.model is None:
        return {"error": _engine._error or "Model not loaded"}

    limit = max(1, min(limit, 30))
    t0 = time.perf_counter()
    results = pdm.fuzzy_search(_engine.model, query, limit=limit)
    search_us = round((time.perf_counter() - t0) * 1_000_000, 1)

    return {
        "query": query,
        "search_time_us": search_us,
        "count": len(results),
        "results": [{"term": term, "score": score} for term, score in results],
    }


def tool_search_by_type(
    container_type: str, short_name: Optional[str] = None
) -> dict[str, Any]:
    """
    O(1) index lookup by container type name, optionally narrowed by instance
    short name.  Returns full container details (parameters + references).
    """
    if _engine.model is None:
        return {"error": _engine._error or "Model not loaded"}

    t0 = time.perf_counter()
    containers = pdm.search_by_type(_engine.model, container_type, short_name)
    search_us = round((time.perf_counter() - t0) * 1_000_000, 1)

    capped = containers[:_MAX_RESULTS]
    return {
        "container_type": container_type,
        "short_name_filter": short_name,
        "search_time_us": search_us,
        "count": len(containers),
        "capped_at": _MAX_RESULTS if len(containers) > _MAX_RESULTS else None,
        "results": [pdm.get_container_details(c) for c in capped],
    }


def tool_search_by_path(definition_path: str) -> dict[str, Any]:
    """
    Search containers whose definition_path ends with the given path segment.
    Uses the bottom-up index for O(1) lookup on the last segment.
    """
    if _engine.model is None:
        return {"error": _engine._error or "Model not loaded"}

    t0 = time.perf_counter()
    containers = pdm.search_by_path(_engine.model, definition_path)
    search_us = round((time.perf_counter() - t0) * 1_000_000, 1)

    capped = containers[:_MAX_RESULTS]
    return {
        "definition_path": definition_path,
        "search_time_us": search_us,
        "count": len(containers),
        "capped_at": _MAX_RESULTS if len(containers) > _MAX_RESULTS else None,
        "results": [pdm.get_container_details(c) for c in capped],
    }


def tool_list_containers(module_name: Optional[str] = None) -> dict[str, Any]:
    """
    Browse the top-level containers grouped by module.
    Use for discovery when you don't yet know container type names.
    """
    if _engine.model is None:
        return {"error": _engine._error or "Model not loaded"}

    modules = _engine.model.modules
    if module_name:
        modules = [m for m in modules if m.short_name.lower() == module_name.lower()]

    output: list[dict[str, Any]] = []
    for m in modules:
        for c in m.containers:
            mult = (
                f"[{c.lower_multiplicity}..*]"
                if c.upper_multiplicity_infinite
                else f"[{c.lower_multiplicity}..{c.upper_multiplicity or '?'}]"
            )
            output.append(
                {
                    "module": m.short_name,
                    "container": c.short_name,
                    "path": c.definition_path,
                    "multiplicity": mult,
                    "params": len(c.parameters),
                    "refs": len(c.references),
                    "children": len(c.all_children()),
                }
            )

    return {
        "module_filter": module_name,
        "total_modules": len(modules),
        "count": len(output),
        "containers": output,
    }


# ---------------------------------------------------------------------------
# Original utility
# ---------------------------------------------------------------------------

def get_precise_time():
    """Get the precise time up to microsecond precision."""
    return datetime.now()
