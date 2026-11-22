from pathlib import Path
from runpy import run_path
from unittest.mock import MagicMock

import pytest
from lxml import etree

from finamt.tax import eric_wrapper

SCRIPT = Path(__file__).parents[2] / "scripts" / "validate_est_reference.py"


@pytest.fixture
def reference(tmp_path, monkeypatch):
    schema = tmp_path / "reference.xsd"
    schema.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:element name="reference" type="xs:integer"/>'
        "</xs:schema>",
        encoding="utf-8",
    )
    xml = tmp_path / "reference.xml"
    xml.write_bytes(b"<reference>42</reference>")
    session = MagicMock()
    buffer = MagicMock()
    monkeypatch.setattr(eric_wrapper, "EricSession", session)
    monkeypatch.setattr(eric_wrapper, "EricBuffer", buffer)
    validate = run_path(str(SCRIPT))["validate_reference"]
    return validate, xml, schema, session, buffer


def test_native_reference_check_uses_only_the_validation_flag(reference, tmp_path):
    validate, xml, schema, session_factory, buffer_factory = reference
    session = session_factory.return_value.__enter__.return_value
    buffer = buffer_factory.return_value.__enter__.return_value
    session.bearbeite_vorgang.return_value = (0, None)
    validate(xml, schema, tmp_path, "synthetic_test_version")
    session_factory.assert_called_once_with(str(tmp_path))
    session.bearbeite_vorgang.assert_called_once_with(
        xml_bytes=xml.read_bytes(),
        datenart_version="synthetic_test_version",
        flags=eric_wrapper.ERIC_VALIDIERE,
        response_buffer=buffer.handle.return_value,
        server_buffer=buffer.handle.return_value,
    )


def test_reference_outside_the_schema_never_reaches_native_eric(reference, tmp_path):
    validate, xml, schema, session_factory, _ = reference
    xml.write_bytes(b"<wrong-field>42</wrong-field>")
    with pytest.raises(etree.DocumentInvalid):
        validate(xml, schema, tmp_path, "synthetic_test_version")
    session_factory.assert_not_called()


def test_rejected_reference_reports_native_error_and_detail(reference, tmp_path):
    validate, xml, schema, session_factory, buffer_factory = reference
    session = session_factory.return_value.__enter__.return_value
    session.bearbeite_vorgang.return_value = (42, None)
    session.get_error_text.return_value = "Prüfung fehlgeschlagen"
    buffer_factory.return_value.__enter__.return_value.content.return_value = b"invalid field"
    with pytest.raises(eric_wrapper.EricError, match="invalid field") as error:
        validate(xml, schema, tmp_path, "synthetic_test_version")
    assert error.value.code == 42
