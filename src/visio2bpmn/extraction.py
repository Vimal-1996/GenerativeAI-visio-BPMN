"""Phase 1 - Visio extraction layer.

Reads a .vsdx file with the `vsdx` library and produces a plain,
JSON-serializable intermediate representation (the "Visio IR") of every
page: shapes with their stencil/master name, text, geometry and nesting,
plus connectors resolved to a (source, target) shape id pair.

Also reads Visio's Comments feature (MS-VSDX spec 2.2.9 / 2.3.4.2.9-11) -
review comments attached to a shape or to a page - by parsing the raw
Comments XML part directly, since the `vsdx` library has no support for
it at all.

This layer knows nothing about BPMN - that mapping happens in
`visio2bpmn.classification`.
"""
from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field, asdict
from typing import Optional

import vsdx

_COMMENTS_NS = "{http://schemas.microsoft.com/office/visio/2011/1/core}"
_PKG_RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_COMMENTS_REL_TYPE = "http://schemas.microsoft.com/visio/2010/relationships/comments"


@dataclass
class VisioComment:
    author: str
    date: str
    text: str


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
    comments: list[VisioComment] = field(default_factory=list)


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
    page_id: Optional[str] = None
    shapes: list[VisioShape] = field(default_factory=list)
    connectors: list[VisioConnector] = field(default_factory=list)
    comments: list[VisioComment] = field(default_factory=list)


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
        page_id=page.page_id,
        shapes=shapes,
        connectors=connectors,
    )


def _parse_comments_part(path: str) -> list[dict]:
    """Read the document-level Comments XML part directly from the .vsdx
    zip. Returns raw records (page_id, shape_id-or-None, author, date,
    text); an empty list if the file has no comments at all."""
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                rels_xml = zf.read("visio/_rels/document.xml.rels")
            except KeyError:
                return []
            rels_root = ET.fromstring(rels_xml)
            target = next(
                (
                    rel.attrib.get("Target")
                    for rel in rels_root.findall(f"{_PKG_RELS_NS}Relationship")
                    if rel.attrib.get("Type") == _COMMENTS_REL_TYPE
                ),
                None,
            )
            if not target:
                return []
            comments_part_path = posixpath.normpath(posixpath.join("visio", target))
            comments_xml = zf.read(comments_part_path)
    except (FileNotFoundError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return []

    root = ET.fromstring(comments_xml)
    authors = {
        entry.attrib.get("ID"): entry.attrib.get("Name", "Unknown")
        for entry in root.findall(f"{_COMMENTS_NS}AuthorList/{_COMMENTS_NS}AuthorEntry")
    }

    records = []
    for entry in root.findall(f"{_COMMENTS_NS}CommentList/{_COMMENTS_NS}CommentEntry"):
        records.append(
            {
                "page_id": entry.attrib.get("PageID"),
                "shape_id": entry.attrib.get("ShapeID"),
                "author": authors.get(entry.attrib.get("AuthorID"), "Unknown"),
                "date": entry.attrib.get("Date", ""),
                "text": (entry.text or "").strip(),
            }
        )
    return records


def _attach_comments(pages: list[VisioPage], records: list[dict]) -> None:
    pages_by_id = {p.page_id: p for p in pages}
    for record in records:
        page = pages_by_id.get(record["page_id"])
        if page is None:
            continue
        comment = VisioComment(author=record["author"], date=record["date"], text=record["text"])
        shape_id = record["shape_id"]
        if shape_id:
            shape = next((s for s in page.shapes if s.id == shape_id), None)
            if shape is not None:
                shape.comments.append(comment)
            # a comment on a connector/line shape (excluded from `page.shapes`)
            # or an otherwise-unrecognized id is silently dropped
        else:
            page.comments.append(comment)


def extract_document(path: str) -> VisioDocument:
    pages: list[VisioPage] = []
    with vsdx.VisioFile(path) as vis:
        for page in vis.pages:
            pages.append(extract_page(page))

    comment_records = _parse_comments_part(path)
    if comment_records:
        _attach_comments(pages, comment_records)

    return VisioDocument(source_path=path, pages=pages)
