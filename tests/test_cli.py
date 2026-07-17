"""End-to-end integration test: real .vsdx file -> CLI convert() -> BPMN XML on disk."""
import os

from lxml import etree

from visio2bpmn.bpmn_xml import BPMN_NS
from visio2bpmn.cli import convert

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_basic.vsdx")


def test_convert_runs_end_to_end_on_real_vsdx_file(tmp_path):
    output_path = tmp_path / "sample_basic.bpmn"

    warnings = convert(
        input_path=FIXTURE_PATH,
        output_path=str(output_path),
        use_llm_fallback=False,
    )

    assert output_path.exists()
    root = etree.fromstring(output_path.read_bytes())
    assert root.tag == f"{{{BPMN_NS}}}definitions"

    # this fixture's shapes have no BPMN-relevant master names and the LLM
    # fallback is disabled, so every shape should come back unresolved
    assert any("Unmapped shape" in w and "RECTANGLE" in w for w in warnings)
    assert any("Unmapped shape" in w and "CIRCLE" in w for w in warnings)
