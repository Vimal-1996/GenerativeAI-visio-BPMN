"""Renders a `PageGraph` as an inline SVG diagram for the Streamlit UI.

This mirrors the same coordinate transform used for the real BPMNDI
output (`bpmn_xml.py`), so the preview matches what actually ends up in
the generated .bpmn file - it isn't a separate best-effort layout.
"""
from __future__ import annotations

from .bpmn_xml import SCALE, _bounds_xy, _node_center_point
from .graph import PageGraph

_MARGIN = 40

_NODE_COLORS = {
    "task": ("#e8f0fe", "#4285f4"),
    "subProcess": ("#e8f0fe", "#4285f4"),
    "startEvent": ("#e6f4ea", "#34a853"),
    "endEvent": ("#fce8e6", "#ea4335"),
    "intermediateEvent": ("#fef7e0", "#f9ab00"),
    "event": ("#fef7e0", "#f9ab00"),
    "exclusiveGateway": ("#fef7e0", "#f9ab00"),
    "parallelGateway": ("#fef7e0", "#f9ab00"),
    "inclusiveGateway": ("#fef7e0", "#f9ab00"),
    "eventBasedGateway": ("#fef7e0", "#f9ab00"),
    "complexGateway": ("#fef7e0", "#f9ab00"),
    "dataObject": ("#f3f3f3", "#9aa0a6"),
    "dataStore": ("#f3f3f3", "#9aa0a6"),
}
_DEFAULT_COLOR = ("#f3f3f3", "#9aa0a6")
_GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway", "complexGateway"}
_EVENT_TYPES = {"startEvent", "endEvent", "intermediateEvent", "event"}


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _node_shape_svg(node, left: float, top: float, w: float, h: float) -> str:
    fill, stroke = _NODE_COLORS.get(node.bpmn_type, _DEFAULT_COLOR)
    label = _escape(node.name or node.bpmn_type)

    if node.bpmn_type in _EVENT_TYPES:
        cx, cy = left + w / 2, top + h / 2
        r = min(w, h) / 2
        shape = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    elif node.bpmn_type in _GATEWAY_TYPES:
        cx, cy = left + w / 2, top + h / 2
        points = f"{cx:.1f},{top:.1f} {left + w:.1f},{cy:.1f} {cx:.1f},{top + h:.1f} {left:.1f},{cy:.1f}"
        shape = f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    else:
        shape = (
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" ry="8" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )

    text_y = top + h + 16 if node.bpmn_type in _EVENT_TYPES | _GATEWAY_TYPES else top + h / 2 + 5
    text = (
        f'<text x="{left + w / 2:.1f}" y="{text_y:.1f}" font-size="13" font-family="sans-serif" '
        f'text-anchor="middle" fill="#202124">{label}</text>'
    )

    comment_marker = ""
    if getattr(node, "documentation", ""):
        mx, my = left + w - 6, top + 6
        comment_marker = (
            f'<g><circle cx="{mx:.1f}" cy="{my:.1f}" r="7" fill="#fbbc04" stroke="#202124" stroke-width="1"/>'
            f'<text x="{mx:.1f}" y="{my + 3.5:.1f}" font-size="9" text-anchor="middle" '
            f'font-family="sans-serif">!</text>'
            f"<title>{_escape(node.documentation)}</title></g>"
        )

    return shape + text + comment_marker


def render_page_svg(page: PageGraph) -> str:
    canvas_width = page.width * SCALE + 2 * _MARGIN
    canvas_height = page.height * SCALE + 2 * _MARGIN

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_width:.0f} {canvas_height:.0f}" '
        f'width="100%" height="{canvas_height:.0f}" font-family="sans-serif">',
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#5f6368"/></marker>',
        f'<rect x="0" y="0" width="{canvas_width:.0f}" height="{canvas_height:.0f}" fill="white"/>',
    ]

    for pool in page.pools:
        if len(page.pools) > 1:
            left, top, w, h = _bounds_xy(pool.x, pool.y, pool.width, pool.height, page.height)
            left, top = left + _MARGIN, top + _MARGIN
            parts.append(
                f'<rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="none" stroke="#5f6368" stroke-width="2"/>'
            )
            parts.append(
                f'<text x="{left + 6:.1f}" y="{top + 16:.1f}" font-size="12" font-weight="bold" '
                f'fill="#5f6368">{_escape(pool.name)}</text>'
            )
        for lane in pool.lanes:
            left, top, w, h = _bounds_xy(lane.x, lane.y, lane.width, lane.height, page.height)
            left, top = left + _MARGIN, top + _MARGIN
            parts.append(
                f'<rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="#fafafa" stroke="#bdc1c6" stroke-width="1.5"/>'
            )
            parts.append(
                f'<text x="{left + 6:.1f}" y="{top + 16:.1f}" font-size="12" font-weight="bold" '
                f'fill="#5f6368">{_escape(lane.name)}</text>'
            )

    node_by_id = {n.id: n for n in page.nodes}
    for flow in page.flows:
        if flow.source_ref not in node_by_id or flow.target_ref not in node_by_id:
            continue
        sx, sy = _node_center_point(node_by_id[flow.source_ref], page.height)
        tx, ty = _node_center_point(node_by_id[flow.target_ref], page.height)
        sx, sy, tx, ty = sx + _MARGIN, sy + _MARGIN, tx + _MARGIN, ty + _MARGIN
        dash = ' stroke-dasharray="5,4"' if flow.kind in {"messageFlow", "association"} else ""
        parts.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="#5f6368" stroke-width="1.5"{dash} marker-end="url(#arrow)"/>'
        )
        if flow.name:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            parts.append(
                f'<text x="{mx:.1f}" y="{my - 6:.1f}" font-size="11" text-anchor="middle" '
                f'fill="#202124" font-style="italic">{_escape(flow.name)}</text>'
            )

    for node in page.nodes:
        left, top, w, h = _bounds_xy(node.x, node.y, node.width, node.height, page.height)
        left, top = left + _MARGIN, top + _MARGIN
        parts.append(_node_shape_svg(node, left, top, w, h))

    parts.append("</svg>")
    return "".join(parts)
