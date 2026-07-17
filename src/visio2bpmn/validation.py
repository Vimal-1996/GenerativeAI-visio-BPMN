"""Phase 5 - XSD validation against the official OMG BPMN 2.0 schema."""
from __future__ import annotations

import os

import xmlschema

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "schemas")
_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "BPMN20.xsd")

_schema: xmlschema.XMLSchema | None = None


def _get_schema() -> xmlschema.XMLSchema:
    global _schema
    if _schema is None:
        _schema = xmlschema.XMLSchema(_SCHEMA_PATH)
    return _schema


def validate_bpmn_xml(xml_bytes: bytes) -> list[str]:
    """Validate BPMN XML bytes against the official BPMN20.xsd.

    Returns a list of human-readable error strings; an empty list means
    the document is schema-valid.
    """
    schema = _get_schema()
    errors = []
    for error in schema.iter_errors(xml_bytes):
        errors.append(str(error.reason or error))
    return errors
