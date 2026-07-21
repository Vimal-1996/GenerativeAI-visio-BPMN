"""One-off script that builds the demo .vsdx fixtures under fixtures/demo/.

There's no Visio installation available in this environment, so these
aren't hand-drawn diagrams - they're built programmatically with the
`vsdx` library's own shape-copy and Connect.create() APIs, starting from
the small template it ships internally (vsdx/media/media.vsdx). Each
shape's NameU attribute is set directly to a real Visio stencil name
(e.g. "Process", "Decision", "Terminator") so the demo actually
exercises visio2bpmn's config-based classification lookup, not just the
geometric fallback.

Re-run with: .venv/Scripts/python.exe scripts/build_sample_fixtures.py
"""
from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

import vsdx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_VSDX = os.path.join(REPO_ROOT, ".venv", "Lib", "site-packages", "vsdx", "media", "media.vsdx")
OUT_DIR = os.path.join(REPO_ROOT, "fixtures", "demo")

# Visio's Comments feature (MS-VSDX spec, section 2.2.9 / 2.3.4.2.9-11) isn't
# supported by the `vsdx` library at all - reading OR writing. This part is
# injected by rewriting the saved .vsdx's zip directly, independent of vsdx.
COMMENTS_NS = "http://schemas.microsoft.com/office/visio/2011/1/core"


def _build_comments_xml(comments: list[dict]) -> bytes:
    authors: dict[str, str] = {}
    for c in comments:
        authors.setdefault(c["author"], c.get("initials", "".join(w[0] for w in c["author"].split())[:3].upper()))
    author_ids = {name: str(i + 1) for i, name in enumerate(authors)}

    author_entries = "".join(
        f'<AuthorEntry ID="{author_ids[name]}" Name="{name}" Initials="{initials}"/>'
        for name, initials in authors.items()
    )
    comment_entries = []
    for i, c in enumerate(comments, start=1):
        shape_attr = f' ShapeID="{c["shape_id"]}"' if c.get("shape_id") else ""
        comment_entries.append(
            f'<CommentEntry AuthorID="{author_ids[c["author"]]}" PageID="{c["page_id"]}"{shape_attr} '
            f'Date="{c["date"]}" CommentID="{i}">{c["text"]}</CommentEntry>'
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Comments xmlns="{COMMENTS_NS}">'
        f'<AuthorList>{author_entries}</AuthorList>'
        f'<CommentList>{"".join(comment_entries)}</CommentList>'
        "</Comments>"
    )
    return xml.encode("utf-8")


def add_comments_to_vsdx(path: str, comments: list[dict]) -> None:
    """Post-process a saved .vsdx to inject a real Comments XML part:
    visio/comments/comments1.xml, plus the [Content_Types].xml override and
    the visio/_rels/document.xml.rels relationship that make it discoverable.
    Rewrites the whole zip since those two parts must be edited in place.

    Each comment dict: {"page_id": str, "shape_id": str | None, "author": str,
    "date": str (ISO 8601), "text": str}.
    """
    tmp_path = path + ".tmp"
    with zipfile.ZipFile(path, "r") as src:
        content_types = src.read("[Content_Types].xml").decode("utf-8")
        doc_rels = src.read("visio/_rels/document.xml.rels").decode("utf-8")

        content_types = content_types.replace(
            "</Types>",
            '<Override PartName="/visio/comments/comments1.xml" '
            'ContentType="application/vnd.ms-visio.comments+xml" /></Types>',
        )
        doc_rels = doc_rels.replace(
            "</ns0:Relationships>",
            '<ns0:Relationship Id="rIdComments1" '
            'Type="http://schemas.microsoft.com/visio/2010/relationships/comments" '
            'Target="comments/comments1.xml" /></ns0:Relationships>',
        )

        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename == "[Content_Types].xml":
                    dst.writestr(item, content_types)
                elif item.filename == "visio/_rels/document.xml.rels":
                    dst.writestr(item, doc_rels)
                else:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr("visio/comments/comments1.xml", _build_comments_xml(comments))

    shutil.move(tmp_path, path)


def _remove_connects_referencing(page: vsdx.Page, shape_ids: set[str]) -> None:
    """`Shape.remove()` only removes the <Shape> element itself, leaving any
    <Connect> rows that reference it as dangling XML. Strip those too, or
    our own extraction layer reports them as connectors to a missing shape."""
    connects_container = page.xml.find(f".//{vsdx.namespace}Connects")
    if connects_container is None:
        return
    for connect_el in list(connects_container.findall(f"{vsdx.namespace}Connect")):
        if connect_el.attrib.get("FromSheet") in shape_ids or connect_el.attrib.get("ToSheet") in shape_ids:
            connects_container.remove(connect_el)


def _set_master_name(shape: vsdx.Shape, name: str) -> None:
    shape.xml.attrib["NameU"] = name
    shape.xml.attrib["Name"] = name


def _add_hyperlink(shape: vsdx.Shape, *, address: str = "", sub_address: str = "", description: str = "") -> None:
    """Attach a Hyperlink row directly to a shape's own XML (Section
    N="Hyperlink" of Row/Cell elements) - `vsdx` has no authoring API for
    this (same gap as Comments), but unlike Comments this section lives
    inline on the shape itself, so it's just an ElementTree insert rather
    than post-save zip surgery. address="" + sub_address=<page name> is
    Visio's convention for a same-document link to another page (what an
    "Off-page Reference" shape uses)."""
    section = ET.SubElement(shape.xml, f"{vsdx.namespace}Section", {"N": "Hyperlink"})
    row = ET.SubElement(section, f"{vsdx.namespace}Row", {"IX": "0"})
    ET.SubElement(row, f"{vsdx.namespace}Cell", {"N": "Address", "V": address})
    ET.SubElement(row, f"{vsdx.namespace}Cell", {"N": "SubAddress", "V": sub_address})
    ET.SubElement(row, f"{vsdx.namespace}Cell", {"N": "Description", "V": description})


def _place(shape: vsdx.Shape, x: float, y: float, width: float, height: float, text: str, master_name: str = "") -> None:
    shape.x = x
    shape.y = y
    shape.width = width
    shape.height = height
    shape.text = text
    if master_name:
        _set_master_name(shape, master_name)
    else:
        shape.xml.attrib.pop("NameU", None)
        shape.xml.attrib.pop("Name", None)


def build_simple_task_flow(path: str) -> None:
    """Start -> Task -> End, reusing the template's existing shapes/connector."""
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page = vis.pages[0]
        start = page.find_shape_by_id("1")   # RECTANGLE -> repurposed as start terminator
        task = page.find_shape_by_id("2")    # CONNECTED_SHAPE -> repurposed as the task
        circle = page.find_shape_by_id("7")  # CIRCLE -> repurposed as end terminator
        curved_connector = page.find_shape_by_id("5")
        line = page.find_shape_by_id("8")

        curved_connector.remove()  # duplicate of the straight connector between shapes 1 and 2
        line.remove()              # unused decoration shape
        _remove_connects_referencing(page, {"5"})

        _place(start, x=1.5, y=9.0, width=1.2, height=0.8, text="Start", master_name="Terminator")
        _place(task, x=4.0, y=9.0, width=2.0, height=1.0, text="Review Application", master_name="Process")
        _place(circle, x=6.5, y=9.0, width=1.2, height=0.8, text="End", master_name="Terminator")
        page.find_shape_by_id("3").text = ""  # clear the template's leftover connector label

        vsdx.Connect.create(page=page, from_shape=task, to_shape=circle)
        # the template's pre-existing straight connector (id=3) already links shape 1 (start) -> shape 2 (task)

        vis.save_vsdx(path)


def build_approval_gateway(path: str) -> None:
    """Start -> Submit -> Decision -> (Approve | Reject) -> End."""
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page = vis.pages[0]
        rect_template = page.find_shape_by_id("1")
        circle_template = page.find_shape_by_id("7")
        page.find_shape_by_id("5").remove()  # duplicate connector
        page.find_shape_by_id("2").remove()  # extra template shape, not needed here
        page.find_shape_by_id("8").remove()  # unused decoration shape
        page.find_shape_by_id("3").remove()  # connector referencing the deleted shape 2
        _remove_connects_referencing(page, {"2", "3", "5"})

        start = circle_template
        submit = rect_template
        decision = rect_template.copy(page)
        approve = rect_template.copy(page)
        reject = rect_template.copy(page)
        end = circle_template.copy(page)

        _place(start, x=1.2, y=9.5, width=1.0, height=0.7, text="Start", master_name="Terminator")
        _place(submit, x=3.2, y=9.5, width=1.8, height=1.0, text="Submit Expense Report", master_name="Process")
        _place(decision, x=5.6, y=9.5, width=1.6, height=1.2, text="Approved?", master_name="Decision")
        _place(approve, x=8.0, y=10.7, width=1.8, height=1.0, text="Process Reimbursement", master_name="Process")
        _place(reject, x=8.0, y=8.3, width=1.8, height=1.0, text="Notify Rejection", master_name="Process")
        _place(end, x=10.2, y=9.5, width=1.0, height=0.7, text="End", master_name="Terminator")

        vsdx.Connect.create(page=page, from_shape=start, to_shape=submit)
        vsdx.Connect.create(page=page, from_shape=submit, to_shape=decision)
        c_yes = vsdx.Connect.create(page=page, from_shape=decision, to_shape=approve)
        c_yes.text = "Yes"
        c_no = vsdx.Connect.create(page=page, from_shape=decision, to_shape=reject)
        c_no.text = "No"
        vsdx.Connect.create(page=page, from_shape=approve, to_shape=end)
        vsdx.Connect.create(page=page, from_shape=reject, to_shape=end)

        vis.save_vsdx(path)


def build_cross_functional_process(path: str) -> None:
    """Two swimlanes (detected by geometry, not by stencil name) with a
    process that crosses between them."""
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page = vis.pages[0]
        rect_template = page.find_shape_by_id("1")
        circle_template = page.find_shape_by_id("7")
        page.find_shape_by_id("5").remove()
        page.find_shape_by_id("2").remove()
        page.find_shape_by_id("8").remove()
        page.find_shape_by_id("3").remove()
        _remove_connects_referencing(page, {"2", "3", "5"})

        lane_top = rect_template
        lane_bottom = rect_template.copy(page)
        # wide, shallow, page-spanning rectangles -> caught by the lane
        # geometric heuristic in classification.py, no stencil name needed
        _place(lane_top, x=page.width / 2, y=9.0, width=page.width * 0.95, height=2.0, text="Requester", master_name="")
        _place(lane_bottom, x=page.width / 2, y=5.5, width=page.width * 0.95, height=2.0, text="Manager", master_name="")

        start = circle_template
        submit = rect_template.copy(page)
        review = rect_template.copy(page)
        approve = rect_template.copy(page)
        end = circle_template.copy(page)

        _place(start, x=1.2, y=9.0, width=0.8, height=0.6, text="Start", master_name="Terminator")
        _place(submit, x=3.2, y=9.0, width=1.8, height=1.0, text="Submit Timesheet", master_name="Process")
        _place(review, x=5.6, y=5.5, width=1.8, height=1.0, text="Review Timesheet", master_name="Process")
        _place(approve, x=5.6, y=9.0, width=1.8, height=1.0, text="Confirm Approval", master_name="Process")
        _place(end, x=8.0, y=9.0, width=0.8, height=0.6, text="End", master_name="Terminator")

        vsdx.Connect.create(page=page, from_shape=start, to_shape=submit)
        vsdx.Connect.create(page=page, from_shape=submit, to_shape=review)
        vsdx.Connect.create(page=page, from_shape=review, to_shape=approve)
        vsdx.Connect.create(page=page, from_shape=approve, to_shape=end)

        vis.save_vsdx(path)


def build_commented_process(path: str) -> None:
    """Same Start -> Task -> End shape as simple_task_flow, plus a real
    Visio Comments part: one comment attached to the task shape, one
    page-level comment (no ShapeID) attached to the page itself."""
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page = vis.pages[0]
        start = page.find_shape_by_id("1")
        task = page.find_shape_by_id("2")
        circle = page.find_shape_by_id("7")
        page.find_shape_by_id("5").remove()
        page.find_shape_by_id("8").remove()
        _remove_connects_referencing(page, {"5"})

        _place(start, x=1.5, y=9.0, width=1.2, height=0.8, text="Start", master_name="Terminator")
        _place(task, x=4.0, y=9.0, width=2.0, height=1.0, text="Review Application", master_name="Process")
        _place(circle, x=6.5, y=9.0, width=1.2, height=0.8, text="End", master_name="Terminator")
        page.find_shape_by_id("3").text = ""

        vsdx.Connect.create(page=page, from_shape=task, to_shape=circle)

        page_id = page.page_id
        task_shape_id = task.ID

        vis.save_vsdx(path)

    add_comments_to_vsdx(
        path,
        [
            {
                "page_id": page_id,
                "shape_id": task_shape_id,
                "author": "Jane Reviewer",
                "date": "2026-07-15T10:30:00.000",
                "text": "Needs manager sign-off before this step can be marked complete.",
            },
            {
                "page_id": page_id,
                "shape_id": None,
                "author": "Jane Reviewer",
                "date": "2026-07-15T10:32:00.000",
                "text": "Overall process still awaiting legal review.",
            },
        ],
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    build_simple_task_flow(os.path.join(OUT_DIR, "simple_task_flow.vsdx"))
    build_approval_gateway(os.path.join(OUT_DIR, "approval_gateway.vsdx"))
    build_cross_functional_process(os.path.join(OUT_DIR, "cross_functional_process.vsdx"))
    build_commented_process(os.path.join(OUT_DIR, "commented_process.vsdx"))
    print(f"Wrote demo fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()
