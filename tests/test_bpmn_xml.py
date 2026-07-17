from lxml import etree

from visio2bpmn.bpmn_xml import BPMN_NS, BPMNDI_NS, generate_bpmn_xml
from visio2bpmn.classification import ClassifiedShape
from visio2bpmn.extraction import VisioConnector, VisioPage, VisioShape
from visio2bpmn.graph import build_page_graph


def make_shape(id, bpmn_type, x, y, width, height, text=""):
    shape = VisioShape(
        id=id, page_name="Page-1", master_name=None, shape_name=None,
        is_group=False, parent_id=None, text=text, x=x, y=y, width=width, height=height,
    )
    return ClassifiedShape(shape=shape, bpmn_type=bpmn_type, source="config")


def _single_pool_page_graph():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    pool = make_shape("pool1", "pool", x=5.5, y=4.25, width=10.0, height=8.0)
    lane1 = make_shape("lane1", "lane", x=5.5, y=2.0, width=10.0, height=4.0)
    lane2 = make_shape("lane2", "lane", x=5.5, y=6.0, width=10.0, height=4.0)
    start = make_shape("start", "startEvent", x=1.0, y=2.0, width=0.5, height=0.5)
    task1 = make_shape("task1", "task", x=3.0, y=2.0, width=1.5, height=1.0, text="Do A")
    end = make_shape("end", "endEvent", x=8.0, y=6.0, width=0.5, height=0.5)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="start", target_shape_id="task1", text=""),
        VisioConnector(connector_shape_id="c2", source_shape_id="task1", target_shape_id="end", text="done"),
    ]
    classified = [pool, lane1, lane2, start, task1, end]
    return build_page_graph(page, classified)


def test_single_pool_generates_bare_process_no_collaboration():
    graph = _single_pool_page_graph()
    xml_bytes = generate_bpmn_xml([graph])
    root = etree.fromstring(xml_bytes)

    assert root.tag == f"{{{BPMN_NS}}}definitions"
    assert root.find(f"{{{BPMN_NS}}}collaboration") is None
    processes = root.findall(f"{{{BPMN_NS}}}process")
    assert len(processes) == 1

    tasks = processes[0].findall(f"{{{BPMN_NS}}}task")
    assert len(tasks) == 1
    assert tasks[0].get("name") == "Do A"

    seq_flows = processes[0].findall(f"{{{BPMN_NS}}}sequenceFlow")
    assert len(seq_flows) == 2

    lanes = processes[0].findall(f".//{{{BPMN_NS}}}lane")
    assert len(lanes) == 2


def test_diagram_shapes_and_edges_are_present_with_flipped_y():
    graph = _single_pool_page_graph()
    xml_bytes = generate_bpmn_xml([graph])
    root = etree.fromstring(xml_bytes)

    diagram = root.find(f"{{{BPMNDI_NS}}}BPMNDiagram")
    assert diagram is not None
    plane = diagram.find(f"{{{BPMNDI_NS}}}BPMNPlane")
    shapes = plane.findall(f"{{{BPMNDI_NS}}}BPMNShape")
    edges = plane.findall(f"{{{BPMNDI_NS}}}BPMNEdge")

    # 2 lanes + 3 nodes (start, task1, end) = 5 shapes; no participant shape (single pool)
    assert len(shapes) == 5
    assert len(edges) == 2

    # start event is at Visio y=2.0 on an 8.5-tall page -> flipped y = (8.5-2.0)*100 = 650
    start_shape = next(s for s in shapes if "start" in s.get("bpmnElement"))
    bounds = start_shape.find(f"{{http://www.omg.org/spec/DD/20100524/DC}}Bounds")
    assert float(bounds.get("y")) == 650.0 - 25.0  # top-left y = center_y - height/2*scale


def test_multi_pool_page_generates_collaboration_and_message_flow():
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
    root = etree.fromstring(xml_bytes)

    collaboration = root.find(f"{{{BPMN_NS}}}collaboration")
    assert collaboration is not None
    participants = collaboration.findall(f"{{{BPMN_NS}}}participant")
    assert len(participants) == 2
    message_flows = collaboration.findall(f"{{{BPMN_NS}}}messageFlow")
    assert len(message_flows) == 1

    processes = root.findall(f"{{{BPMN_NS}}}process")
    assert len(processes) == 2
    # message flow must not appear as a sequenceFlow inside either process
    for process in processes:
        assert process.findall(f"{{{BPMN_NS}}}sequenceFlow") == []
