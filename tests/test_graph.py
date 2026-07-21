from visio2bpmn.classification import ClassifiedShape
from visio2bpmn.extraction import VisioComment, VisioConnector, VisioHyperlink, VisioPage, VisioShape
from visio2bpmn.graph import build_page_graph


def make_shape(id, bpmn_type, x, y, width, height, text="", comments=None, hyperlinks=None):
    shape = VisioShape(
        id=id,
        page_name="Page-1",
        master_name=None,
        shape_name=None,
        is_group=False,
        parent_id=None,
        text=text,
        x=x,
        y=y,
        width=width,
        height=height,
        comments=comments or [],
        hyperlinks=hyperlinks or [],
    )
    return ClassifiedShape(shape=shape, bpmn_type=bpmn_type, source="config")


def test_single_pool_two_lanes_cross_lane_flow_is_sequence_flow():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    pool = make_shape("pool1", "pool", x=5.5, y=4.25, width=10.0, height=8.0)
    lane1 = make_shape("lane1", "lane", x=5.5, y=2.0, width=10.0, height=4.0)
    lane2 = make_shape("lane2", "lane", x=5.5, y=6.0, width=10.0, height=4.0)
    start = make_shape("start", "startEvent", x=1.0, y=2.0, width=0.5, height=0.5)
    task1 = make_shape("task1", "task", x=3.0, y=2.0, width=1.5, height=1.0, text="Do A")
    gateway = make_shape("gw1", "exclusiveGateway", x=6.0, y=2.0, width=1.0, height=1.0, text="Check?")
    task2 = make_shape("task2", "task", x=3.0, y=6.0, width=1.5, height=1.0, text="Do B")
    end = make_shape("end", "endEvent", x=8.0, y=6.0, width=0.5, height=0.5)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="start", target_shape_id="task1", text=""),
        VisioConnector(connector_shape_id="c2", source_shape_id="task1", target_shape_id="gw1", text=""),
        VisioConnector(connector_shape_id="c3", source_shape_id="gw1", target_shape_id="task2", text="yes"),
        VisioConnector(connector_shape_id="c4", source_shape_id="task2", target_shape_id="end", text=""),
    ]

    classified = [pool, lane1, lane2, start, task1, gateway, task2, end]
    graph = build_page_graph(page, classified)

    assert len(graph.pools) == 1
    assert len(graph.pools[0].lanes) == 2

    node_by_original_id = {n.id.split("_")[-1]: n for n in graph.nodes}
    assert node_by_original_id["task1"].lane_id == node_by_original_id["start"].lane_id
    assert node_by_original_id["task2"].lane_id != node_by_original_id["task1"].lane_id
    assert node_by_original_id["task1"].pool_id == node_by_original_id["task2"].pool_id  # same pool

    kinds = {f.id: f.kind for f in graph.flows}
    assert all(kind == "sequenceFlow" for kind in kinds.values())  # same pool, no messageFlow
    assert not graph.warnings


def test_no_pool_or_lane_creates_single_default_pool():
    page = VisioPage(name="Flat Page", width=11.0, height=8.5)
    start = make_shape("start", "startEvent", x=1.0, y=1.0, width=0.5, height=0.5)
    task1 = make_shape("task1", "task", x=3.0, y=1.0, width=1.5, height=1.0)
    end = make_shape("end", "endEvent", x=5.0, y=1.0, width=0.5, height=0.5)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="start", target_shape_id="task1", text=""),
        VisioConnector(connector_shape_id="c2", source_shape_id="task1", target_shape_id="end", text=""),
    ]

    classified = [start, task1, end]
    graph = build_page_graph(page, classified)

    assert len(graph.pools) == 1
    assert graph.pools[0].lanes == []
    assert {n.pool_id for n in graph.nodes} == {graph.pools[0].id}


def test_ambiguous_terminator_event_resolved_by_flow_position():
    page = VisioPage(name="Flat Page", width=11.0, height=8.5)
    # generic "Terminator" shapes classify as the ambiguous "event" type -
    # graph construction must resolve start vs end from flow position
    start = make_shape("start", "event", x=1.0, y=1.0, width=0.5, height=0.5)
    task1 = make_shape("task1", "task", x=3.0, y=1.0, width=1.5, height=1.0)
    end = make_shape("end", "event", x=5.0, y=1.0, width=0.5, height=0.5)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="start", target_shape_id="task1", text=""),
        VisioConnector(connector_shape_id="c2", source_shape_id="task1", target_shape_id="end", text=""),
    ]

    classified = [start, task1, end]
    graph = build_page_graph(page, classified)

    node_by_original_id = {n.id.split("_")[-1]: n for n in graph.nodes}
    assert node_by_original_id["start"].bpmn_type == "startEvent"
    assert node_by_original_id["end"].bpmn_type == "endEvent"
    assert node_by_original_id["task1"].bpmn_type == "task"


def test_fully_disconnected_terminator_event_is_reported_as_orphan():
    # a resolved startEvent/endEvent with exactly one side connected is normal
    # and must not warn, but an "event" with *no* connections on either side
    # is a genuine orphan and must still be flagged, even though it shares
    # the ambiguous "event" bpmn_type used for unresolved Terminator shapes
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    disconnected = make_shape("floating", "event", x=5.0, y=5.0, width=0.5, height=0.5)

    graph = build_page_graph(page, [disconnected])

    assert any("Orphan node" in w and "floating" in w for w in graph.warnings)


def test_shape_and_page_comments_become_node_and_page_documentation():
    page = VisioPage(
        name="Page-1",
        width=11.0,
        height=8.5,
        comments=[VisioComment(author="Jane", date="2026-07-15T10:00:00.000", text="Page-level note")],
    )
    task1 = make_shape(
        "task1",
        "task",
        x=1.0,
        y=1.0,
        width=1.0,
        height=1.0,
        comments=[VisioComment(author="Jane", date="2026-07-15T10:01:00.000", text="Shape-level note")],
    )

    graph = build_page_graph(page, [task1])

    assert "Page-level note" in graph.documentation
    assert "Jane" in graph.documentation
    assert "Shape-level note" in graph.nodes[0].documentation


def test_shape_with_no_comments_has_empty_documentation():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    task1 = make_shape("task1", "task", x=1.0, y=1.0, width=1.0, height=1.0)

    graph = build_page_graph(page, [task1])

    assert graph.documentation == ""
    assert graph.nodes[0].documentation == ""


def test_same_document_hyperlink_becomes_node_documentation():
    """An Off-page Reference shape's Hyperlink (Address="", SubAddress=<page
    name>) should read as a "continues on page X" note in the node's
    documentation, combined with any comments already there."""
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    link = make_shape(
        "link1",
        "intermediateEvent",
        x=1.0,
        y=1.0,
        width=1.0,
        height=1.0,
        comments=[VisioComment(author="Jane", date="2026-07-15T10:00:00.000", text="Reviewed")],
        hyperlinks=[VisioHyperlink(address="", sub_address="Page-2", description="Continues elsewhere")],
    )

    graph = build_page_graph(page, [link])

    doc = graph.nodes[0].documentation
    assert "Reviewed" in doc
    assert "Hyperlink: continues on page 'Page-2'" in doc
    assert "Continues elsewhere" in doc


def test_external_hyperlink_becomes_node_documentation():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    link = make_shape(
        "link1",
        "task",
        x=1.0,
        y=1.0,
        width=1.0,
        height=1.0,
        hyperlinks=[VisioHyperlink(address="https://example.com/spec", sub_address="", description="")],
    )

    graph = build_page_graph(page, [link])

    assert graph.nodes[0].documentation == "Hyperlink: https://example.com/spec"


def test_dangling_connector_and_orphan_node_are_reported_as_warnings():
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    task1 = make_shape("task1", "task", x=1.0, y=1.0, width=1.0, height=1.0)
    orphan = make_shape("orphan", "task", x=5.0, y=5.0, width=1.0, height=1.0)

    page.connectors = [
        VisioConnector(connector_shape_id="c1", source_shape_id="task1", target_shape_id=None, text=""),
    ]

    classified = [task1, orphan]
    graph = build_page_graph(page, classified)

    assert any("Dangling connector" in w for w in graph.warnings)
    assert any("Orphan node" in w and "orphan" in w for w in graph.warnings)


def test_node_ids_are_prefixed_with_page_key_to_avoid_cross_page_collisions():
    page = VisioPage(name="Page 1", width=11.0, height=8.5)
    task1 = make_shape("1", "task", x=1.0, y=1.0, width=1.0, height=1.0)

    classified = [task1]
    graph = build_page_graph(page, classified)

    assert graph.nodes[0].id == "Page_1_1"
