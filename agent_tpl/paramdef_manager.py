"""
AUTOSAR ParamDef Manager — All-in-One Serialization & Search Engine

Parses AUTOSAR ParamDef .arxml files into an optimized in-memory model,
serializes to binary snapshots for fast reload, builds search indexes,
and provides bottom-up indexed search with fuzzy matching.

Usage:
    python paramdef_manager.py parse <file1.arxml> [file2.arxml ...] [-o snapshot.bin]
    python paramdef_manager.py load <snapshot.bin> [--info] [--tree]
    python paramdef_manager.py search <snapshot.bin> --type <type> [--name <shortName>]
    python paramdef_manager.py fuzzy <snapshot.bin> --query <text>
    python paramdef_manager.py benchmark <file1.arxml> [file2.arxml ...]
    python paramdef_manager.py fingerprint <file1.arxml> [file2.arxml ...]

Author: Nguyen Duc Tuan
Related: ComScl_ModelMngr Research Paper (#40004)
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pickle
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# AUTOSAR namespace
# ---------------------------------------------------------------------------
AR_NS = "http://autosar.org/schema/r4.0"
NS = {"ar": AR_NS}


def _tag(local: str) -> str:
    """Return fully qualified tag name with AUTOSAR namespace."""
    return f"{{{AR_NS}}}{local}"


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------
@dataclass
class ParamDef:
    """A single parameter definition (integer, boolean, enum, etc.)."""

    short_name: str
    param_type: str  # integer | boolean | enumeration | string | float | function-name
    description: str = ""
    lower_multiplicity: str = "0"
    upper_multiplicity: str = "1"
    scope: str = ""
    origin: str = ""
    default_value: Optional[str] = None
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    enum_literals: list[str] = field(default_factory=list)
    symbolic_name_value: bool = False


@dataclass
class ReferenceDef:
    """A reference definition (to other containers or foreign types)."""

    short_name: str
    ref_type: str  # reference | foreign-reference | choice-reference | symbolic-name
    description: str = ""
    dest_ref: Optional[str] = None
    dest_type: Optional[str] = None
    lower_multiplicity: str = "0"
    upper_multiplicity: str = "1"


@dataclass
class ContainerDef:
    """A container definition — the primary node in the config tree."""

    short_name: str
    description: str = ""
    lower_multiplicity: str = "0"
    upper_multiplicity: Optional[str] = "1"
    upper_multiplicity_infinite: bool = False
    parameters: list[ParamDef] = field(default_factory=list)
    references: list[ReferenceDef] = field(default_factory=list)
    sub_containers: list[ContainerDef] = field(default_factory=list)
    choice_containers: list[ContainerDef] = field(default_factory=list)
    definition_path: str = ""
    # Parent reference (set during index build, excluded from repr for clarity)
    _parent: Optional[ContainerDef] = field(default=None, repr=False)

    @property
    def parent(self) -> Optional[ContainerDef]:
        return self._parent

    def all_children(self) -> list[ContainerDef]:
        """Return all direct children (sub-containers + choice containers)."""
        return self.sub_containers + self.choice_containers

    def depth(self) -> int:
        """Return the depth of this container in the tree."""
        d = 0
        node = self._parent
        while node is not None:
            d += 1
            node = node._parent
        return d

    def path_segments(self) -> list[str]:
        """Return the definition path as a list of short names from root."""
        return self.definition_path.split("/") if self.definition_path else []


@dataclass
class ModuleDef:
    """A top-level ECUC module definition (e.g., Com, PduR)."""

    short_name: str
    description: str = ""
    category: str = ""
    version: str = ""
    containers: list[ContainerDef] = field(default_factory=list)


@dataclass
class ParamDefModel:
    """The complete parsed model from one or more ParamDef .arxml files."""

    modules: list[ModuleDef] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    fingerprint: str = ""
    parse_time_s: float = 0.0
    created_at: float = field(default_factory=time.time)
    # Search indexes (built post-parse)
    _type_index: dict[str, list[ContainerDef]] = field(
        default_factory=dict, repr=False
    )
    _name_index: dict[str, list[ContainerDef]] = field(
        default_factory=dict, repr=False
    )
    _all_containers: list[ContainerDef] = field(default_factory=list, repr=False)
    _vocabulary: list[str] = field(default_factory=list, repr=False)

    # -- Statistics ----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        total_containers = len(self._all_containers)
        total_params = sum(
            len(c.parameters) for c in self._all_containers
        )
        total_refs = sum(len(c.references) for c in self._all_containers)
        max_depth = max((c.depth() for c in self._all_containers), default=0)
        return {
            "modules": len(self.modules),
            "containers": total_containers,
            "parameters": total_params,
            "references": total_refs,
            "max_depth": max_depth,
            "unique_types": len(self._type_index),
            "vocabulary_size": len(self._vocabulary),
            "source_files": len(self.source_files),
            "fingerprint": self.fingerprint[:16] + "...",
        }


# ---------------------------------------------------------------------------
# Parser: ARXML → Model
# ---------------------------------------------------------------------------
class ParamDefParser:
    """Parses AUTOSAR ParamDef .arxml files into a ParamDefModel."""

    # Mapping from XML tag suffix to param_type string
    PARAM_TAG_MAP = {
        "ECUC-INTEGER-PARAM-DEF": "integer",
        "ECUC-BOOLEAN-PARAM-DEF": "boolean",
        "ECUC-ENUMERATION-PARAM-DEF": "enumeration",
        "ECUC-STRING-PARAM-DEF": "string",
        "ECUC-FLOAT-PARAM-DEF": "float",
        "ECUC-FUNCTION-NAME-DEF": "function-name",
        "ECUC-LINKER-SYMBOL-DEF": "linker-symbol",
        "ECUC-ADD-INFO-PARAM-DEF": "add-info",
    }

    REF_TAG_MAP = {
        "ECUC-REFERENCE-DEF": "reference",
        "ECUC-FOREIGN-REFERENCE-DEF": "foreign-reference",
        "ECUC-CHOICE-REFERENCE-DEF": "choice-reference",
        "ECUC-SYMBOLIC-NAME-REFERENCE-DEF": "symbolic-name",
        "ECUC-URI-REFERENCE-DEF": "uri-reference",
        "ECUC-INSTANCE-REFERENCE-DEF": "instance-reference",
    }

    def _text(self, el: Optional[ET.Element], tag: str) -> str:
        """Get text content of a child element, or empty string."""
        if el is None:
            return ""
        child = el.find(_tag(tag))
        return (child.text or "").strip() if child is not None else ""

    def _desc(self, el: ET.Element) -> str:
        """Extract description text from DESC/L-2 element."""
        desc_el = el.find(_tag("DESC"))
        if desc_el is None:
            return ""
        l2 = desc_el.find(_tag("L-2"))
        return (l2.text or "").strip() if l2 is not None else ""

    def _parse_param(self, el: ET.Element, param_type: str) -> ParamDef:
        """Parse a single parameter definition element."""
        p = ParamDef(
            short_name=self._text(el, "SHORT-NAME"),
            param_type=param_type,
            description=self._desc(el),
            lower_multiplicity=self._text(el, "LOWER-MULTIPLICITY") or "0",
            upper_multiplicity=self._text(el, "UPPER-MULTIPLICITY") or "1",
            scope=self._text(el, "SCOPE"),
            origin=self._text(el, "ORIGIN"),
            symbolic_name_value=self._text(el, "SYMBOLIC-NAME-VALUE") == "true",
        )
        # Default value
        dv = el.find(_tag("DEFAULT-VALUE"))
        if dv is not None and dv.text:
            p.default_value = dv.text.strip()
        # Min / Max
        min_el = el.find(_tag("MIN"))
        if min_el is not None and min_el.text:
            p.min_value = min_el.text.strip()
        max_el = el.find(_tag("MAX"))
        if max_el is not None and max_el.text:
            p.max_value = max_el.text.strip()
        # Enum literals
        if param_type == "enumeration":
            literals_el = el.find(_tag("LITERALS"))
            if literals_el is not None:
                for lit in literals_el.findall(_tag("ECUC-ENUMERATION-LITERAL-DEF")):
                    name = self._text(lit, "SHORT-NAME")
                    if name:
                        p.enum_literals.append(name)
        return p

    def _parse_reference(self, el: ET.Element, ref_type: str) -> ReferenceDef:
        """Parse a single reference definition element."""
        r = ReferenceDef(
            short_name=self._text(el, "SHORT-NAME"),
            ref_type=ref_type,
            description=self._desc(el),
            lower_multiplicity=self._text(el, "LOWER-MULTIPLICITY") or "0",
            upper_multiplicity=self._text(el, "UPPER-MULTIPLICITY") or "1",
        )
        # Destination reference
        dest_el = el.find(_tag("DESTINATION-REF"))
        if dest_el is not None and dest_el.text:
            r.dest_ref = dest_el.text.strip()
            r.dest_type = dest_el.get("DEST", "")
        # For foreign references, the destination type attribute
        dest_type_el = el.find(_tag("DESTINATION-TYPE"))
        if dest_type_el is not None and dest_type_el.text:
            r.dest_type = dest_type_el.text.strip()
        return r

    def _parse_container(
        self, el: ET.Element, parent_path: str
    ) -> ContainerDef:
        """Recursively parse a container definition element."""
        short_name = self._text(el, "SHORT-NAME")
        path = f"{parent_path}/{short_name}" if parent_path else short_name

        c = ContainerDef(
            short_name=short_name,
            description=self._desc(el),
            lower_multiplicity=self._text(el, "LOWER-MULTIPLICITY") or "0",
            definition_path=path,
        )

        # Upper multiplicity
        upper_inf = el.find(_tag("UPPER-MULTIPLICITY-INFINITE"))
        if upper_inf is not None and (upper_inf.text or "").strip() == "true":
            c.upper_multiplicity_infinite = True
            c.upper_multiplicity = None
        else:
            c.upper_multiplicity = self._text(el, "UPPER-MULTIPLICITY") or "1"

        # Parameters
        params_el = el.find(_tag("PARAMETERS"))
        if params_el is not None:
            for tag_suffix, ptype in self.PARAM_TAG_MAP.items():
                for p_el in params_el.findall(_tag(tag_suffix)):
                    c.parameters.append(self._parse_param(p_el, ptype))

        # References
        refs_el = el.find(_tag("REFERENCES"))
        if refs_el is not None:
            for tag_suffix, rtype in self.REF_TAG_MAP.items():
                for r_el in refs_el.findall(_tag(tag_suffix)):
                    c.references.append(self._parse_reference(r_el, rtype))

        # Sub-containers
        subs_el = el.find(_tag("SUB-CONTAINERS"))
        if subs_el is not None:
            for sub_el in subs_el.findall(
                _tag("ECUC-PARAM-CONF-CONTAINER-DEF")
            ):
                c.sub_containers.append(self._parse_container(sub_el, path))
            for sub_el in subs_el.findall(
                _tag("ECUC-CHOICE-CONTAINER-DEF")
            ):
                c.sub_containers.append(self._parse_container(sub_el, path))

        # Choice containers (inside CHOICES element for choice container defs)
        choices_el = el.find(_tag("CHOICES"))
        if choices_el is not None:
            for ch_el in choices_el.findall(
                _tag("ECUC-PARAM-CONF-CONTAINER-DEF")
            ):
                c.choice_containers.append(self._parse_container(ch_el, path))

        return c

    def _parse_module(self, el: ET.Element) -> ModuleDef:
        """Parse an ECUC-MODULE-DEF element."""
        m = ModuleDef(
            short_name=self._text(el, "SHORT-NAME"),
            description=self._desc(el),
            category=self._text(el, "CATEGORY"),
        )

        # Version from ADMIN-DATA
        admin = el.find(_tag("ADMIN-DATA"))
        if admin is not None:
            for rev in admin.findall(f".//{_tag('DOC-REVISION')}"):
                label = self._text(rev, "REVISION-LABEL")
                if label:
                    m.version = label  # last one wins

        # Top-level containers
        containers_el = el.find(_tag("CONTAINERS"))
        if containers_el is not None:
            for c_el in containers_el.findall(
                _tag("ECUC-PARAM-CONF-CONTAINER-DEF")
            ):
                m.containers.append(
                    self._parse_container(c_el, m.short_name)
                )
            for c_el in containers_el.findall(
                _tag("ECUC-CHOICE-CONTAINER-DEF")
            ):
                m.containers.append(
                    self._parse_container(c_el, m.short_name)
                )

        return m

    def parse_file(self, filepath: str) -> list[ModuleDef]:
        """Parse a single .arxml file and return list of ModuleDefs."""
        tree = ET.parse(filepath)
        root = tree.getroot()
        modules = []
        for mod_el in root.iter(_tag("ECUC-MODULE-DEF")):
            modules.append(self._parse_module(mod_el))
        return modules

    def parse_files(self, filepaths: list[str]) -> ParamDefModel:
        """Parse multiple .arxml files into a unified ParamDefModel."""
        t0 = time.perf_counter()
        model = ParamDefModel()
        model.source_files = [str(Path(f).resolve()) for f in filepaths]
        model.fingerprint = compute_fingerprint(filepaths)

        for fp in filepaths:
            modules = self.parse_file(fp)
            model.modules.extend(modules)

        model.parse_time_s = time.perf_counter() - t0
        build_indexes(model)
        return model


# ---------------------------------------------------------------------------
# Index Builder
# ---------------------------------------------------------------------------
def _collect_containers(
    container: ContainerDef,
    parent: Optional[ContainerDef],
    out: list[ContainerDef],
) -> None:
    """Recursively collect all containers and set parent references."""
    container._parent = parent
    out.append(container)
    for child in container.all_children():
        _collect_containers(child, container, out)


def build_indexes(model: ParamDefModel) -> None:
    """Build search indexes on the model (type index, name index, vocabulary)."""
    all_containers: list[ContainerDef] = []

    for module in model.modules:
        for container in module.containers:
            _collect_containers(container, None, all_containers)

    model._all_containers = all_containers

    # Type index: definition type (last segment of path) → list of containers
    type_idx: dict[str, list[ContainerDef]] = {}
    name_idx: dict[str, list[ContainerDef]] = {}
    vocab_set: set[str] = set()

    for c in all_containers:
        # Type key = last segment of definition path (= the container's own short_name)
        type_key = c.short_name
        type_idx.setdefault(type_key, []).append(c)

        # Name index: shortName → containers (for direct lookup)
        name_idx.setdefault(c.short_name, []).append(c)

        # Vocabulary: collect all short names for fuzzy search
        vocab_set.add(c.short_name)
        for p in c.parameters:
            vocab_set.add(p.short_name)
        for r in c.references:
            vocab_set.add(r.short_name)

    model._type_index = type_idx
    model._name_index = name_idx
    model._vocabulary = sorted(vocab_set)


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------
def compute_fingerprint(filepaths: list[str]) -> str:
    """Compute SHA-256 fingerprint over sorted file contents."""
    h = hashlib.sha256()
    for fp in sorted(filepaths):
        with open(fp, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Serializer / Deserializer
# ---------------------------------------------------------------------------
SNAPSHOT_MAGIC = b"ARSNAP01"
SNAPSHOT_VERSION = 1


def serialize(model: ParamDefModel, output_path: str, compress: bool = True) -> dict[str, Any]:
    """
    Serialize a ParamDefModel to a binary snapshot file.

    Format: MAGIC (8 bytes) + VERSION (4 bytes) + gzip(pickle(model))

    Returns metadata dict with size and timing information.
    """
    t0 = time.perf_counter()
    raw = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
    raw_size = len(raw)

    if compress:
        data = gzip.compress(raw, compresslevel=6)
    else:
        data = raw

    with open(output_path, "wb") as f:
        f.write(SNAPSHOT_MAGIC)
        f.write(SNAPSHOT_VERSION.to_bytes(4, "little"))
        f.write(data)

    elapsed = time.perf_counter() - t0
    file_size = os.path.getsize(output_path)

    return {
        "serialize_time_s": round(elapsed, 6),
        "raw_pickle_bytes": raw_size,
        "file_bytes": file_size,
        "compression_ratio": round(raw_size / file_size, 2) if file_size > 0 else 0,
        "compressed": compress,
    }


def deserialize(input_path: str) -> tuple[ParamDefModel, dict[str, Any]]:
    """
    Deserialize a ParamDefModel from a binary snapshot file.

    Returns (model, metadata) where metadata contains timing info.
    """
    t0 = time.perf_counter()

    with open(input_path, "rb") as f:
        magic = f.read(8)
        if magic != SNAPSHOT_MAGIC:
            raise ValueError(
                f"Invalid snapshot file: expected magic {SNAPSHOT_MAGIC!r}, got {magic!r}"
            )
        version = int.from_bytes(f.read(4), "little")
        if version != SNAPSHOT_VERSION:
            raise ValueError(
                f"Unsupported snapshot version: {version} (expected {SNAPSHOT_VERSION})"
            )
        data = f.read()

    # Try gzip decompress; fall back to raw pickle
    try:
        raw = gzip.decompress(data)
    except gzip.BadGzipFile:
        raw = data

    model: ParamDefModel = pickle.loads(raw)

    # Rebuild indexes (parent refs may not survive pickle correctly in all cases)
    build_indexes(model)

    elapsed = time.perf_counter() - t0

    meta = {
        "deserialize_time_s": round(elapsed, 6),
        "file_bytes": os.path.getsize(input_path),
        "snapshot_version": version,
    }

    return model, meta


# ---------------------------------------------------------------------------
# Search Engine
# ---------------------------------------------------------------------------
def search_by_type(
    model: ParamDefModel, type_name: str, short_name: Optional[str] = None
) -> list[ContainerDef]:
    """
    Search containers by type (short_name of the container definition).

    If short_name is provided, filters results to those matching.
    Uses O(1) index lookup + O(depth) parent validation.
    """
    candidates = model._type_index.get(type_name, [])
    if short_name is not None:
        candidates = [c for c in candidates if c.short_name == short_name]
    return candidates


def search_by_path(
    model: ParamDefModel, definition_path: str
) -> list[ContainerDef]:
    """
    Search containers by full or partial definition path.

    Example: "Com/ComConfig/ComIPdu" returns all ComIPdu containers.
    Uses O(1) lookup on last path segment + O(depth) parent validation.
    """
    segments = definition_path.strip("/").split("/")
    if not segments:
        return []

    target_type = segments[-1]
    candidates = model._type_index.get(target_type, [])

    # Validate parent chain (bottom-up)
    results = []
    for c in candidates:
        if c.definition_path.endswith(definition_path):
            results.append(c)
    return results


def fuzzy_search(
    model: ParamDefModel, query: str, limit: int = 10, threshold: float = 0.4
) -> list[tuple[str, float]]:
    """
    Fuzzy search over the vocabulary (all short names).

    Returns list of (term, score) sorted by relevance.
    Uses SequenceMatcher for similarity scoring.
    """
    query_lower = query.lower()
    scored: list[tuple[str, float]] = []

    for term in model._vocabulary:
        term_lower = term.lower()

        # Exact substring match gets boosted score
        if query_lower in term_lower:
            score = 0.8 + 0.2 * (len(query_lower) / len(term_lower))
        else:
            score = SequenceMatcher(None, query_lower, term_lower).ratio()

        if score >= threshold:
            scored.append((term, round(score, 4)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def get_container_details(container: ContainerDef) -> dict[str, Any]:
    """Return a dict with all details of a container for display/API use."""
    return {
        "short_name": container.short_name,
        "definition_path": container.definition_path,
        "description": container.description,
        "multiplicity": f"[{container.lower_multiplicity}..{'*' if container.upper_multiplicity_infinite else (container.upper_multiplicity or '?')}]",
        "depth": container.depth(),
        "parameters": [
            {
                "name": p.short_name,
                "type": p.param_type,
                "default": p.default_value,
                "range": f"[{p.min_value}, {p.max_value}]"
                if p.min_value is not None
                else None,
                "enum_values": p.enum_literals or None,
                "multiplicity": f"[{p.lower_multiplicity}..{p.upper_multiplicity}]",
            }
            for p in container.parameters
        ],
        "references": [
            {
                "name": r.short_name,
                "type": r.ref_type,
                "dest": r.dest_ref,
            }
            for r in container.references
        ],
        "sub_containers": [sc.short_name for sc in container.sub_containers],
        "choice_containers": [
            cc.short_name for cc in container.choice_containers
        ],
        "parent": container.parent.short_name if container.parent else None,
    }


# ---------------------------------------------------------------------------
# Tree Printer
# ---------------------------------------------------------------------------
def print_tree(model: ParamDefModel, max_depth: int = -1) -> str:
    """Return a string representation of the container tree."""
    lines: list[str] = []

    def _walk(container: ContainerDef, prefix: str, is_last: bool, depth: int) -> None:
        if max_depth >= 0 and depth > max_depth:
            return
        connector = "└── " if is_last else "├── "
        param_count = len(container.parameters)
        ref_count = len(container.references)
        suffix = ""
        if param_count or ref_count:
            suffix = f"  ({param_count}P, {ref_count}R)"
        lines.append(f"{prefix}{connector}{container.short_name}{suffix}")

        new_prefix = prefix + ("    " if is_last else "│   ")
        children = container.all_children()
        for i, child in enumerate(children):
            _walk(child, new_prefix, i == len(children) - 1, depth + 1)

    for module in model.modules:
        lines.append(f"📦 {module.short_name} (v{module.version})")
        for i, c in enumerate(module.containers):
            _walk(c, "", i == len(module.containers) - 1, 0)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------
def benchmark(
    filepaths: list[str], snapshot_path: str = "__benchmark_snapshot.bin", runs: int = 5
) -> dict[str, Any]:
    """
    Benchmark XML parse vs snapshot deserialize.

    Returns comparative timing data.
    """
    parser = ParamDefParser()

    # Measure XML parse (multiple runs)
    parse_times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        model = parser.parse_files(filepaths)
        parse_times.append(time.perf_counter() - t0)

    # Serialize
    ser_meta = serialize(model, snapshot_path, compress=True)

    # Measure deserialize (multiple runs)
    deser_times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        _, _ = deserialize(snapshot_path)
        deser_times.append(time.perf_counter() - t0)

    # Measure search (after deserialization)
    loaded_model, _ = deserialize(snapshot_path)
    search_times = []
    # Search for each container type
    for type_name in list(loaded_model._type_index.keys())[:20]:
        t0 = time.perf_counter()
        search_by_type(loaded_model, type_name)
        search_times.append(time.perf_counter() - t0)

    # Cleanup
    try:
        os.remove(snapshot_path)
    except OSError:
        pass

    # Compute source file sizes
    source_size = sum(os.path.getsize(f) for f in filepaths)

    avg_parse = sum(parse_times) / len(parse_times)
    avg_deser = sum(deser_times) / len(deser_times)
    avg_search = sum(search_times) / len(search_times) if search_times else 0

    return {
        "source_files": len(filepaths),
        "source_size_kb": round(source_size / 1024, 1),
        "snapshot_size_kb": round(ser_meta["file_bytes"] / 1024, 1),
        "compression_ratio": ser_meta["compression_ratio"],
        "model_stats": model.stats(),
        "parse_avg_ms": round(avg_parse * 1000, 2),
        "parse_min_ms": round(min(parse_times) * 1000, 2),
        "deserialize_avg_ms": round(avg_deser * 1000, 2),
        "deserialize_min_ms": round(min(deser_times) * 1000, 2),
        "speedup_factor": round(avg_parse / avg_deser, 1) if avg_deser > 0 else float("inf"),
        "search_avg_us": round(avg_search * 1_000_000, 2),
        "serialize_ms": round(ser_meta["serialize_time_s"] * 1000, 2),
        "runs": runs,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _format_table(data: dict[str, Any], title: str = "") -> str:
    """Format a dict as a simple aligned table."""
    lines = []
    if title:
        lines.append(f"\n{'='*60}")
        lines.append(f"  {title}")
        lines.append(f"{'='*60}")
    max_key = max(len(str(k)) for k in data.keys()) if data else 0
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"  {str(k):<{max_key}} :")
            for sk, sv in v.items():
                lines.append(f"    {str(sk):<{max_key}}  {sv}")
        else:
            lines.append(f"  {str(k):<{max_key}}  {v}")
    return "\n".join(lines)


def cmd_parse(args: argparse.Namespace) -> None:
    parser = ParamDefParser()
    model = parser.parse_files(args.files)

    output = args.output or "paramdef_snapshot.bin"
    meta = serialize(model, output, compress=not args.no_compress)

    print(f"✅ Parsed {len(args.files)} file(s) in {model.parse_time_s*1000:.1f} ms")
    print(_format_table(model.stats(), "Model Statistics"))
    print(_format_table(meta, "Serialization"))
    print(f"\n  Snapshot saved to: {output}")


def cmd_load(args: argparse.Namespace) -> None:
    model, meta = deserialize(args.snapshot)
    print(f"✅ Loaded snapshot in {meta['deserialize_time_s']*1000:.1f} ms")
    print(_format_table(model.stats(), "Model Statistics"))

    if args.tree:
        print(f"\n{'='*60}")
        print("  Container Tree")
        print(f"{'='*60}")
        print(print_tree(model, max_depth=args.depth))


def cmd_search(args: argparse.Namespace) -> None:
    model, meta = deserialize(args.snapshot)

    t0 = time.perf_counter()
    if args.path:
        results = search_by_path(model, args.path)
    else:
        results = search_by_type(model, args.type, args.name)
    search_time = time.perf_counter() - t0

    print(f"🔍 Found {len(results)} result(s) in {search_time*1_000_000:.0f} µs\n")

    for c in results:
        details = get_container_details(c)
        print(f"  📦 {details['short_name']}")
        print(f"     Path: {details['definition_path']}")
        print(f"     Multiplicity: {details['multiplicity']}")
        print(f"     Depth: {details['depth']}")
        if details["description"]:
            desc = details["description"][:120]
            print(f"     Desc: {desc}{'...' if len(details['description']) > 120 else ''}")
        if details["parameters"]:
            print(f"     Parameters ({len(details['parameters'])}):")
            for p in details["parameters"][:10]:
                extra = ""
                if p["default"] is not None:
                    extra += f" default={p['default']}"
                if p["range"]:
                    extra += f" range={p['range']}"
                if p["enum_values"]:
                    extra += f" enum={p['enum_values']}"
                print(f"       - {p['name']} ({p['type']}){extra}")
            if len(details["parameters"]) > 10:
                print(f"       ... and {len(details['parameters'])-10} more")
        if details["references"]:
            print(f"     References ({len(details['references'])}):")
            for r in details["references"][:5]:
                print(f"       - {r['name']} ({r['type']}) → {r['dest']}")
        if details["sub_containers"]:
            print(f"     Sub-containers: {', '.join(details['sub_containers'][:5])}")
        print()


def cmd_fuzzy(args: argparse.Namespace) -> None:
    model, _ = deserialize(args.snapshot)

    t0 = time.perf_counter()
    results = fuzzy_search(model, args.query, limit=args.limit)
    search_time = time.perf_counter() - t0

    print(f"🔍 Fuzzy search for '{args.query}' ({search_time*1000:.1f} ms)\n")
    for term, score in results:
        bar = "█" * int(score * 20)
        print(f"  {score:.2f} {bar:<20} {term}")


def cmd_benchmark(args: argparse.Namespace) -> None:
    results = benchmark(args.files, runs=args.runs)
    print(_format_table(results, "Benchmark Results"))
    print(f"\n  ⚡ Snapshot is {results['speedup_factor']}x faster than XML parsing")


def cmd_fingerprint(args: argparse.Namespace) -> None:
    fp = compute_fingerprint(args.files)
    print(f"SHA-256: {fp}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="AUTOSAR ParamDef Manager — Serialize, Search & Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # parse
    sp = sub.add_parser("parse", help="Parse .arxml files and create snapshot")
    sp.add_argument("files", nargs="+", help=".arxml file paths")
    sp.add_argument("-o", "--output", help="Output snapshot path")
    sp.add_argument("--no-compress", action="store_true", help="Disable gzip compression")
    sp.set_defaults(func=cmd_parse)

    # load
    sp = sub.add_parser("load", help="Load and inspect a snapshot")
    sp.add_argument("snapshot", help="Snapshot file path")
    sp.add_argument("--tree", action="store_true", help="Print container tree")
    sp.add_argument("--depth", type=int, default=-1, help="Max tree depth to display")
    sp.set_defaults(func=cmd_load)

    # search
    sp = sub.add_parser("search", help="Search containers in a snapshot")
    sp.add_argument("snapshot", help="Snapshot file path")
    sp.add_argument("--type", help="Container type (short name)")
    sp.add_argument("--name", help="Instance short name")
    sp.add_argument("--path", help="Definition path (e.g., Com/ComConfig/ComIPdu)")
    sp.set_defaults(func=cmd_search)

    # fuzzy
    sp = sub.add_parser("fuzzy", help="Fuzzy search over vocabulary")
    sp.add_argument("snapshot", help="Snapshot file path")
    sp.add_argument("--query", required=True, help="Search query")
    sp.add_argument("--limit", type=int, default=10, help="Max results")
    sp.set_defaults(func=cmd_fuzzy)

    # benchmark
    sp = sub.add_parser("benchmark", help="Benchmark parse vs deserialize")
    sp.add_argument("files", nargs="+", help=".arxml file paths")
    sp.add_argument("--runs", type=int, default=5, help="Number of runs")
    sp.set_defaults(func=cmd_benchmark)

    # fingerprint
    sp = sub.add_parser("fingerprint", help="Compute file fingerprint")
    sp.add_argument("files", nargs="+", help=".arxml file paths")
    sp.set_defaults(func=cmd_fingerprint)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
