"""Check an official synthetic ESt reference XML against its XSD and local ERiC."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lxml import etree

from finamt.tax.eric_wrapper import ERIC_VALIDIERE, EricBuffer, EricError, EricSession


def validate_reference(xml_path: Path, schema_path: Path, eric_home: Path, version: str) -> None:
    xml = xml_path.read_bytes()
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    root = etree.fromstring(xml, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError("Die Referenzdatei muss XML ohne DTD enthalten.")
    schema = etree.XMLSchema(etree.parse(str(schema_path), parser))
    schema.assertValid(root)

    with EricSession(str(eric_home)) as session:
        with EricBuffer(session) as response, EricBuffer(session) as server:
            code, _ = session.bearbeite_vorgang(
                xml_bytes=xml,
                datenart_version=version,
                flags=ERIC_VALIDIERE,
                response_buffer=response.handle(),
                server_buffer=server.handle(),
            )
            if code:
                details = response.content().decode("utf-8", errors="replace").strip()
                text = session.get_error_text(code)
                raise EricError(code, "\n".join(filter(None, (text, details))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path, help="Synthetic reference XML from the ELSTER SDK")
    parser.add_argument("--schema", required=True, type=Path, help="Matching local XSD")
    parser.add_argument(
        "--eric-home", required=True, type=Path, help="Directory with the ERiC library"
    )
    parser.add_argument("--datenart-version", required=True, help="Version specified by ELSTER")
    args = parser.parse_args()
    version = args.datenart_version.strip()
    if not version:
        parser.error("--datenart-version muss die amtliche Datenartversion enthalten.")
    try:
        validate_reference(args.xml, args.schema, args.eric_home, version)
    except (EricError, etree.LxmlError, OSError, ValueError) as exc:
        print(f"Referenzprüfung fehlgeschlagen. {exc}", file=sys.stderr)
        return 1
    print("XSD und lokale ERiC-Prüfung erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
