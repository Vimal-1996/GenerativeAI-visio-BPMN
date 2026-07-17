# GenerativeAI-visio-BPMN

Converts a Visio `.vsdx` file into a standards-compliant BPMN 2.0 XML file, ready to import into SAP Signavio.

See `plan` history for the full phased design. Pipeline stages, in order:

1. **Extraction** (`visio2bpmn.extraction`) - parses the `.vsdx` with the [`vsdx`](https://github.com/dave-howard/vsdx) library into a plain "Visio IR": shapes (master/stencil name, text, geometry) and connectors (resolved source/target). Also reads Visio's review Comments (shape-level and page-level) directly from the file's raw XML, since `vsdx` doesn't support that part.
2. **Classification** (`visio2bpmn.classification`) - maps each shape to a BPMN element type via `config/shape_mapping.yaml`, falling back to geometric heuristics, then (optionally) an LLM call for anything still unresolved.
3. **Graph construction** (`visio2bpmn.graph`) - builds pools/lanes/nodes/flows, assigning nodes to lanes by geometric containment.
4. **BPMN XML generation** (`visio2bpmn.bpmn_xml`) - emits `<definitions>` with `<process>`/`<collaboration>` and a `<bpmndi:BPMNDiagram>` so the imported diagram is laid out correctly, not just semantically valid.
5. **Validation** (`visio2bpmn.validation`) - validates the output against the official OMG BPMN 2.0 XSD (`schemas/`).

## Setup

```
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

## Usage

```
.venv\Scripts\visio2bpmn path\to\diagram.vsdx -o output.bpmn
```

Options:
- `--config <path>` - override the shape-mapping YAML (default: `config/shape_mapping.yaml`)
- `--no-llm-fallback` - disable the LLM fallback classifier (requires `ANTHROPIC_API_KEY` when enabled)
- `--skip-validation` - skip XSD schema validation of the generated XML
- `-v` / `--verbose` - debug logging

The command prints any warnings (unmapped shapes, dangling connectors, orphan nodes, schema errors) to stderr - a clean run has none.

## Web UI

```
.venv\Scripts\streamlit.exe run app.py
```

Pick one of the pre-loaded sample diagrams (`fixtures/demo/*.vsdx`, plus the generic-shapes fixture) or upload your own `.vsdx`, then click **Convert to BPMN**. Shows conversion metrics, a live diagram preview (rendered from the same coordinates that go into the BPMNDI output), the generated XML, and any warnings - with a download button for the `.bpmn` file. Nodes with a Visio review comment attached show a small marker with a hover tooltip in the preview; the comment itself is carried into the `.bpmn` file as a `<bpmn:documentation>` element (see the "Commented process" sample).

## Tests

```
.venv\Scripts\python.exe -m pytest tests/ -v
```

`tests/test_extraction.py` and `tests/test_cli.py` run against a real `.vsdx` file (`fixtures/sample_basic.vsdx`); the rest use hand-built fixtures to test each pipeline stage in isolation.
