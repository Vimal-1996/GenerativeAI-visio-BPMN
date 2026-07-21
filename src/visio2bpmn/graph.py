"""Phase 3 - process graph construction.

Turns classified shapes + connectors into a logical process graph: flow
nodes, sequence/message flows, and pool/lane containers. Visio has no
real parent/child relationship for lane membership, so nodes are
assigned to lanes/pools by geometric containment (bounding-box overlap),
using each shape's (x, y) as its center point and (width, height) as its
extent - the standard Visio pin/size convention.

Each Visio page becomes one `PageGraph`, which Phase 4 turns into its
own top-level BPMN process/collaboration + diagram. IDs are prefixed
with a sanitized page name because Visio shape IDs are only unique
within a page, not across the whole document.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .classification import ClassifiedShape
from .extraction import VisioComment, VisioHyperlink, VisioPage

CONTAINER_TYPES = {"pool", "lane"}
NON_FLOW_TYPES = {"group", "textAnnotation"}


def _page_key(page_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", page_name).strip("_") or "Page"


@dataclass
class ProcessNode:
    id: str
    bpmn_type: str
    name: str
    lane_id: Optional[str]
    pool_id: str
    x: float
    y: float
    width: float
    height: float
    documentation: str = ""


@dataclass
class Flow:
    id: str
    source_ref: str
    target_ref: str
    name: str
    kind: str  # "sequenceFlow" | "messageFlow" | "association"


@dataclass
class Lane:
    id: str
    name: str
    x: float
    y: float
    width: float
    height: float
    node_ids: list[str] = field(default_factory=list)


@dataclass
class Pool:
    id: str
    name: str
    x: float
    y: float
    width: float
    height: float
    lanes: list[Lane] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)  # nodes directly in the pool, no lane


@dataclass
class PageGraph:
    page_name: str
    width: float
    height: float
    pools: list[Pool] = field(default_factory=list)
    nodes: list[ProcessNode] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    documentation: str = ""


def _format_comments(comments: list[VisioComment]) -> str:
    return "\n".join(f"{c.author} ({c.date}): {c.text}" for c in comments if c.text)


def _format_hyperlink(link: VisioHyperlink) -> Optional[str]:
    if link.address:
        target = f"{link.address}#{link.sub_address}" if link.sub_address else link.address
        text = f"Hyperlink: {target}"
    elif link.sub_address:
        text = f"Hyperlink: continues on page {link.sub_address!r}"
    else:
        return None
    return f"{text} — {link.description}" if link.description else text


def _format_hyperlinks(hyperlinks: list[VisioHyperlink]) -> str:
    return "\n".join(text for text in (_format_hyperlink(link) for link in hyperlinks) if text)


def _combine_documentation(*parts: str) -> str:
    return "\n".join(p for p in parts if p)


def _bbox(shape: ClassifiedShape) -> tuple[float, float, float, float]:
    s = shape.shape
    return (s.x - s.width / 2, s.x + s.width / 2, s.y - s.height / 2, s.y + s.height / 2)


def _area(shape: ClassifiedShape) -> float:
    return shape.shape.width * shape.shape.height


def _contains(container: ClassifiedShape, node: ClassifiedShape) -> bool:
    cx0, cx1, cy0, cy1 = _bbox(container)
    nx, ny = node.shape.x, node.shape.y
    return cx0 <= nx <= cx1 and cy0 <= ny <= cy1


def _best_container(node: ClassifiedShape, containers: list[ClassifiedShape]) -> Optional[ClassifiedShape]:
    candidates = [c for c in containers if c is not node and _contains(c, node)]
    if not candidates:
        return None
    return min(candidates, key=_area)


def build_page_graph(page: VisioPage, classified: list[ClassifiedShape]) -> PageGraph:
    graph = PageGraph(
        page_name=page.name,
        width=page.width,
        height=page.height,
        documentation=_format_comments(page.comments),
    )
    key = _page_key(page.name)
    by_id = {c.shape.id: c for c in classified}

    lane_shapes = [c for c in classified if c.bpmn_type == "lane"]
    pool_shapes = [c for c in classified if c.bpmn_type == "pool"]
    node_shapes = [
        c for c in classified
        if c.bpmn_type is not None and c.bpmn_type not in CONTAINER_TYPES | NON_FLOW_TYPES
    ]

    # Map each lane shape to its containing pool shape (if any); a lane with
    # no containing pool shape gets an implicit pool synthesized for it.
    lane_to_pool_shape: dict[str, Optional[ClassifiedShape]] = {
        lane.shape.id: _best_container(lane, pool_shapes) for lane in lane_shapes
    }

    pools_by_key: dict[str, Pool] = {}

    def get_or_create_pool(pool_shape: Optional[ClassifiedShape], fallback_name: str) -> Pool:
        pool_key = pool_shape.shape.id if pool_shape else "__implicit__"
        if pool_key not in pools_by_key:
            if pool_shape:
                name = pool_shape.shape.text.strip() or fallback_name
                x, y, w, h = pool_shape.shape.x, pool_shape.shape.y, pool_shape.shape.width, pool_shape.shape.height
            else:
                name = fallback_name
                x, y, w, h = page.width / 2, page.height / 2, page.width, page.height
            pool = Pool(id=f"Pool_{key}_{pool_key}", name=name, x=x, y=y, width=w, height=h)
            pools_by_key[pool_key] = pool
            graph.pools.append(pool)
        return pools_by_key[pool_key]

    default_pool_name = page.name

    lane_id_by_shape_id: dict[str, str] = {}
    lane_obj_by_id: dict[str, Lane] = {}
    for lane_shape in lane_shapes:
        pool_shape = lane_to_pool_shape[lane_shape.shape.id]
        pool = get_or_create_pool(pool_shape, default_pool_name)
        lane = Lane(
            id=f"Lane_{key}_{lane_shape.shape.id}",
            name=lane_shape.shape.text.strip() or lane_shape.shape.id,
            x=lane_shape.shape.x,
            y=lane_shape.shape.y,
            width=lane_shape.shape.width,
            height=lane_shape.shape.height,
        )
        pool.lanes.append(lane)
        lane_id_by_shape_id[lane_shape.shape.id] = lane.id
        lane_obj_by_id[lane.id] = lane

    if not pool_shapes and not lane_shapes:
        get_or_create_pool(None, default_pool_name)

    def default_pool() -> Pool:
        return get_or_create_pool(None, default_pool_name)

    for node_shape in node_shapes:
        s = node_shape.shape
        node_id = f"{key}_{s.id}"
        lane_shape = _best_container(node_shape, lane_shapes)
        if lane_shape is not None:
            lane_id = lane_id_by_shape_id[lane_shape.shape.id]
            pool = get_or_create_pool(lane_to_pool_shape[lane_shape.shape.id], default_pool_name)
            pool_id = pool.id
            lane_obj_by_id[lane_id].node_ids.append(node_id)
        else:
            pool_shape = _best_container(node_shape, pool_shapes)
            pool = get_or_create_pool(pool_shape, default_pool_name) if pool_shape else default_pool()
            pool_id = pool.id
            lane_id = None
            pool.node_ids.append(node_id)

        graph.nodes.append(
            ProcessNode(
                id=node_id,
                bpmn_type=node_shape.bpmn_type,
                name=s.text.strip(),
                lane_id=lane_id,
                pool_id=pool_id,
                x=s.x,
                y=s.y,
                width=s.width,
                height=s.height,
                documentation=_combine_documentation(_format_comments(s.comments), _format_hyperlinks(s.hyperlinks)),
            )
        )

    node_pool_id = {n.id: n.pool_id for n in graph.nodes}

    for connector in page.connectors:
        if not connector.source_shape_id or not connector.target_shape_id:
            graph.warnings.append(
                f"Dangling connector {connector.connector_shape_id} on page {page.name!r} "
                f"(source={connector.source_shape_id}, target={connector.target_shape_id})"
            )
            continue
        if connector.source_shape_id not in by_id or connector.target_shape_id not in by_id:
            graph.warnings.append(
                f"Connector {connector.connector_shape_id} on page {page.name!r} references a "
                f"missing shape - skipped"
            )
            continue

        source_id = f"{key}_{connector.source_shape_id}"
        target_id = f"{key}_{connector.target_shape_id}"
        if source_id not in node_pool_id or target_id not in node_pool_id:
            graph.warnings.append(
                f"Connector {connector.connector_shape_id} on page {page.name!r} references an "
                f"unclassified shape - skipped"
            )
            continue

        source_type = by_id[connector.source_shape_id].bpmn_type
        target_type = by_id[connector.target_shape_id].bpmn_type
        if source_type in {"dataObject", "dataStore"} or target_type in {"dataObject", "dataStore"}:
            kind = "association"
        elif node_pool_id[source_id] != node_pool_id[target_id]:
            kind = "messageFlow"
        else:
            kind = "sequenceFlow"

        graph.flows.append(
            Flow(
                id=f"Flow_{key}_{connector.connector_shape_id}",
                source_ref=source_id,
                target_ref=target_id,
                name=connector.text.strip(),
                kind=kind,
            )
        )

    for node in graph.nodes:
        has_incoming = any(f.target_ref == node.id for f in graph.flows)
        has_outgoing = any(f.source_ref == node.id for f in graph.flows)

        if node.bpmn_type == "event":
            # ambiguous generic terminator (e.g. Visio's "Terminator" shape) -
            # resolve start vs end by its position in the flow graph
            if has_outgoing and not has_incoming:
                node.bpmn_type = "startEvent"
            elif has_incoming and not has_outgoing:
                node.bpmn_type = "endEvent"
            # otherwise (both, or neither) leave as a generic intermediate event

        if not has_incoming and not has_outgoing:
            graph.warnings.append(
                f"Orphan node {node.id!r} ({node.bpmn_type}) on page {page.name!r} has no connected flows"
            )

    return graph


def build_graph(classified_by_page: dict[str, tuple[VisioPage, list[ClassifiedShape]]]) -> list[PageGraph]:
    return [build_page_graph(page, classified) for page, classified in classified_by_page.values()]
