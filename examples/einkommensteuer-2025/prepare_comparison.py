"""Create two sets of synthetic originals for comparing manual tax workflows."""

from __future__ import annotations

import re
import textwrap
from argparse import ArgumentParser
from datetime import date
from pathlib import Path

import fitz

from finamt.tax.est.workday_csv_2025 import workday_csv_template

EXAMPLES = Path(__file__).resolve().parent


def write_pdf(path: Path, text: str) -> None:
    lines = ["FIKTIVER BELEG · Softwaretest 2025", ""]
    lines.extend(textwrap.fill(line, width=85) for line in text.splitlines())
    with fitz.open() as document:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(42, 48, 553, 789), "\n".join(lines), fontsize=10)
        path.write_bytes(document.tobytes(no_new_id=True))


def calendar() -> bytes:
    rows = [workday_csv_template().strip("\r\n")]
    weeks_off = {16, 17, 18, 19, 22, 24, 32, 33, 40, 47}
    for week in range(2, 52):
        if week not in weeks_off:
            for weekday in range(1, 6):
                day = date.fromisocalendar(2025, week, weekday)
                entry = "nein;überwiegend;nein" if weekday == 3 else "ja;nein;nein"
                rows.append(f"{day};{entry}")
    return ("\r\n".join(rows) + "\r\n").encode("utf-8")


def create_cases(output: Path) -> None:
    sections = {
        line[0]: line[3:]
        for line in (EXAMPLES / "weitere-belege.txt").read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-J]\. ", line)
    }
    payroll = (EXAMPLES / "lohnsteuerbeleg-mit-vorsorge.txt").read_text(encoding="utf-8")
    payroll = re.sub(r"^Nr\. (\d+[a-z]?): (\S+) EUR (.+)$", r"\1. \3 \2 EUR", payroll, flags=re.M)
    profile = (
        sections["I"] + "\n" + sections["J"] + "\nWohnsitz ganzjährig in Deutschland. "
        "Kein Auslandsbezug, keine Lohnersatzleistung und keine weiteren Einkünfte. "
        "Eine gültige Lohnsteuerbescheinigung, kein besonderer Arbeitslohn. "
        "Keine weiteren Sonderfälle oder Abzüge über die Unterlagen dieses Falls hinaus."
    )

    for name in ("standardfall", "belegfall"):
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        wage_text = (
            payroll if name == "belegfall" else re.sub(r"^20\. .*\n", "", payroll, flags=re.M)
        )
        write_pdf(folder / "01-lohnsteuer.pdf", wage_text)
        (folder / "02-arbeitskalender.csv").write_bytes(calendar())
        write_pdf(
            folder / "03-pendelstrecke.pdf",
            (EXAMPLES / "streckennachweis.txt").read_text(encoding="utf-8"),
        )
        write_pdf(folder / "04-steuersituation.pdf", profile)

    folder = output / "belegfall"
    write_pdf(folder / "05-fortbildung.pdf", sections["A"])
    write_pdf(
        folder / "06-fortbildung-erstattung.pdf",
        "Arbeitgeberzuschuss zum Fachseminar. Erstattung von 125,00 EUR am 30.04.2025. "
        "Der Zuschuss betrifft die Teilnahmegebühr vom 10.04.2025.",
    )
    write_pdf(folder / "07-dienstreise.pdf", sections["D"])
    write_pdf(folder / "08-spende.pdf", sections["E"])
    write_pdf(folder / "09-handwerker.pdf", sections["G"])
    write_pdf(folder / "10-kontoauszug.pdf", sections["H"] + " Überwiesener Betrag 525,00 EUR.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory for the synthetic cases")
    create_cases(parser.parse_args().output)
