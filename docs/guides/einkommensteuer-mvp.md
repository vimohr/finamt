# Einkommensteuer für Arbeitnehmer

## Ausgangslage

Analysierter Upstream-Stand ist [`5718293`](https://github.com/spaceoctahedron/finamt/commit/571829362f926c99cdef6e2aebc5d7b94a4c88c7) (`main`, Paketversion 0.26.0).

| Bereich | Befund und Konsequenz für den Fork |
| --- | --- |
| Architektur | Das Python-Paket bietet eine Typer-CLI und eine lokale FastAPI-Anwendung. PyMuPDF liest PDF-Text, PaddleOCR und Tesseract verarbeiten Scans. Vier LLM-Aufrufe extrahieren Daten für die bestehende Belegbuchhaltung. Der React/Vite-Build liegt unter `src/finamt/ui/static/`. Für eine neue Oberfläche werden auch die Frontend-Quellen oder ein eigener reproduzierbarer Build gebraucht. |
| Datenmodelle | `ReceiptData`, `ReceiptItem`, `Counterparty` und `Posting` beschreiben Geschäftsvorfälle. `ReceiptData.id` hasht normalisierten OCR-Text. SQLite speichert Belege, Rohtext, Buchungen und Projektmetadaten. Für die Einkommensteuer braucht es eigene Personen- und Jahresfälle, Originaldatei-Hashes, Fundstellen pro Feld und nachvollziehbare Revisionen. `ProjectLayout` eignet sich später für die lokale Ablage. |
| ERiC und ELSTER | `tax/elster.py` enthält XML-Builder für UStVA, USt und KSt, einen E-Bilanz-Envelope sowie einen älteren HTTP-/Signaturpfad für UStVA. `tax/eric_wrapper.py` kapselt die native ERiC-Bibliothek über `ctypes`. `ElsterEricClient` unterscheidet Validierung, Testsendung und Produktivsendung. Der Changelog dokumentiert eine angenommene USt-Jahreserklärung. Die Funktionen belegen keinen ESt-XML-Vertrag. |
| Tests | pytest deckt Fachmodule, SQLite, die Extraktionspipeline und die CLI ab. Die Wrapper-Tests simulieren die native Bibliothek. CI installiert Projekt und Testabhängigkeiten mit `uv` und führt pytest mit Coverage aus. ESt-Regeln, ESt-Schema und native ESt-Validierung brauchen eigene Referenzfälle. |
| Roadmap | Die README führt den ESt-XML-Builder als offen. Der Changelog dokumentiert die ESt-Zeile in der Erklärungsübersicht als Platzhalter. Beim KSt-Builder ist die README hinter dem Code zurück. |
| Lizenz | `LICENSE` und README nennen AGPL-3.0. Copyright- und Lizenzhinweise bleiben im Fork erhalten. Bei der Weitergabe und beim Betrieb einer modifizierten Version für entfernte Nutzer gelten die Quellcodepflichten der Lizenz, insbesondere Abschnitt 13. Für Sprachmodelle und das separat bezogene ERiC-SDK gelten deren jeweilige Nutzungsbedingungen. |

## Aufbau

1. **Belege erfassen.** Das Original erhält beim Import einen SHA-256-Hash. Der Import hält pro Fakt den Originalbeleg und seine Fundstelle fest. OCR und LLM dürfen Vorschläge für Inhalte, Kategorien und Rückfragen liefern. Die prüfende Person bestätigt oder korrigiert die Vorschläge. Korrekturen erzeugen eine neue Revision mit derselben Originalreferenz oder mit einem Ersatzbeleg.
2. **Fachregeln anwenden.** Der Jahresfall enthält ausschließlich bestätigte Fakten. Reine Python-Funktionen erzeugen Ergebnisse mit stabilen Regel-IDs, Fundstellen und Eingabewerten. Geldbeträge bleiben centgenau. Ein fehlender Sachverhalt wird als offen behandelt, wenn er für eine Berechnung nötig ist. Unbekannte Steuerjahre führen zu einem Fehler.
3. **Felder abbilden.** Ein eigener, versionierter Adapter übernimmt Beträge und Eingabefakten aus dem Jahresfall. Das amtliche Formular dient der Vorschau. Für XML sind das amtliche ESt-Schema, die passende Datenartversion und deren Rundungs- und eDaten-Vorgaben maßgeblich. Der prüfbare Entwurf enthält durch Verweise den ganzen Rechenweg.
4. **Erklärung abschließen.** Die Fallansicht zeigt fehlende Angaben, Grenzfälle und alle ausgehenden Werte. ERiC validiert das XML lokal. Die Testübermittlung läuft mit synthetischen Fällen. Eine produktive Sendung erfordert die ausdrückliche Freigabe des validierten Entwurfs. Dessen Hash, Schema und Transferbeleg werden im Projekt archiviert und bei einem erneuten Sendeversuch geprüft.

## Implementierungsplan

| Etappe | Umfang | Abnahme |
| --- | --- | --- |
| 1. Anlage N 2025 aus Belegdaten | Inländischer Standardfall für eine Person. Bestätigte Lohnsteuerbescheinigungen, getrennte Summen für Klassen I–V und VI, Entfernungspauschale, Tagespauschale im Homeoffice und Arbeitnehmer-Pauschbetrag. Lokaler CLI-Entwurf mit Formularreferenzen. | Ein synthetischer Jahresfall läuft vom Quelldokument bis zur Vorschau. Tarifgrenzen der Entfernungspauschale, die Höchstbeträge, der Nachweis von Fahrtkostenzuschüssen, die Quellenintegrität und fehlende Daten werden automatisiert geprüft. |
| 2. Vollständige Werbungskosten für den MVP | Pendelstreckenwechsel, gemischte Verkehrsmittel, Zuschüsse, Arbeitsmittel mit beruflichem Anteil, GWG und AfA, Fortbildung mit Abgrenzung zur Erstausbildung, berufliche Reisen mit Zeit, Fahrt, Unterkunft, Mahlzeiten und Erstattungen, weitere Werbungskosten. | Referenzfälle prüfen anteilige Nutzung, Zeitgrenzen, Reisekosten je Tag, Abzüge für Erstattungen und doppelte Belegerfassung. Anlage N enthält die Eingabewerte und den nachvollziehbaren Abzug. |
| 3. Vorsorgeaufwand und Sonderausgaben | Lohnsteuerbescheinigungen um die SV-Positionen erweitern. Versicherungsbescheinigungen, Arbeitgeberanteile, Zuschüsse und Rückerstattungen zuordnen. Kirchensteuer, unterstützte Sonderausgaben und Spenden nach § 10b EStG einschließlich Spendenvortrag erfassen. | Referenzfälle prüfen gesetzliche und private Versicherungen, Erstattungen, bereits gemeldete eDaten, Höchstbeträge und den Umgang mit Spendenvorträgen. |
| 4. Haushaltsnahe Aufwendungen | § 35a EStG nach Haushaltshilfe, Dienstleistungen und Handwerkerleistungen abbilden. Rechnungs- und Zahlungsnachweis, begünstigte Kosten, Höchstbeträge und Aufteilung je Haushalt erfassen. | Referenzfälle prüfen Arbeits- und Materialanteile, Erstattungen, Zahlungsnachweis, Höchstbeträge und Ausschluss doppelter Berücksichtigung. |
| 5. Jahresfall und Steuerberechnung | ESt 1 A, persönliche Angaben und Steuernummern, Belegprüfung und Rückfragen in der lokalen Oberfläche. Jahresregeln für Einkommen, Tarif, Solidaritätszuschlag, Kirchensteuer, Ermäßigungen und Lohnsteueranrechnung. Eingangskontrolle für Fälle außerhalb des unterstützten Profils. | Vollständige synthetische Arbeitnehmerfälle stimmen an Tarifschwellen und bei Erstattungen mit amtlichen Referenzrechnungen oder ERiC überein. Jeder berechnete Wert lässt sich bis zu Originalbelegen oder Rechtsgrundlagen verfolgen. |
| 6. ELSTER-Abgabe | Amtliche ESt-Schnittstellenbeschreibung und XSD für 2025 beziehen. Feldmatrix für ESt 1 A, N, Vorsorgeaufwand, Sonderausgaben und Haushaltsnahe Aufwendungen gegen Schema und Referenzdateien testen. ERiC-Adapter, Validierungsbericht und Testannahme ergänzen. | XML besteht XSD- und native Plausibilitätsprüfung. Ein synthetischer Fall erhält ein Transferticket im Testverfahren. Der produktive Pfad wird mit expliziter Freigabe, Wiederholungsprüfung und Archivierung abgenommen. |

Die ESt-Schnittstelle und die Hersteller-ID für den Fork parallel zur Fachlogik über den ELSTER-Entwicklerzugang vorbereiten. Vor jeder Veröffentlichung ein Steuerjahr samt Quellenstand und Schema festlegen. Familienfälle mit Zusammenveranlagung und Kindern, Progression und Auslandsbezug sowie weitere Einkunftsarten folgen als eigene Erweiterungen. Bis dahin müssen betroffene Fälle im Abgabedialog offen ausgewiesen werden.

## Anlage-N-Entwurf für 2025 ausprobieren

Der synthetische [Beispielfall](../../examples/einkommensteuer-2025/fall.json) enthält eine Lohnsteuerbescheinigung, einen Arbeitskalender und einen Streckennachweis. Aus dem Checkout lässt er sich so ausführen.

```bash
uv run finamt est examples/einkommensteuer-2025/fall.json > anlage-n-entwurf.json
```

Für einen eigenen Fall die erfassten Werte mit den Originalen abgleichen und in `documents` deren Pfad und SHA-256-Hash hinterlegen. Relative Pfade werden vom Ordner der Falldatei aus aufgelöst. Ein PDF-Verweis braucht die Seitennummer ab 1 und eine Fundstelle. Bei anderen Dateien genügt eine eindeutige Textfundstelle. Geldbeträge und Entfernungen sind Zeichenketten mit Dezimalpunkt, etwa `"46250.30"` oder `"21.70"`. Leere Bescheinigungsfelder bleiben weg. Beträge mit Vorzeichen unter null liegen außerhalb des aktuellen Eingabeprofils.

`reviewed_standard_case` bestätigt den Abgleich und den Umfang des Falls. Erfasst werden die Positionen 3–6 und 17–18 gültiger Lohnsteuerbescheinigungen einer Person für regulären inländischen Arbeitslohn. Identische Dateien und wiederholte Transfertickets werden abgewiesen. Bei Korrekturen die jeweils gültige Bescheinigung verwenden. Versorgungsbezüge, Entschädigungen, Lohnersatzleistungen, Korrekturen des Bruttoarbeitslohns und weitere Zeilen der Bescheinigung erfordern eine Erweiterung des Entwurfs.

Erfasst werden eine Strecke zur ersten Tätigkeitsstätte und ein Verkehrsmittel für alle dort angegebenen Hin- und Rückfahrten. Ein Kalendertag wird einmal erfasst. `permanently_without_other_workplace` gilt, wenn für die Tätigkeit dauerhaft kein anderer Arbeitsplatz zur Verfügung steht. Bei zeitweise fehlendem Arbeitsplatz gelten die allgemeinen Bedingungen. Der aktuelle Fallumfang setzt voraus, dass für die erfassten Tage keine konkurrierenden Kosten für ein häusliches Arbeitszimmer oder Unterkunftskosten aus doppelter Haushaltsführung angesetzt werden. Öffentliche Fahrkartenkosten betreffen die bestätigten Zahlungen für Arbeitswege im Steuerjahr. Zuschüsse von Jobcenter oder Arbeitsagentur, Sammelbeförderung, halbe Wege und gemischte Strecken folgen in Etappe 2.

`fields` enthält aus der Anlage N übernommene Zeilen und Kennzahlen für die Vorschau. `summary` enthält die Rechenergebnisse für den unterstützten Umfang. `trace` verbindet jeden Wert mit den verwendeten Eingaben und Regeln. Eine Fundstelle enthält die Beleg-ID, gegebenenfalls die Seite und das Feld oder die Textposition. Unter `documents` stehen Dateiname und geprüfter Hash. Berechnungsparameter verweisen auf ihre amtlichen Quellen. Angaben wie Fundstellen und Zahlwerte stammen aus der bestätigten Eingabe. Die CLI prüft die Datei- und Seitenreferenzen. Die automatische Extraktion, ESt 1 A und das ERiC-XML sind weitere Etappen.

```bash
uv run --extra dev pytest
```

## Quellen

- [finamt-README und Roadmap](https://github.com/spaceoctahedron/finamt/blob/571829362f926c99cdef6e2aebc5d7b94a4c88c7/README.md#todo)
- [finamt-Changelog](https://github.com/spaceoctahedron/finamt/blob/571829362f926c99cdef6e2aebc5d7b94a4c88c7/CHANGELOG.md) und [AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html)
- [ELSTER-Entwicklerzugang und ERiC](https://www.elster.de/eportal/infoseite/entwickler) und [ELSTER-Hilfe für 2025](https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_est_ufa_10_2025)
- [Amtlicher Vordruck Anlage N 2025](https://www.formulare-bfinv.de/ffw/action/invoke.do?id=034027_25) und [PDF-Abzug des Vordrucks](https://www.buhl.de/steuer/wp-content/uploads/sites/31/2026/02/Anlage_N_2025.pdf)
- [Geändertes Muster der Lohnsteuerbescheinigung 2025](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Lohnsteuer/2025-02-20-geaen-ausdruck-elektron-LSt-besch-2025.html)
- [§ 9 EStG für 2025](https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/II-Einkommen-2-24b/4-Ueberschuss-der-Einnahmen-ueber-die-Wk-8-9a/Paragraf-9/inhalt.html) und [§ 9a EStG für 2025](https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/II-Einkommen-2-24b/4-Ueberschuss-der-Einnahmen-ueber-die-Wk-8-9a/Paragraf-9a/inhalt.html)
- [BMF-Schreiben zur Tagespauschale](https://ao.bundesfinanzministerium.de/lsth/2025/B-Anhaenge/Anhang-19/I/anhang-19-I.html)
- [§ 10 EStG für 2025](https://esth.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/II-Einkommen-2-24b/5-Sonderausgaben-10-10g/Paragraf-10/paragraf-10.html) und [§ 10b EStG für 2025](https://esth.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/II-Einkommen-2-24b/5-Sonderausgaben-10-10g/Paragraf-10b/paragraf-10b.html)
- [§ 35a EStG](https://www.gesetze-im-internet.de/estg/__35a.html) und [§ 32a EStG für 2025](https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/IV-Tarif-31-34b/Paragraf-32a/paragraf-32a.html)
