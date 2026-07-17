"""Streamlit UI for the Visio -> BPMN converter.

Run with:
    .venv\\Scripts\\streamlit.exe run app.py
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from visio2bpmn.bpmn_xml import generate_bpmn_xml
from visio2bpmn.classification import ClassifiedShape, classify_document
from visio2bpmn.cli import DEFAULT_CONFIG
from visio2bpmn.diagram_svg import render_page_svg
from visio2bpmn.extraction import extract_document
from visio2bpmn.graph import build_page_graph
from visio2bpmn.validation import validate_bpmn_xml

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

SAMPLES = {
    "Simple task flow": ("fixtures/demo/simple_task_flow.vsdx", "Start -> Task -> End, the smallest possible diagram."),
    "Approval gateway": ("fixtures/demo/approval_gateway.vsdx", "A decision gateway with an approve/reject branch."),
    "Cross-functional (swimlanes)": (
        "fixtures/demo/cross_functional_process.vsdx",
        "Two swimlanes, detected by shape geometry rather than a named stencil.",
    ),
    "Generic shapes (unmapped demo)": (
        "fixtures/sample_basic.vsdx",
        "Plain shapes with no BPMN-relevant stencil name, to show how unmapped shapes are reported.",
    ),
    "Commented process": (
        "fixtures/demo/commented_process.vsdx",
        "Has real Visio review comments (shape-level and page-level) - carried through as BPMN documentation.",
    ),
}

st.set_page_config(page_title="Visio -> BPMN Converter", page_icon="\U0001F504", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] {
        background-color: rgba(66, 133, 244, 0.06);
        border: 1px solid rgba(66, 133, 244, 0.2);
        border-radius: 10px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("\U0001F504 Visio → BPMN Converter")
st.caption("Convert a Visio `.vsdx` diagram into Signavio-ready BPMN 2.0 XML.")

with st.sidebar:
    st.header("1. Choose input")
    source_mode = st.radio("Source", ["Sample file", "Upload your own"], label_visibility="collapsed")

    input_path: str | None = None
    uploaded_bytes: bytes | None = None
    display_name = ""

    if source_mode == "Sample file":
        sample_name = st.selectbox("Sample", list(SAMPLES.keys()))
        rel_path, description = SAMPLES[sample_name]
        input_path = os.path.join(REPO_ROOT, rel_path)
        display_name = sample_name
        st.caption(description)
    else:
        uploaded = st.file_uploader("Upload a .vsdx file", type=["vsdx"])
        if uploaded is not None:
            uploaded_bytes = uploaded.read()
            display_name = uploaded.name

    st.header("2. Options")
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    use_llm = st.checkbox(
        "Use LLM fallback for ambiguous shapes",
        value=False,
        disabled=not has_api_key,
        help="Classifies shapes the config/heuristics can't resolve, via the Anthropic API."
        + ("" if has_api_key else " Requires ANTHROPIC_API_KEY to be set."),
    )
    skip_validation = st.checkbox("Skip XSD schema validation", value=False)

    convert_clicked = st.button("Convert to BPMN", type="primary", use_container_width=True)

if convert_clicked:
    if uploaded_bytes is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".vsdx")
        tmp.write(uploaded_bytes)
        tmp.close()
        vsdx_path = tmp.name
    elif input_path is not None:
        vsdx_path = input_path
    else:
        st.warning("Please select a sample or upload a .vsdx file first.")
        st.stop()

    with st.spinner("Running extraction → classification → graph → BPMN generation..."):
        document = extract_document(vsdx_path)
        classified = classify_document(document, DEFAULT_CONFIG, use_llm_fallback=use_llm)

        classified_by_page: dict[str, list[ClassifiedShape]] = {}
        for c in classified:
            classified_by_page.setdefault(c.shape.page_name, []).append(c)

        warnings: list[str] = []
        page_graphs = []
        for page in document.pages:
            page_classified = classified_by_page.get(page.name, [])
            for c in page_classified:
                if c.bpmn_type is None:
                    warnings.append(
                        f"Unmapped shape on page {page.name!r}: text={c.shape.text!r} "
                        f"master={c.shape.master_name!r}"
                    )
            page_graph = build_page_graph(page, page_classified)
            warnings.extend(page_graph.warnings)
            page_graphs.append(page_graph)

        xml_bytes = generate_bpmn_xml(page_graphs)

        if not skip_validation:
            for error in validate_bpmn_xml(xml_bytes):
                warnings.append(f"Schema validation error: {error}")

    output_name = os.path.splitext(os.path.basename(display_name or "output"))[0] + ".bpmn"
    st.session_state["result"] = {
        "display_name": display_name,
        "page_graphs": page_graphs,
        "warnings": warnings,
        "xml_bytes": xml_bytes,
        "output_name": output_name,
    }

result = st.session_state.get("result")

if result is None:
    st.info("Pick a sample or upload a `.vsdx` file in the sidebar, then click **Convert to BPMN**.")
else:
    page_graphs = result["page_graphs"]
    warnings = result["warnings"]
    xml_bytes = result["xml_bytes"]

    st.success(f"Converted **{result['display_name']}**")

    total_pools = sum(len(g.pools) for g in page_graphs)
    total_lanes = sum(len(pool.lanes) for g in page_graphs for pool in g.pools)
    total_nodes = sum(len(g.nodes) for g in page_graphs)
    total_flows = sum(len(g.flows) for g in page_graphs)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pages", len(page_graphs))
    c2.metric("Pools", total_pools)
    c3.metric("Lanes", total_lanes)
    c4.metric("Nodes", total_nodes)
    c5.metric("Flows", total_flows)

    st.download_button(
        "⬇️ Download .bpmn file",
        data=xml_bytes,
        file_name=result["output_name"],
        mime="application/xml",
        type="primary",
        use_container_width=True,
    )

    tab_preview, tab_xml, tab_warnings = st.tabs(
        ["\U0001F4C4 Diagram preview", "\U0001F4DD BPMN XML", f"⚠️ Warnings ({len(warnings)})"]
    )

    with tab_preview:
        for page_graph in page_graphs:
            st.subheader(page_graph.page_name)
            svg = render_page_svg(page_graph)
            st.components.v1.html(svg, height=int(page_graph.height * 100) + 100, scrolling=True)

    with tab_xml:
        st.code(xml_bytes.decode("utf-8"), language="xml")

    with tab_warnings:
        if warnings:
            for warning in warnings:
                st.warning(warning)
        else:
            st.success("No warnings - clean conversion!")
