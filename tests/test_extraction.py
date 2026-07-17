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
