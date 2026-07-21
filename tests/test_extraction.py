"""Integration test for Phase 1 against a real .vsdx file (not a mock).

fixtures/sample_basic.vsdx is the small template file bundled with the
`vsdx` library itself (vsdx/media/media.vsdx) - it has a real page with a
rectangle, a circle, a line, and two connectors (straight + curved) both
linking the rectangle to a second shape. It's a genuine Visio zip/XML
document, so this test exercises the actual `vsdx` parsing path end to
end, unlike the classification/graph/bpmn_xml tests which build
`VisioShape`/`ClassifiedShape` objects by hand.
"""
import os

from visio2bpmn.extraction import extract_document

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_basic.vsdx")
COMMENTED_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo", "commented_process.vsdx")
MULTIPAGE_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo", "sdlc_multipage.vsdx")


def test_extracts_one_page_with_expected_shapes_and_connectors():
    document = extract_document(FIXTURE_PATH)

    assert len(document.pages) == 1
    page = document.pages[0]
    assert page.name == "Page-1"
    assert page.width > 0 and page.height > 0

    texts = {s.text.strip() for s in page.shapes}
    assert texts == {"RECTANGLE", "CONNECTED_SHAPE", "CIRCLE", "LINE"}

    # the two connector shapes (straight + curved) are excluded from the
    # node list and captured as connectors instead
    shape_ids = {s.id for s in page.shapes}
    assert "3" not in shape_ids
    assert "5" not in shape_ids

    assert len(page.connectors) == 2
    for connector in page.connectors:
        assert connector.source_shape_id == "1"  # RECTANGLE
        assert connector.target_shape_id == "2"  # CONNECTED_SHAPE


def test_shape_geometry_is_populated():
    document = extract_document(FIXTURE_PATH)
    page = document.pages[0]
    rectangle = next(s for s in page.shapes if s.text.strip() == "RECTANGLE")

    assert rectangle.width > 0
    assert rectangle.height > 0
    assert rectangle.x > 0
    assert rectangle.y > 0


def test_file_with_no_comments_part_returns_empty_comments():
    document = extract_document(FIXTURE_PATH)
    page = document.pages[0]

    assert page.comments == []
    assert all(shape.comments == [] for shape in page.shapes)


def test_shape_and_page_level_comments_are_extracted_from_real_comments_part():
    """commented_process.vsdx has a real Visio Comments XML part (MS-VSDX
    2.2.9), injected by scripts/build_sample_fixtures.py since the vsdx
    library has no support for authoring or reading it - this exercises
    our own raw zip/XML parsing end to end."""
    document = extract_document(COMMENTED_FIXTURE_PATH)
    page = document.pages[0]

    assert page.page_id is not None

    assert len(page.comments) == 1
    assert page.comments[0].author == "Jane Reviewer"
    assert "legal review" in page.comments[0].text

    task = next(s for s in page.shapes if s.text.strip() == "Review Application")
    assert len(task.comments) == 1
    assert task.comments[0].author == "Jane Reviewer"
    assert "manager sign-off" in task.comments[0].text
    assert task.comments[0].date == "2026-07-15T10:30:00.000"

    # shapes with no comment attached still default to an empty list
    start = next(s for s in page.shapes if s.text.strip() == "Start")
    assert start.comments == []


def test_multipage_file_extracts_all_pages_with_page_scoped_comments():
    """sdlc_multipage.vsdx (scripts/build_sdlc_multipage_diagram.py) has 3
    real pages, each with its own PageID and its own shapes/comments -
    this exercises PageID-based comment matching across multiple pages,
    not just within a single page."""
    document = extract_document(MULTIPAGE_FIXTURE_PATH)

    assert len(document.pages) == 3
    assert [p.name for p in document.pages] == ["Planning & Design", "Build & Test", "Release & Operations"]

    page_ids = [p.page_id for p in document.pages]
    assert len(set(page_ids)) == 3  # every page got a distinct PageID

    planning, build_test, release_ops = document.pages

    design_decision = next(s for s in planning.shapes if s.text.strip() == "Design Approved?")
    assert len(design_decision.comments) == 1
    assert design_decision.comments[0].author == "Marcus PM"

    qa_test = next(s for s in build_test.shapes if s.text.strip() == "QA Testing")
    assert len(qa_test.comments) == 1
    assert qa_test.comments[0].author == "Priya QA Lead"

    # a comment meant for page 1 must not bleed into another page's shapes
    assert all(s.comments == [] for s in build_test.shapes if s.text.strip() != "QA Testing")

    # page-level comment (no ShapeID) attaches to the correct page only
    assert release_ops.comments != []
    assert planning.comments == []
    assert build_test.comments == []


def test_multipage_file_shape_hyperlinks_link_pages_together():
    """Planning & Design and Build & Test each carry an Off-page Reference
    shape with a real Visio Hyperlink (Address="", SubAddress=<next page's
    name>) pointing at the following page - this exercises reading the
    Hyperlink section directly off Shape.xml, since `vsdx` parses that
    section into the shape's own XML but doesn't model it itself."""
    document = extract_document(MULTIPAGE_FIXTURE_PATH)
    planning, build_test, release_ops = document.pages

    to_build_test = next(s for s in planning.shapes if s.text.strip() == "Continue to Build & Test")
    assert len(to_build_test.hyperlinks) == 1
    link = to_build_test.hyperlinks[0]
    assert link.address == ""
    assert link.sub_address == "Build & Test"
    assert "Build & Test phase" in link.description

    to_release_ops = next(s for s in build_test.shapes if s.text.strip() == "Continue to Release & Operations")
    assert len(to_release_ops.hyperlinks) == 1
    assert to_release_ops.hyperlinks[0].sub_address == "Release & Operations"

    # shapes with no hyperlink still default to an empty list
    start = next(s for s in planning.shapes if s.text.strip() == "Start")
    assert start.hyperlinks == []
    assert all(s.hyperlinks == [] for s in release_ops.shapes)
