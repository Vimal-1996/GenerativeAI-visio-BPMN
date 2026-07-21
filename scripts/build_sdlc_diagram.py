"""Builds a complex, multi-lane Software Development Life Cycle (SDLC) demo
diagram at fixtures/demo/sdlc_swimlanes.vsdx.

Same approach as build_sample_fixtures.py: there's no Visio installation in
this environment, so the diagram is built programmatically with the `vsdx`
library's shape-copy and Connect.create() APIs, starting from the small
template it ships internally (vsdx/media/media.vsdx). Reuses the comment
injection helper from build_sample_fixtures.py since vsdx itself has no
support for reading or writing Visio's Comments feature.

Five swimlanes (Product Owner, Development, QA, DevOps/Release, Operations),
16 process/decision/terminator shapes, 20 connectors including two rework
loops (design revision, bug-fix cycle) that cross lane boundaries - built to
exercise visio2bpmn's lane-containment geometry, decision-gateway handling,
and Comments passthrough all in one file.

Re-run with: .venv/Scripts/python.exe scripts/build_sdlc_diagram.py
"""
from __future__ import annotations

import os

import vsdx

from build_sample_fixtures import (
    MEDIA_VSDX,
    _place,
    _remove_connects_referencing,
    add_comments_to_vsdx,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "fixtures", "demo")

PAGE_WIDTH = 35.0
PAGE_HEIGHT = 18.5

LANE_WIDTH = 34.0
LANE_HEIGHT = 3.2
LANE_X = PAGE_WIDTH / 2  # 17.5, lane center

LANE_Y = {
    "po": 16.5,      # Product Owner / Business Analyst
    "dev": 13.0,      # Development Team
    "qa": 9.5,        # QA / Testing
    "devops": 6.0,    # DevOps / Release Management
    "ops": 2.5,       # Operations / Support
}


def build_sdlc_swimlanes(path: str) -> None:
    with vsdx.VisioFile(MEDIA_VSDX) as vis:
        page = vis.pages[0]
        page.width = PAGE_WIDTH
        page.height = PAGE_HEIGHT

        rect_template = page.find_shape_by_id("1")
        circle_template = page.find_shape_by_id("7")
        for stale_id in ("2", "3", "5", "8"):
            page.find_shape_by_id(stale_id).remove()
        _remove_connects_referencing(page, {"2", "3", "5", "8"})

        # --- lanes (wide, shallow, page-spanning rectangles -> geometric
        # lane heuristic in classification.py, no stencil name needed) ---
        lane_po = rect_template
        lane_dev = rect_template.copy(page)
        lane_qa = rect_template.copy(page)
        lane_devops = rect_template.copy(page)
        lane_ops = rect_template.copy(page)

        _place(lane_po, x=LANE_X, y=LANE_Y["po"], width=LANE_WIDTH, height=LANE_HEIGHT, text="Product Owner", master_name="")
        _place(lane_dev, x=LANE_X, y=LANE_Y["dev"], width=LANE_WIDTH, height=LANE_HEIGHT, text="Development", master_name="")
        _place(lane_qa, x=LANE_X, y=LANE_Y["qa"], width=LANE_WIDTH, height=LANE_HEIGHT, text="QA / Testing", master_name="")
        _place(lane_devops, x=LANE_X, y=LANE_Y["devops"], width=LANE_WIDTH, height=LANE_HEIGHT, text="DevOps / Release", master_name="")
        _place(lane_ops, x=LANE_X, y=LANE_Y["ops"], width=LANE_WIDTH, height=LANE_HEIGHT, text="Operations / Support", master_name="")

        # --- process nodes ---
        start = circle_template
        end = circle_template.copy(page)

        req = rect_template.copy(page)
        stories = rect_template.copy(page)
        design = rect_template.copy(page)
        design_decision = rect_template.copy(page)
        revise_design = rect_template.copy(page)
        develop = rect_template.copy(page)
        code_review = rect_template.copy(page)
        unit_test = rect_template.copy(page)
        deploy_qa = rect_template.copy(page)
        qa_test = rect_template.copy(page)
        bugs_decision = rect_template.copy(page)
        fix_bugs = rect_template.copy(page)
        uat = rect_template.copy(page)
        uat_decision = rect_template.copy(page)
        deploy_prod = rect_template.copy(page)
        monitor = rect_template.copy(page)

        T = "Terminator"
        P = "Process"
        D = "Decision"

        _place(start, x=1.5, y=LANE_Y["po"], width=1.0, height=0.7, text="Start", master_name=T)
        _place(req, x=4.0, y=LANE_Y["po"], width=2.2, height=1.1, text="Gather Requirements", master_name=P)
        _place(stories, x=6.5, y=LANE_Y["po"], width=2.2, height=1.1, text="Write User Stories", master_name=P)
        _place(design, x=6.5, y=LANE_Y["dev"], width=2.2, height=1.1, text="Design Solution", master_name=P)
        _place(design_decision, x=9.2, y=LANE_Y["po"], width=1.8, height=1.4, text="Design Approved?", master_name=D)
        _place(revise_design, x=9.2, y=LANE_Y["dev"], width=2.2, height=1.1, text="Revise Design", master_name=P)
        _place(develop, x=11.9, y=LANE_Y["dev"], width=2.2, height=1.1, text="Develop Code", master_name=P)
        _place(code_review, x=14.6, y=LANE_Y["dev"], width=2.2, height=1.1, text="Code Review", master_name=P)
        _place(unit_test, x=17.3, y=LANE_Y["dev"], width=2.2, height=1.1, text="Unit Testing", master_name=P)
        _place(deploy_qa, x=17.3, y=LANE_Y["devops"], width=2.2, height=1.1, text="Deploy to QA Environment", master_name=P)
        _place(qa_test, x=20.0, y=LANE_Y["qa"], width=2.2, height=1.1, text="QA Testing", master_name=P)
        _place(bugs_decision, x=22.7, y=LANE_Y["qa"], width=1.8, height=1.4, text="Bugs Found?", master_name=D)
        _place(fix_bugs, x=22.7, y=LANE_Y["dev"], width=2.2, height=1.1, text="Fix Bugs", master_name=P)
        _place(uat, x=25.4, y=LANE_Y["po"], width=2.2, height=1.1, text="User Acceptance Testing", master_name=P)
        _place(uat_decision, x=28.1, y=LANE_Y["po"], width=1.8, height=1.4, text="UAT Approved?", master_name=D)
        _place(deploy_prod, x=28.1, y=LANE_Y["devops"], width=2.2, height=1.1, text="Deploy to Production", master_name=P)
        _place(monitor, x=30.8, y=LANE_Y["ops"], width=2.2, height=1.1, text="Monitor & Support", master_name=P)
        _place(end, x=33.0, y=LANE_Y["ops"], width=1.0, height=0.7, text="End", master_name=T)

        # --- flow, including two rework loops that cross lanes ---
        vsdx.Connect.create(page=page, from_shape=start, to_shape=req)
        vsdx.Connect.create(page=page, from_shape=req, to_shape=stories)
        vsdx.Connect.create(page=page, from_shape=stories, to_shape=design)
        vsdx.Connect.create(page=page, from_shape=design, to_shape=design_decision)

        c = vsdx.Connect.create(page=page, from_shape=design_decision, to_shape=revise_design)
        c.text = "No"
        vsdx.Connect.create(page=page, from_shape=revise_design, to_shape=design)  # loop back

        c = vsdx.Connect.create(page=page, from_shape=design_decision, to_shape=develop)
        c.text = "Yes"

        vsdx.Connect.create(page=page, from_shape=develop, to_shape=code_review)
        vsdx.Connect.create(page=page, from_shape=code_review, to_shape=unit_test)
        vsdx.Connect.create(page=page, from_shape=unit_test, to_shape=deploy_qa)
        vsdx.Connect.create(page=page, from_shape=deploy_qa, to_shape=qa_test)
        vsdx.Connect.create(page=page, from_shape=qa_test, to_shape=bugs_decision)

        c = vsdx.Connect.create(page=page, from_shape=bugs_decision, to_shape=fix_bugs)
        c.text = "Yes"
        vsdx.Connect.create(page=page, from_shape=fix_bugs, to_shape=code_review)  # loop back

        c = vsdx.Connect.create(page=page, from_shape=bugs_decision, to_shape=uat)
        c.text = "No"

        vsdx.Connect.create(page=page, from_shape=uat, to_shape=uat_decision)

        c = vsdx.Connect.create(page=page, from_shape=uat_decision, to_shape=fix_bugs)
        c.text = "No"  # second rework loop, re-enters the same fix cycle

        c = vsdx.Connect.create(page=page, from_shape=uat_decision, to_shape=deploy_prod)
        c.text = "Yes"

        vsdx.Connect.create(page=page, from_shape=deploy_prod, to_shape=monitor)
        vsdx.Connect.create(page=page, from_shape=monitor, to_shape=end)

        page_id = page.page_id
        qa_test_id = qa_test.ID
        uat_decision_id = uat_decision.ID

        vis.save_vsdx(path)

    add_comments_to_vsdx(
        path,
        [
            {
                "page_id": page_id,
                "shape_id": qa_test_id,
                "author": "Priya QA Lead",
                "date": "2026-07-20T09:15:00.000",
                "text": "Automate the regression suite before the next release cycle - manual pass took 3 days.",
            },
            {
                "page_id": page_id,
                "shape_id": uat_decision_id,
                "author": "Marcus PM",
                "date": "2026-07-20T14:05:00.000",
                "text": "Get explicit written sign-off from the business stakeholder here before proceeding to prod deploy.",
            },
            {
                "page_id": page_id,
                "shape_id": None,
                "author": "Marcus PM",
                "date": "2026-07-20T14:10:00.000",
                "text": "This model assumes 2-week sprints - adjust the deploy cadence if the team's cycle time changes.",
            },
        ],
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "sdlc_swimlanes.vsdx")
    build_sdlc_swimlanes(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
