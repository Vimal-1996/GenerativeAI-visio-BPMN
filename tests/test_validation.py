import os

from lxml import etree

from visio2bpmn.bpmn_xml import generate_bpmn_xml
from visio2bpmn.classification import ClassifiedShape
from visio2bpmn.cli import convert
from visio2bpmn.extraction import VisioConnector, VisioPage, VisioShape
from visio2bpmn.graph import build_page_graph
from visio2bpmn.validation import validate_bpmn_xml

COMMENTED_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo", "commented_process.vsdx")
MULTIPAGE_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo", "sdlc_multipage.vsdx")


def make_shape(id, bpmn_type, x, y, width, height, text=""):
    shape = VisioShape(
        id=id, page_name="Page-1", master_name=None, shape_name=None,
        is_group=False, parent_id=None, text=text, x=x, y=y, width=width, height=height,
    )
    return ClassifiedShape(shape=shape, bpmn_type=bpmn_type, source="config")


def test_generated_single_pool_document_is_schema_valid():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    pool = make_shape("pool1", "pool", x=5.5, y=4.25, width=10.0, height=8.0)
    lane1 = make_shape("lane1", "lane", x=5.5, y=2.0, width=10.0, height=4.0)
    lane2 = make_shape("lane2", "lane", x=5.5, y=6.0, width=10.0, height=4.0)
    start = make_shape("start", "startEvent", x=1.0, y=2.0, width=0.5, height=0.5)
    task1 = make_shape("task1", "task", x=3.0, y=2.0, width=1.5, height=1.0, text="Do A")
    gw = make_shape("gw1", "exclusiveGateway", x=6.0, y=2.0, width=1.0, height=1.0, text="Check?")
    task2 = make_shape("task2", "task", x=3.0, y=6.0, width=1.5, height=1.0, text="Do B")
    end = make_shape("end", "endEvent", x=8.0, y=6.0, width=0.5, height=0.5)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="start", target_shape_id="task1", text=""),
        VisioConnector(connector_shape_id="c2", source_shape_id="task1", target_shape_id="gw1", text=""),
        VisioConnector(connector_shape_id="c3", source_shape_id="gw1", target_shape_id="task2", text="yes"),
        VisioConnector(connector_shape_id="c4", source_shape_id="task2", target_shape_id="end", text=""),
    ]
    classified = [pool, lane1, lane2, start, task1, gw, task2, end]
    graph = build_page_graph(page, classified)

    xml_bytes = generate_bpmn_xml([graph])
    errors = validate_bpmn_xml(xml_bytes)
    assert errors == [], f"Schema validation errors: {errors}"


def test_real_multipage_file_is_schema_valid_with_unique_ids_across_pages(tmp_path):
    """sdlc_multipage.vsdx has 3 pages with different pool/lane counts - a
    real regression test for two things that were previously implemented
    but never exercised by any test: (1) per-page id-prefixing in
    graph.py actually avoids id collisions once every page's output is
    merged into one <definitions>, and (2) build_definitions() places all
    rootElements before any bpmndi:BPMNDiagram (interleaving them, as it
    did before this fixture caught the bug, fails the real BPMN XSD)."""
    output_path = tmp_path / "sdlc_multipage.bpmn"
    warnings = convert(input_path=MULTIPAGE_FIXTURE_PATH, output_path=str(output_path), use_llm_fallback=False)

    assert warnings == []
    xml_bytes = output_path.read_bytes()
    errors = validate_bpmn_xml(xml_bytes)
    assert errors == [], f"Schema validation errors: {errors}"

    root = etree.fromstring(xml_bytes)
    ids = [el.get("id") for el in root.iter() if el.get("id") is not None]
    assert len(ids) == len(set(ids)), "duplicate id attributes across pages in the merged document"


def test_real_file_with_comments_produces_schema_valid_documentation(tmp_path):
    output_path = tmp_path / "commented_process.bpmn"
    warnings = convert(input_path=COMMENTED_FIXTURE_PATH, output_path=str(output_path), use_llm_fallback=False)

    assert warnings == []
    xml_bytes = output_path.read_bytes()
    assert b"<documentation>" in xml_bytes
    errors = validate_bpmn_xml(xml_bytes)
    assert errors == [], f"Schema validation errors: {errors}"


def test_generated_multi_pool_document_is_schema_valid():
    page = VisioPage(name="Page-2", width=11.0, height=8.5)
    pool_a = make_shape("poolA", "pool", x=2.75, y=4.25, width=5.0, height=8.0)
    pool_b = make_shape("poolB", "pool", x=8.25, y=4.25, width=5.0, height=8.0)
    task_a = make_shape("taskA", "task", x=2.75, y=4.25, width=1.5, height=1.0, text="Send request")
    task_b = make_shape("taskB", "task", x=8.25, y=4.25, width=1.5, height=1.0, text="Receive request")

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="taskA", target_shape_id="taskB", text="request"),
    ]
    classified = [pool_a, pool_b, task_a, task_b]
    graph = build_page_graph(page, classified)

    xml_bytes = generate_bpmn_xml([graph])
    errors = validate_bpmn_xml(xml_bytes)
    assert errors == [], f"Schema validation errors: {errors}"
