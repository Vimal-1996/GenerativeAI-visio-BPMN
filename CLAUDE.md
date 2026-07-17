# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Converts a Visio `.vsdx` file into standards-compliant BPMN 2.0 XML, ready to import into SAP Signavio. Pure Python, `src/` layout, package name `visio2bpmn`.

## Commands

Environment uses a `py` launcher venv (Python 3.14) on Windows, not a system `python`.

```
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Run the CLI:
```
.venv\Scripts\visio2bpmn path\to\diagram.vsdx -o output.bpmn
```
Flags: `--config <path>` (override `config/shape_mapping.yaml`), `--no-llm-fallback`, `--skip-validation`, `-v`.

Run the Streamlit UI:
```
.venv\Scripts\streamlit.exe run app.py
```

Run tests:
```
.venv\Scripts\python.exe -m pytest tests/ -v
```
Single test: `.venv\Scripts\python.exe -m pytest tests/test_graph.py::test_name -v`

Regenerate the demo `.vsdx` fixtures (there's no Visio install in this environment, so they're built programmatically via the `vsdx` library rather than hand-drawn):
```
.venv\Scripts\python.exe scripts\build_sample_fixtures.py
```

## Architecture

Five-stage pipeline, each stage a separate module in `src/visio2bpmn/`, each with its own intermediate representation. Data flows one direction; nothing later mutates an earlier stage's objects in place.

1. **`extraction.py`** - opens `.vsdx` with the [`vsdx`](https://github.com/dave-howard/vsdx) library, produces a plain "Visio IR" (`VisioDocument` → `VisioPage` → `VisioShape`/`VisioConnector`) with shape master/stencil name, text, geometry, and connectors resolved to `(source_shape_id, target_shape_id)`. Knows nothing about BPMN. Connector resolution matters here: each connector shape produces two `Connect` rows in the underlying vsdx file (`from_rel == "BeginX"` → source, `"EndX"` → target) that must be paired by connector id.

2. **`classification.py`** - maps each `VisioShape` to a BPMN element type (`ClassifiedShape`), in priority order: (a) exact master/stencil name lookup against `config/shape_mapping.yaml`, (b) geometric heuristics (currently just lane detection: a shape spanning most of the page in one dimension while elongated), (c) an LLM fallback (Claude via `anthropic`, only invoked if `ANTHROPIC_API_KEY` is set and `use_llm_fallback=True`) for whatever's still unresolved. Unresolved shapes are never guessed - they come back with `bpmn_type=None` and get reported as warnings.

3. **`graph.py`** - turns classified shapes + connectors into a `PageGraph` (pools → lanes → nodes, plus `Flow`s classified as `sequenceFlow`/`messageFlow`/`association`). Key details: lane/pool membership is geometric containment (shape center point inside container bbox), not Visio group hierarchy. IDs are prefixed with a sanitized page name because Visio shape IDs are only unique within a page. A shape classified as the ambiguous generic `"event"` type (e.g. a Visio "Terminator") gets resolved to `startEvent`/`endEvent` here based on whether it has only outgoing/only incoming flows. Orphan nodes (zero flows on either side) and dangling/unresolved connectors are collected into `graph.warnings`, not raised as exceptions.

4. **`bpmn_xml.py`** - serializes a list of `PageGraph` into one BPMN 2.0 `<definitions>` document via `lxml`. A page with >1 pool gets wrapped in `<collaboration>`/`<participant>`; a single pool is emitted as a bare `<process>` (no collaboration). Every shape/edge also gets a `<bpmndi:BPMNShape>`/`BPMNEdge` entry so the diagram lays out correctly on import, not just parses. Coordinate convention: Visio's origin is bottom-left with Y increasing upward; BPMN DI's origin is top-left with Y increasing downward - `_flip_y`/`_bounds_xy` in this module do that conversion and are reused by `diagram_svg.py` so the browser preview matches the real DI output exactly.

5. **`validation.py`** - validates generated XML against the official OMG BPMN 2.0 XSD bundle in `schemas/` (downloaded from `bpmn-io/bpmn-moddle`, not hand-written).

`cli.py` wires stages 1-5 together (`convert()`) behind an argparse CLI; `app.py` (repo root) wires the same `convert()`-equivalent logic into a Streamlit UI, plus `diagram_svg.py` for the live preview.

### Design invariants worth preserving

- Every stage produces warnings/None instead of raising on ambiguous input - unmapped shapes, dangling connectors, and orphan nodes are reported, never silently dropped or guessed. Keep this pattern when extending classification/graph logic.
- The rule-based classification path (config + geometry) is intentionally primary; the LLM is a last-resort fallback for whatever it can't resolve, not the default path. Don't invert that priority.
- `diagram_svg.py` must keep reusing `bpmn_xml.py`'s coordinate transform functions rather than reimplementing layout math, so the preview can't silently drift from the actual DI output.

## Testing conventions

- Most tests build `VisioShape`/`ClassifiedShape`/`VisioPage` objects by hand to test one pipeline stage in isolation (see the `make_shape` helpers in `tests/test_graph.py`, `tests/test_classification.py`, `tests/test_bpmn_xml.py`).
- `tests/test_extraction.py` and `tests/test_cli.py` run against a real `.vsdx` file (`fixtures/sample_basic.vsdx`, the bundled template from the `vsdx` library itself) - this is the one path that exercises actual Visio zip/XML parsing rather than mocked IR objects. Prefer adding to this real-file coverage over hand-built fixtures when testing anything in `extraction.py`.
- `tests/test_validation.py` checks generated output against the real OMG XSD, not a relaxed schema - a passing test here is a genuine correctness signal, not just internal consistency.
