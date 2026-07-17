"""Phase 2 - shape classification / mapping layer.

Converts each `VisioShape` into a BPMN element type using, in priority
order:

 1. exact master/stencil name lookup against the config file
    (config/shape_mapping.yaml)
 2. geometric heuristics (currently: lane/pool detection by a shape
    spanning most of the page in one dimension while being elongated)
 3. an LLM fallback (Claude), invoked only for shapes still unresolved
    after 1 and 2 - kept as a last resort so the pipeline stays
    deterministic and cheap for the common case.

Shapes the LLM also can't confidently resolve (or that have no LLM
fallback configured) are reported as unresolved rather than guessed.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import yaml

from .extraction import VisioConnector, VisioDocument, VisioPage, VisioShape

logger = logging.getLogger(__name__)

# Fixed enum the rule-based mapping and the LLM fallback must both pick from.
BPMN_TYPES = [
    "task",
    "subProcess",
    "startEvent",
    "endEvent",
    "intermediateEvent",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
    "complexGateway",
    "event",
    "pool",
    "lane",
    "dataObject",
    "dataStore",
    "textAnnotation",
    "group",
]


@dataclass
class ClassifiedShape:
    shape: VisioShape
    bpmn_type: Optional[str]
    source: str  # "config" | "heuristic" | "llm" | "unresolved"


def load_mapping_config(path: str) -> dict[str, str]:
    """Flatten the stencil-family sections of shape_mapping.yaml into one
    case-insensitive {master_name: bpmn_type} lookup."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    mapping: dict[str, str] = {}
    for section_name, section in raw.items():
        if section_name == "geometric_fallback" or not isinstance(section, dict):
            continue
        for master_name, bpmn_type in section.items():
            mapping[master_name.strip().lower()] = bpmn_type
    return mapping


def _looks_like_lane(shape: VisioShape, page: VisioPage) -> bool:
    """A lane/pool candidate typically spans most of the page in one
    dimension while being elongated - the strongest signal available from
    bounding-box geometry alone, without inspecting Visio's raw path data."""
    if not shape.width or not shape.height:
        return False
    spans_width = shape.width >= 0.9 * page.width
    spans_height = shape.height >= 0.9 * page.height
    ratio = max(shape.width / shape.height, shape.height / shape.width)
    return (spans_width or spans_height) and ratio >= 3


def classify_shape(shape: VisioShape, page: VisioPage, mapping: dict[str, str]) -> ClassifiedShape:
    key = (shape.master_name or shape.shape_name or "").strip().lower()
    if key and key in mapping:
        return ClassifiedShape(shape=shape, bpmn_type=mapping[key], source="config")

    if _looks_like_lane(shape, page):
        return ClassifiedShape(shape=shape, bpmn_type="lane", source="heuristic")

    return ClassifiedShape(shape=shape, bpmn_type=None, source="unresolved")


def _neighbor_texts(shape: VisioShape, page: VisioPage) -> list[str]:
    neighbor_ids: set[str] = set()
    for connector in page.connectors:
        if connector.source_shape_id == shape.id and connector.target_shape_id:
            neighbor_ids.add(connector.target_shape_id)
        if connector.target_shape_id == shape.id and connector.source_shape_id:
            neighbor_ids.add(connector.source_shape_id)
    by_id = {s.id: s for s in page.shapes}
    return [by_id[nid].text for nid in neighbor_ids if nid in by_id and by_id[nid].text]


def classify_with_llm(shape: VisioShape, page: VisioPage, client) -> Optional[str]:
    """Last-resort classifier for a shape the config lookup and geometric
    heuristics couldn't resolve. Returns None (leaving the shape
    unresolved) if the model doesn't return one of BPMN_TYPES."""
    neighbors = _neighbor_texts(shape, page)
    prompt = (
        "Classify this Visio shape from a business process diagram into exactly one "
        f"BPMN element type from this list: {', '.join(BPMN_TYPES)}.\n"
        f"Shape text: {shape.text!r}\n"
        f"Shape master/stencil name: {shape.master_name or shape.shape_name or 'unknown'!r}\n"
        f"Bounding box: width={shape.width:.2f}, height={shape.height:.2f}\n"
        f"Text of directly connected shapes: {neighbors}\n"
        "Reply with only the BPMN element type, nothing else."
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip()
    except Exception:
        logger.warning("LLM classification call failed for shape %s", shape.id, exc_info=True)
        return None

    if answer in BPMN_TYPES:
        return answer
    logger.warning("LLM returned unrecognized BPMN type %r for shape %s", answer, shape.id)
    return None


def classify_document(
    document: VisioDocument,
    mapping_config_path: str,
    use_llm_fallback: bool = True,
) -> list[ClassifiedShape]:
    mapping = load_mapping_config(mapping_config_path)

    llm_client = None
    if use_llm_fallback and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        llm_client = anthropic.Anthropic()

    results: list[ClassifiedShape] = []
    for page in document.pages:
        for shape in page.shapes:
            classified = classify_shape(shape, page, mapping)
            if classified.bpmn_type is None and llm_client is not None:
                llm_type = classify_with_llm(shape, page, llm_client)
                if llm_type is not None:
                    classified = ClassifiedShape(shape=shape, bpmn_type=llm_type, source="llm")
            if classified.bpmn_type is None:
                logger.warning(
                    "Unresolved shape id=%s page=%s text=%r master=%r",
                    shape.id, page.name, shape.text, shape.master_name,
                )
            results.append(classified)
    return results
