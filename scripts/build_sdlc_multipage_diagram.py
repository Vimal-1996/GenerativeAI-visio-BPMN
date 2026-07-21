"""Builds a 3-page SDLC demo diagram at fixtures/demo/sdlc_multipage.vsdx,
splitting the single-page flow from build_sdlc_diagram.py across pages by
phase - specifically to exercise visio2bpmn's multi-page handling (per-page
id-prefixing in graph.py, per-page collaboration/diagram emission in
bpmn_xml.py, and cross-page PageID-scoped Comments matching in
extraction.py) against a real multi-page .vsdx file.

Pages 1 and 2 also carry a real Off-page Reference shape with a Visio
Hyperlink (Address="", SubAddress=<next page's name>) linking them to the
following page, the standard Visio pattern for "continues elsewhere" -
this exercises extraction.py's Hyperlink-section parsing and graph.py's
hyperlink-to-documentation formatting end to end.

Same approach as build_sample_fixtures.py / build_sdlc_diagram.py: no Visio
install in this environment, so the diagram is built programmatically with
the `vsdx` library, starting from its own bundled template
(vsdx/media/media.vsdx).

Page-id quirk: `VisioFile.add_page()`/`add_page_at()`/`copy_page()` all
construct the new `Page` object with `page_id=''` hardcoded
(vsdx/vsdxfile.py `_create_page`), even though the correct numeric ID is
written into pages.xml. That empty page_id breaks `Page.width`/`.height`
(they look up PageSheet by page_id) and would break our own comment-to-page
matching (add_comments_to_vsdx keys comments by page_id). _fix_page_id()
below reads the real ID back out of pages.xml immediately after adding a
page and patches the live Page object, matching what a loaded-from-disk
page would have.

Re-run with: .venv/Scripts/python.exe scripts/build_sdlc_multipage_diagram.py
"""
from __future__ import annotations

import os

import vsdx

from build_sample_fixtures import MEDIA_VSDX, _add_hyperlink, _place, _remove_connects_referencing, add_comments_to_vsdx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "fixtures", "demo")

PAGE_WIDTH = 24.0
PAGE_HEIGHT = 14.0
LANE_WIDTH = 23.0
LANE_X = PAGE_WIDTH / 2

T = "Terminator"
P = "Process"
D = "Decision"


def _fix_page_id(vis: vsdx.VisioFile, page: vsdx.Page) -> None:
    root = vis.pages_xml.getroot() if hasattr(vis.pages_xml, "getroot") else vis.pages_xml
    page_element = root.find(f'{vsdx.namespace}Page[@Name="{page.name}"]')
    page.page_id = page_element.attrib["ID"]


def _size_page(page: vsdx.Page) -> None:
    page.width = PAGE_WIDTH
    page.height = PAGE_HEIGHT


def _add_lane(template: vsdx.Shape, page: vsdx.Page, y: float, height: float, text: str) -> vsdx.Shape:
    lane = template.copy(page)
    _place(lane, x=LANE_X, y=y, width=LANE_WIDTH, height=height, text=text, master_name="")
    return lane


def build_planning_and_design_page(vis: vsdx.VisioFile) -> tuple[vsdx.Page, dict]:
    """Lanes: Product Owner, Development.
    Start -> Gather Requirements -> Write User Stories -> Design Solution ->
    Design Approved? -> [No: Revise Design -> loop to Design Solution]
                      -> [Yes: End]
    """
    page = vis.pages[0]
    page.name = "Planning & Design"
    _size_page(page)

    rect_template = page.find_shape_by_id("1")
    circle_template = page.find_shape_by_id("7")
    for stale_id in ("2", "3", "5", "8"):
        page.find_shape_by_id(stale_id).remove()
    _remove_connects_referencing(page, {"2", "3", "5", "8"})

    lane_po = _add_lane(rect_template, page, y=10.5, height=3.0, text="Product Owner")
    lane_dev = _add_lane(rect_template, page, y=7.0, height=3.0, text="Development")

    start = circle_template
    req = rect_template  # reuse directly so the template shape isn't left over, unclassified
    stories = rect_template.copy(page)
    design = rect_template.copy(page)
    design_decision = rect_template.copy(page)
    revise_design = rect_template.copy(page)
    to_build_test = rect_template.copy(page)
    end = circle_template.copy(page)

    _place(start, x=1.5, y=10.5, width=1.0, height=0.7, text="Start", master_name=T)
    _place(req, x=4.0, y=10.5, width=2.4, height=1.1, text="Gather Requirements", master_name=P)
    _place(stories, x=7.0, y=10.5, width=2.4, height=1.1, text="Write User Stories", master_name=P)
    _place(design, x=7.0, y=7.0, width=2.4, height=1.1, text="Design Solution", master_name=P)
    _place(design_decision, x=10.0, y=10.5, width=2.0, height=1.5, text="Design Approved?", master_name=D)
    _place(revise_design, x=10.0, y=7.0, width=2.4, height=1.1, text="Revise Design", master_name=P)
    _place(to_build_test, x=13.0, y=10.5, width=2.4, height=1.1, text="Continue to Build & Test", master_name="Off-page Reference")
    _place(end, x=16.0, y=10.5, width=1.0, height=0.7, text="End", master_name=T)
    _add_hyperlink(to_build_test, sub_address="Build & Test", description="Design approved - continues in the Build & Test phase")

    vsdx.Connect.create(page=page, from_shape=start, to_shape=req)
    vsdx.Connect.create(page=page, from_shape=req, to_shape=stories)
    vsdx.Connect.create(page=page, from_shape=stories, to_shape=design)
    vsdx.Connect.create(page=page, from_shape=design, to_shape=design_decision)
    c = vsdx.Connect.create(page=page, from_shape=design_decision, to_shape=revise_design)
    c.text = "No"
    vsdx.Connect.create(page=page, from_shape=revise_design, to_shape=design)
    c = vsdx.Connect.create(page=page, from_shape=design_decision, to_shape=to_build_test)
    c.text = "Yes"
    vsdx.Connect.create(page=page, from_shape=to_build_test, to_shape=end)

    comment_targets = {"design_decision_id": design_decision.ID}
    return page, comment_targets


def build_build_and_test_page(vis: vsdx.VisioFile, rect_source: vsdx.Shape, circle_source: vsdx.Shape) -> tuple[vsdx.Page, dict]:
    """Lanes: Development, QA / Testing, DevOps / Release.
    Start -> Develop Code -> Code Review -> Unit Testing -> Deploy to QA
    Environment -> QA Testing -> Bugs Found? -> [Yes: Fix Bugs -> loop to
    Code Review] -> [No: End]
    """
    page = vis.add_page("Build & Test")
    _fix_page_id(vis, page)
    _size_page(page)

    lane_dev = _add_lane(rect_source, page, y=11.0, height=2.6, text="Development")
    lane_qa = _add_lane(rect_source, page, y=7.5, height=2.6, text="QA / Testing")
    lane_devops = _add_lane(rect_source, page, y=4.0, height=2.6, text="DevOps / Release")

    start = circle_source.copy(page)
    develop = rect_source.copy(page)
    code_review = rect_source.copy(page)
    unit_test = rect_source.copy(page)
    deploy_qa = rect_source.copy(page)
    qa_test = rect_source.copy(page)
    bugs_decision = rect_source.copy(page)
    fix_bugs = rect_source.copy(page)
    to_release_ops = rect_source.copy(page)
    end = circle_source.copy(page)

    _place(start, x=1.5, y=11.0, width=1.0, height=0.7, text="Start", master_name=T)
    _place(develop, x=4.0, y=11.0, width=2.4, height=1.1, text="Develop Code", master_name=P)
    _place(code_review, x=7.0, y=11.0, width=2.4, height=1.1, text="Code Review", master_name=P)
    _place(unit_test, x=10.0, y=11.0, width=2.4, height=1.1, text="Unit Testing", master_name=P)
    _place(deploy_qa, x=10.0, y=4.0, width=2.6, height=1.1, text="Deploy to QA Environment", master_name=P)
    _place(qa_test, x=13.0, y=7.5, width=2.4, height=1.1, text="QA Testing", master_name=P)
    _place(bugs_decision, x=16.0, y=7.5, width=2.0, height=1.5, text="Bugs Found?", master_name=D)
    _place(fix_bugs, x=16.0, y=11.0, width=2.4, height=1.1, text="Fix Bugs", master_name=P)
    _place(to_release_ops, x=19.0, y=7.5, width=2.6, height=1.1, text="Continue to Release & Operations", master_name="Off-page Reference")
    _place(end, x=22.0, y=7.5, width=1.0, height=0.7, text="End", master_name=T)
    _add_hyperlink(to_release_ops, sub_address="Release & Operations", description="No bugs found - continues in the Release & Operations phase")

    vsdx.Connect.create(page=page, from_shape=start, to_shape=develop)
    vsdx.Connect.create(page=page, from_shape=develop, to_shape=code_review)
    vsdx.Connect.create(page=page, from_shape=code_review, to_shape=unit_test)
    vsdx.Connect.create(page=page, from_shape=unit_test, to_shape=deploy_qa)
    vsdx.Connect.create(page=page, from_shape=deploy_qa, to_shape=qa_test)
    vsdx.Connect.create(page=page, from_shape=qa_test, to_shape=bugs_decision)
    c = vsdx.Connect.create(page=page, from_shape=bugs_decision, to_shape=fix_bugs)
    c.text = "Yes"
    vsdx.Connect.create(page=page, from_shape=fix_bugs, to_shape=code_review)
    c = vsdx.Connect.create(page=page, from_shape=bugs_decision, to_shape=to_release_ops)
    c.text = "No"
    vsdx.Connect.create(page=page, from_shape=to_release_ops, to_shape=end)

    comment_targets = {"qa_test_id": qa_test.ID}
    return page, comment_targets


def build_release_and_operations_page(vis: vsdx.VisioFile, rect_source: vsdx.Shape, circle_source: vsdx.Shape) -> vsdx.Page:
    """Lanes: Product Owner, DevOps / Release, Operations / Support.
    Start -> User Acceptance Testing -> UAT Approved? ->
    [No: Request Rework -> End] -> [Yes: Deploy to Production ->
    Monitor & Support -> End]
    """
    page = vis.add_page("Release & Operations")
    _fix_page_id(vis, page)
    _size_page(page)

    lane_po = _add_lane(rect_source, page, y=11.0, height=2.6, text="Product Owner")
    lane_devops = _add_lane(rect_source, page, y=7.5, height=2.6, text="DevOps / Release")
    lane_ops = _add_lane(rect_source, page, y=4.0, height=2.6, text="Operations / Support")

    start = circle_source.copy(page)
    uat = rect_source.copy(page)
    uat_decision = rect_source.copy(page)
    request_rework = rect_source.copy(page)
    rejected_end = circle_source.copy(page)
    deploy_prod = rect_source.copy(page)
    monitor = rect_source.copy(page)
    end = circle_source.copy(page)

    _place(start, x=1.5, y=11.0, width=1.0, height=0.7, text="Start", master_name=T)
    _place(uat, x=4.0, y=11.0, width=2.6, height=1.1, text="User Acceptance Testing", master_name=P)
    _place(uat_decision, x=7.2, y=11.0, width=2.0, height=1.5, text="UAT Approved?", master_name=D)
    _place(request_rework, x=7.2, y=7.5, width=2.4, height=1.1, text="Request Rework", master_name=P)
    _place(rejected_end, x=10.2, y=7.5, width=1.0, height=0.7, text="End", master_name=T)
    _place(deploy_prod, x=10.2, y=11.0, width=2.6, height=1.1, text="Deploy to Production", master_name=P)
    _place(monitor, x=13.5, y=4.0, width=2.4, height=1.1, text="Monitor & Support", master_name=P)
    _place(end, x=16.5, y=4.0, width=1.0, height=0.7, text="End", master_name=T)

    vsdx.Connect.create(page=page, from_shape=start, to_shape=uat)
    vsdx.Connect.create(page=page, from_shape=uat, to_shape=uat_decision)
    c = vsdx.Connect.create(page=page, from_shape=uat_decision, to_shape=request_rework)
    c.text = "No"
    vsdx.Connect.create(page=page, from_shape=request_rework, to_shape=rejected_end)
    c = vsdx.Connect.create(page=page, from_shape=uat_decision, to_shape=deploy_prod)
    c.text = "Yes"
    vsdx.Connect.create(page=page, from_shape=deploy_prod, to_shape=monitor)
    vsdx.Connect.create(page=page, from_shape=monitor, to_shape=end)

    return page


def build_sdlc_multipage(path: str) -> None:
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page1, page1_targets = build_planning_and_design_page(vis)
        rect_source = page1.find_shape_by_id("1")
        circle_source = page1.find_shape_by_id("7")

        page2, page2_targets = build_build_and_test_page(vis, rect_source, circle_source)
        page3 = build_release_and_operations_page(vis, rect_source, circle_source)

        page1_id, page2_id, page3_id = page1.page_id, page2.page_id, page3.page_id
        design_decision_id = page1_targets["design_decision_id"]
        qa_test_id = page2_targets["qa_test_id"]

        vis.save_vsdx(path)

    add_comments_to_vsdx(
        path,
        [
            {
                "page_id": page1_id,
                "shape_id": design_decision_id,
                "author": "Marcus PM",
                "date": "2026-07-21T09:00:00.000",
                "text": "Loop in the architecture review board before approving any design with a new external dependency.",
            },
            {
                "page_id": page2_id,
                "shape_id": qa_test_id,
                "author": "Priya QA Lead",
                "date": "2026-07-21T10:30:00.000",
                "text": "Run the full regression suite here, not just smoke tests - we've had escapes from smoke-only passes before.",
            },
            {
                "page_id": page3_id,
                "shape_id": None,
                "author": "Marcus PM",
                "date": "2026-07-21T11:15:00.000",
                "text": "Release page assumes a blue-green deploy; update this flow if we move to canary releases.",
            },
        ],
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "sdlc_multipage.vsdx")
    build_sdlc_multipage(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
