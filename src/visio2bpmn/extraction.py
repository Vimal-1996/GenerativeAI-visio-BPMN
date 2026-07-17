"""Phase 1 - Visio extraction layer.

Reads a .vsdx file with the `vsdx` library and produces a plain,
JSON-serializable intermediate representation (the "Visio IR") of every
page: shapes with their stencil/master name, text, geometry and nesting,
plus connectors resolved to a (source, target) shape id pair.

This layer knows nothing about BPMN - that mapping happens in
`visio2bpmn.classification`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import vsdx


@dataclass
class VisioShape:
    id: str
    page_name: str
    master_name: Optional[str]
    shape_name: Optional[str]
    is_group: bool
    parent_id: Optional[str]
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class VisioConnector:
    connector_shape_id: str
    source_shape_id: Optional[str]
    target_shape_id: Optional[str]
    text: str


@dataclass
class VisioPage:
    name: str
    width: float
    height: float
    shapes: list[VisioShape] = field(default_factory=list)
    connectors: list[VisioConnector] = field(default_factory=list)


@dataclass
class VisioDocument:
    source_path: str
    pages: list[VisioPage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _shape_geometry(shape: "vsdx.Shape") -> tuple[float, float, float, float]:
    return (
        _as_float(getattr(shape, "x", None)),
        _as_float(getattr(shape, "y", None)),
        _as_float(getattr(shape, "width", None)),
        _as_float(getattr(shape, "height", None)),
    )


def _master_name(shape: "vsdx.Shape") -> Optional[str]:
    """Best-effort stencil/master name, used by the classification config lookup."""
    try:
        master_page = shape.master_page
    except Exception:
        master_page = None
    if master_page is not None:
        try:
            return master_page.name
        except Exception:
            pass
    return None


def extract_page(page: "vsdx.Page") -> VisioPage:
    all_shapes = page.all_shapes

    # Each connector (line/arrow) shape produces two Connect rows - one for its
    # BeginX end (source) and one for its EndX end (target). Group them by the
    # connector's own shape id to resolve a single source->target edge.
    connects_by_connector: dict[str, list] = {}
    for connect in page.connects:
        connects_by_connector.setdefault(connect.connector_shape_id, []).append(connect)

    connectors: list[VisioConnector] = []
    connector_shape_ids: set[str] = set()
    for connector_id, connects in connects_by_connector.items():
        connector_shape_ids.add(connector_id)
        source_id = None
        target_id = None
        for c in connects:
            if c.from_rel == "BeginX":
                source_id = c.shape_id
            elif c.from_rel == "EndX":
                target_id = c.shape_id
        connector_shape = page.find_shape_by_id(connector_id)
        connectors.append(
            VisioConnector(
                connector_shape_id=connector_id,
                source_shape_id=source_id,
                target_shape_id=target_id,
                text=(connector_shape.text or "").strip() if connector_shape else "",
            )
        )

    shapes: list[VisioShape] = []
    for shape in all_shapes:
        if shape.ID is None or shape.ID in connector_shape_ids:
            continue  # connector (line/arrow) shapes are captured above, not as process nodes
        x, y, width, height = _shape_geometry(shape)
        parent = shape.parent
        parent_id = parent.ID if isinstance(parent, vsdx.Shape) else None
        shapes.append(
            VisioShape(
                id=shape.ID,
                page_name=page.name,
                master_name=_master_name(shape),
                shape_name=getattr(shape, "shape_name", None),
                is_group=(shape.shape_type == "Group"),
                parent_id=parent_id,
                text=(shape.text or "").strip(),
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )

    return VisioPage(
        name=page.name,
        width=page.width,
        height=page.height,
        shapes=shapes,
        connectors=connectors,
    )


def extract_document(path: str) -> VisioDocument:
    pages: list[VisioPage] = []
    with vsdx.VisioFile(path) as vis:
        for page in vis.pages:
            pages.append(extract_page(page))
    return VisioDocument(source_path=path, pages=pages)
