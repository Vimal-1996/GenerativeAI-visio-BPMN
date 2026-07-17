"""Phase 4 - BPMN 2.0 XML generation.

Serializes a list of `PageGraph` objects (Phase 3) into a single BPMN
2.0 `<definitions>` document: one `<process>` per pool (wrapped in a
`<collaboration>` with `<participant>`s when a page has more than one
pool), plus a `<bpmndi:BPMNDiagram>` per page with shape bounds and edge
waypoints so the diagram looks right when opened in Signavio, not just
semantically valid.

Coordinate note: Visio's origin is bottom-left with Y increasing
upward; BPMN DI's origin is top-left with Y increasing downward, so
every coordinate is flipped against the page height on the way out.
"""
from __future__ import annotations

from lxml import etree

from .graph import PageGraph, ProcessNode

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

NSMAP = {
    None: BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "omgdc": DC_NS,
    "omgdi": DI_NS,
}

# BPMN element type -> XML tag name for flow nodes we can emit.
_NODE_TAGS = {
    "task": "task",
    "subProcess": "subProcess",
    "startEvent": "startEvent",
    "endEvent": "endEvent",
    "intermediateEvent": "intermediateThrowEvent",
    "event": "intermediateThrowEvent",
    "exclusiveGateway": "exclusiveGateway",
    "parallelGateway": "parallelGateway",
    "inclusiveGateway": "inclusiveGateway",
    "eventBasedGateway": "eventBasedGateway",
    "complexGateway": "complexGateway",
    "dataObject": "dataObjectReference",
    "dataStore": "dataStoreReference",
}

SCALE = 100.0  # Visio units (inches) -> BPMN DI coordinate units


def _bpmn(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"


def _bpmndi(tag: str) -> str:
    return f"{{{BPMNDI_NS}}}{tag}"


def _dc(tag: str) -> str:
    return f"{{{DC_NS}}}{tag}"


def _di(tag: str) -> str:
    return f"{{{DI_NS}}}{tag}"


def _flip_y(y: float, page_height: float) -> float:
    return (page_height - y) * SCALE


def _bounds_xy(x: float, y: float, width: float, height: float, page_height: float) -> tuple[float, float, float, float]:
    """Top-left x, y (BPMN DI convention) + width, height, for a shape
    whose (x, y) is its center in Visio's bottom-left-origin coordinates."""
    cx = x * SCALE
    cy = _flip_y(y, page_height)
    w = width * SCALE
    h = height * SCALE
    return cx - w / 2, cy - h / 2, w, h


def _add_bounds(parent: etree._Element, x: float, y: float, width: float, height: float, page_height: float) -> None:
    left, top, w, h = _bounds_xy(x, y, width, height, page_height)
    etree.SubElement(
        parent,
        _dc("Bounds"),
        {"x": f"{left:.2f}", "y": f"{top:.2f}", "width": f"{w:.2f}", "height": f"{h:.2f}"},
    )


def _node_center_point(node: ProcessNode, page_height: float) -> tuple[float, float]:
    return node.x * SCALE, _flip_y(node.y, page_height)


def build_definitions(pages: list[PageGraph]) -> etree._Element:
    definitions = etree.Element(
        _bpmn("definitions"),
        nsmap=NSMAP,
        attrib={"id": "Definitions_1", "targetNamespace": "http://bpmn.io/schema/bpmn"},
    )

    for page in pages:
        _add_page(definitions, page)

    return definitions


def _add_page(definitions: etree._Element, page: PageGraph) -> None:
    node_by_id = {n.id: n for n in page.nodes}
    multi_pool = len(page.pools) > 1

    collaboration = None
    if multi_pool:
        collaboration = etree.SubElement(definitions, _bpmn("collaboration"), {"id": f"Collaboration_{_safe(page.page_name)}"})

    for pool in page.pools:
        process = etree.SubElement(definitions, _bpmn("process"), {"id": f"Process_{pool.id}", "isExecutable": "false"})

        if multi_pool:
            etree.SubElement(
                collaboration,
                _bpmn("participant"),
                {"id": f"Participant_{pool.id}", "name": pool.name, "processRef": f"Process_{pool.id}"},
            )

        if pool.lanes:
            lane_set = etree.SubElement(process, _bpmn("laneSet"), {"id": f"LaneSet_{pool.id}"})
            for lane in pool.lanes:
                lane_el = etree.SubElement(lane_set, _bpmn("lane"), {"id": lane.id, "name": lane.name})
                for node_id in lane.node_ids:
                    etree.SubElement(lane_el, _bpmn("flowNodeRef")).text = node_id

        for node_id in [n for lane in pool.lanes for n in lane.node_ids] + pool.node_ids:
            node = node_by_id[node_id]
            tag = _NODE_TAGS.get(node.bpmn_type, "task")
            attrib = {"id": node.id}
            if node.name:
                attrib["name"] = node.name
            etree.SubElement(process, _bpmn(tag), attrib)

        pool_node_ids = {n for lane in pool.lanes for n in lane.node_ids} | set(pool.node_ids)
        for flow in page.flows:
            if flow.source_ref not in pool_node_ids or flow.target_ref not in pool_node_ids:
                continue
            if flow.kind == "sequenceFlow":
                attrib = {"id": flow.id, "sourceRef": flow.source_ref, "targetRef": flow.target_ref}
                if flow.name:
                    attrib["name"] = flow.name
                etree.SubElement(process, _bpmn("sequenceFlow"), attrib)
            elif flow.kind == "association":
                etree.SubElement(
                    process,
                    _bpmn("association"),
                    {"id": flow.id, "sourceRef": flow.source_ref, "targetRef": flow.target_ref},
                )

    if multi_pool:
        for flow in page.flows:
            if flow.kind == "messageFlow":
                attrib = {"id": flow.id, "sourceRef": flow.source_ref, "targetRef": flow.target_ref}
                if flow.name:
                    attrib["name"] = flow.name
                etree.SubElement(collaboration, _bpmn("messageFlow"), attrib)

    plane_element_ref = f"Collaboration_{_safe(page.page_name)}" if multi_pool else f"Process_{page.pools[0].id}"
    _add_diagram(definitions, page, plane_element_ref)


def _safe(name: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "Page"


def _add_diagram(definitions: etree._Element, page: PageGraph, plane_element_ref: str) -> None:
    diagram = etree.SubElement(
        definitions,
        _bpmndi("BPMNDiagram"),
        {"id": f"Diagram_{_safe(page.page_name)}"},
    )
    plane = etree.SubElement(diagram, _bpmndi("BPMNPlane"), {"id": f"Plane_{_safe(page.page_name)}", "bpmnElement": plane_element_ref})

    for pool in page.pools:
        if len(page.pools) > 1:
            shape = etree.SubElement(
                plane,
                _bpmndi("BPMNShape"),
                {"id": f"Shape_Participant_{pool.id}", "bpmnElement": f"Participant_{pool.id}", "isHorizontal": "true"},
            )
            _add_bounds(shape, pool.x, pool.y, pool.width, pool.height, page.height)
        for lane in pool.lanes:
            shape = etree.SubElement(
                plane,
                _bpmndi("BPMNShape"),
                {"id": f"Shape_{lane.id}", "bpmnElement": lane.id, "isHorizontal": "true"},
            )
            _add_bounds(shape, lane.x, lane.y, lane.width, lane.height, page.height)

    for node in page.nodes:
        shape = etree.SubElement(plane, _bpmndi("BPMNShape"), {"id": f"Shape_{node.id}", "bpmnElement": node.id})
        _add_bounds(shape, node.x, node.y, node.width, node.height, page.height)

    node_by_id = {n.id: n for n in page.nodes}
    for flow in page.flows:
        if flow.source_ref not in node_by_id or flow.target_ref not in node_by_id:
            continue
        edge = etree.SubElement(plane, _bpmndi("BPMNEdge"), {"id": f"Edge_{flow.id}", "bpmnElement": flow.id})
        sx, sy = _node_center_point(node_by_id[flow.source_ref], page.height)
        tx, ty = _node_center_point(node_by_id[flow.target_ref], page.height)
        etree.SubElement(edge, _di("waypoint"), {"x": f"{sx:.2f}", "y": f"{sy:.2f}"})
        etree.SubElement(edge, _di("waypoint"), {"x": f"{tx:.2f}", "y": f"{ty:.2f}"})


def generate_bpmn_xml(pages: list[PageGraph]) -> bytes:
    definitions = build_definitions(pages)
    return etree.tostring(definitions, pretty_print=True, xml_declaration=True, encoding="UTF-8")
