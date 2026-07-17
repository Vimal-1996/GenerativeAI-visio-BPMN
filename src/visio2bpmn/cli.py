"""Phase 6 - CLI entry point.

Wires the pipeline together: extraction -> classification -> process
graph -> BPMN XML generation -> XSD validation -> write output file.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .bpmn_xml import generate_bpmn_xml
from .classification import ClassifiedShape, classify_document
from .extraction import extract_document
from .graph import build_page_graph
from .validation import validate_bpmn_xml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_CONFIG = os.path.join(_REPO_ROOT, "config", "shape_mapping.yaml")

logger = logging.getLogger(__name__)


def convert(
    input_path: str,
    output_path: str,
    config_path: str = DEFAULT_CONFIG,
    use_llm_fallback: bool = True,
    skip_validation: bool = False,
) -> list[str]:
    """Run the full Visio -> BPMN pipeline for one .vsdx file.

    Returns a list of human-readable warnings (unmapped shapes, dangling
    connectors, orphan nodes, schema validation errors) - an empty list
    means a clean conversion.
    """
    document = extract_document(input_path)
    classified = classify_document(document, config_path, use_llm_fallback=use_llm_fallback)

    classified_by_page: dict[str, list[ClassifiedShape]] = {}
    for c in classified:
        classified_by_page.setdefault(c.shape.page_name, []).append(c)

    warnings: list[str] = []
    page_graphs = []
    for page in document.pages:
        page_classified = classified_by_page.get(page.name, [])
        for c in page_classified:
            if c.bpmn_type is None:
                warnings.append(
                    f"Unmapped shape id={c.shape.id} page={page.name!r} "
                    f"text={c.shape.text!r} master={c.shape.master_name!r}"
                )
        graph = build_page_graph(page, page_classified)
        warnings.extend(graph.warnings)
        page_graphs.append(graph)

    xml_bytes = generate_bpmn_xml(page_graphs)

    if not skip_validation:
        for error in validate_bpmn_xml(xml_bytes):
            warnings.append(f"Schema validation error: {error}")

    with open(output_path, "wb") as f:
        f.write(xml_bytes)

    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="visio2bpmn",
        description="Convert a Visio .vsdx file into Signavio-ready BPMN 2.0 XML",
    )
    parser.add_argument("input", help="Path to the input .vsdx file")
    parser.add_argument("-o", "--output", required=True, help="Path to write the generated .bpmn XML file")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Path to the shape-mapping config YAML (default: config/shape_mapping.yaml)",
    )
    parser.add_argument(
        "--no-llm-fallback",
        action="store_true",
        help="Disable the LLM fallback classifier for shapes the config/heuristics can't resolve",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip XSD schema validation of the generated XML",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    warnings = convert(
        input_path=args.input,
        output_path=args.output,
        config_path=args.config,
        use_llm_fallback=not args.no_llm_fallback,
        skip_validation=args.skip_validation,
    )

    print(f"Wrote {args.output}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
