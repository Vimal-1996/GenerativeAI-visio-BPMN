import os

from visio2bpmn.classification import classify_shape, load_mapping_config
from visio2bpmn.extraction import VisioPage, VisioShape

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "shape_mapping.yaml")


def make_shape(**kwargs) -> VisioShape:
    defaults = dict(
        id="1",
        page_name="Page-1",
        master_name=None,
        shape_name=None,
        is_group=False,
        parent_id=None,
        text="",
        x=0.0,
        y=0.0,
        width=1.0,
        height=1.0,
    )
    defaults.update(kwargs)
    return VisioShape(**defaults)


def test_config_lookup_matches_bpmn_stencil_task():
    mapping = load_mapping_config(CONFIG_PATH)
    shape = make_shape(master_name="Task", text="Approve invoice")

    result = classify_shape(shape, VisioPage(name="Page-1", width=11.0, height=8.5), mapping)

    assert result.bpmn_type == "task"
    assert result.source == "config"


def test_config_lookup_matches_basic_flowchart_decision():
    mapping = load_mapping_config(CONFIG_PATH)
    shape = make_shape(master_name="Decision", text="Approved?")

    result = classify_shape(shape, VisioPage(name="Page-1", width=11.0, height=8.5), mapping)

    assert result.bpmn_type == "exclusiveGateway"
    assert result.source == "config"


def test_geometric_heuristic_detects_lane():
    mapping = load_mapping_config(CONFIG_PATH)
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    # spans full page width and is much wider than tall -> lane candidate
    shape = make_shape(master_name=None, shape_name=None, width=10.5, height=2.0)

    result = classify_shape(shape, page, mapping)

    assert result.bpmn_type == "lane"
    assert result.source == "heuristic"


def test_unmatched_shape_is_unresolved():
    mapping = load_mapping_config(CONFIG_PATH)
    page = VisioPage(name="Page-1", width=11.0, height=8.5)
    shape = make_shape(master_name="Some Unknown Custom Stencil Shape", width=1.0, height=1.0)

    result = classify_shape(shape, page, mapping)

    assert result.bpmn_type is None
    assert result.source == "unresolved"
