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

1. **Belege erfassen.** Das Original erhält beim Import einen SHA-256-Hash. Der Fall hält pro Fakt den Originalbeleg und seine Fundstelle fest. OCR und Sprachmodelle liefern Vorschläge für Inhalte, Kategorien und Rückfragen. Die prüfende Person bestätigt oder korrigiert die Vorschläge. Änderungen an den Falldaten machen die bisherige Vorschau ungültig.
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

## Geführter Fall für 2025

Starte `uv run finamt serve --no-browser` und öffne [die lokale Fallansicht](http://127.0.0.1:8000/einkommensteuer).

1. Beantworte unter **Steuersituation** die Fragen für 2025. Lade danach die gültigen Lohnsteuerbescheinigungen, einen Arbeitskalender und weitere Nachweise. In **Originalbelege** kannst du jedes Original öffnen. Wähle bei PDF-Vorschlägen die betreffende Seite.
2. Lies die Lohnsteuerbescheinigungen aus und bestätige die Positionen neben dem Original. Für Scans kannst du die lokale OCR einschalten. Die weiteren Formulare erfassen Arbeitstage, Ausgaben, Reisen, Vorsorge, Spenden und haushaltsnahe Leistungen. Erfasse eine Fortbildungserstattung bei der Ausgabe mit Datum und Erstattungsbeleg. Unter **Dienstreisetag und Fahrtkilometer** kannst du die gefahrenen Kilometer mit eigenem Nachweis eintragen. Weitere Angaben wie Fahrkartenkosten und Vorauszahlungen lassen sich in den erweiterten Angaben ergänzen.
3. Bestätige das Profil für den Hauptvordruck und erstelle die Vorschau. Die Regelprüfung gleicht die Lohnpositionen erneut mit lesbaren PDFs ab. Bei einer Abweichung bleibt die Abschlussbestätigung gesperrt. Offene Fragen und manuelle Prüfpunkte stehen neben der Übersicht.
4. Gehe Arbeitslohn, Werbungskosten, Jahresschätzung und Anlagen durch. **Prüfen** öffnet Rechenweg und Fundstellen. Nach dem Durchgang kannst du die Übersicht bestätigen und den Prüfentwurf als JSON speichern. Speichere die Falldatei und die Originale separat, um später weiterzuarbeiten. Die Anwendung speichert diese Dateien nicht dauerhaft auf dem Server.

Unter **Ausgaben und Arbeitstage** kannst du einen Arbeitskalender für 2025 als CSV übernehmen. Lade die Vorlage herunter, speichere sie als UTF-8 mit Semikolon als Trennzeichen und füge sie unter **Belege** hinzu. Prüfe die Anzahl der Tage und öffne bei Bedarf den Kalender, bevor du die Einträge übernimmst. Jeder Tag verweist auf seine CSV-Zeile. Doppelte Datumsangaben und ungültige Zeilen stoppen den Import. Trage zusätzlich die bestätigte Pendelstrecke ein, wenn der Kalender Besuche an der ersten Tätigkeitsstätte enthält.

Über **Fortbildungsbelege abgleichen** prüft finamt die angehängten PDFs mit Text und Textdateien gesammelt. Geeignet sind Rechnungen mit ausdrücklich bezeichneter beruflicher Fortbildung, Rechnungsnummer, Anbieter und Rechnungsbetrag. Zahlungsbeleg und Erstattung brauchen dieselbe Rechnungsnummer, denselben Anbieter, jeweils ihren Betrag und ein belegtes Zahlungsdatum. Beim Zahlungsbeleg kann die Rechnungsnummer im Verwendungszweck stehen. Die Angaben eines Nachweises stehen auf einer Seite. Öffne Rechnung, Zahlung und Erstattung im Vorschlag und bestätige den Vorgang. Kommt später ein passender Erstattungsbeleg hinzu, kannst du ihn beim erneuten Abgleich zu der bestätigten Fortbildung ergänzen. In der Übersicht bleiben alle Fundstellen verfügbar. Bei fehlenden oder widersprüchlichen Angaben erscheint eine Rückfrage mit den betreffenden Originalen.

Bei einem als Kontoauszug bezeichneten PDF oder Textbeleg können mehrere nummerierte Buchungen auf einer Seite stehen. Jede Buchung beginnt mit einer eigenen Überschrift wie **Buchung 2**. Datum, Empfänger, Betrag und Rechnungsnummer müssen in derselben Buchung stehen. Der Vorschlag verweist auf die Seite und die konkrete Buchung. Bei zwei Buchungen für dieselbe Rechnungsnummer erscheint eine Rückfrage.

Tabellarische PDF-Kontoauszüge können Buchungstag, Empfänger, Verwendungszweck und Betrag in klar getrennten Spalten liefern. Jede Buchungszeile muss auf einer Textzeile stehen. Der Betrag einer Abbuchung trägt ein Minuszeichen. Die Währung EUR steht am Betrag oder in der Spaltenüberschrift. finamt übernimmt das Buchungsdatum aus der entsprechenden Spalte und verweist auf die konkrete Tabellenzeile. Vorgemerkte Umsätze brauchen einen Nachweis der tatsächlichen Zahlung.

Für Rückfragen und Belegvorschläge kannst du ein lokales Sprachmodell einschalten. Ein zweites Modell kann bestätigte Zahlen und ausgewählte Belegauszüge in einem separaten Aufruf prüfen. Es erhält den Erfassungsdialog nicht und stellt Rückfragen. Die Modellgewichte können beim ersten Aufruf heruntergeladen werden. Eingaben und Inferenz bleiben lokal.

Bei Belegvorschlägen aus dem Original prüft finamt den Betrag und einen als Zahlung oder Erstattung ausgewiesenen Termin im Steuerjahr. Der Quellenverweis enthält beide Fundstellen. Bei mehreren Zahlungsdaten auf derselben Seite muss der Betrag mit dem passenden Datum belegt sein. Unvollständige Belege lösen früh eine Rückfrage aus. Klar bezeichnete Einzelbelege zur privaten Haftpflicht, privaten Berufsunfähigkeitsversicherung und zu Erstattungen der gesetzlichen Pflegeversicherung brauchen keinen Modellaufruf. Bestätige den Vorschlag nach Sichtprüfung.

```bash
FINAMT_EST_GUIDE_MODEL=mistral:7b \
FINAMT_EST_REVIEW_MODEL=qwen2.5:7b-instruct-q4_K_M \
uv run finamt serve --no-browser
```

## Installation und Test unter Windows

`finamt-0.26.0-windows-x64-setup.exe` installiert finamt für das aktuelle Benutzerkonto unter `%LOCALAPPDATA%\Programs\finamt`. Beim Setup lädt die mitgelieferte, hashgeprüfte uv-Version Python und die im Lockfile festgelegten Abhängigkeiten. Dafür ist Internetzugang nötig. Anschließend startet **finamt** aus dem Windows-Startmenü. Die Fallansicht verwendet die [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Für Abrechnung und lesbare Lohn-PDFs genügt die Grundinstallation. Bei Verwendung von OCR können weitere Modelldateien heruntergeladen werden.

Aktiviere im Setup **Lokales KI-Modell herunterladen**, um Qwen3-4B-Instruct-2507 (Q4_K_M) für Rückfragen und Belegvorschläge einzurichten. Das Setup lädt rund 2,5 GB und prüft die SHA-256-Summen von GGUF-Modell und llama.cpp. Für das Modell sind zusätzlich rund 3 GB freier Speicherplatz vorgesehen. Nach der Einrichtung aktiviert der Startmenüeintrag das Modell für den Assistenten. Die Inferenz läuft auf dem eigenen Rechner und braucht keine Grafikkarte oder einen KI-Account. Die zweite Modellprüfung lässt sich weiterhin separat konfigurieren. Bei einem fehlgeschlagenen Modell-Download bleibt die Grundinstallation nutzbar und das Modell kann durch erneutes Setup eingerichtet werden. [Qwen-Modellkarte](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) · [GGUF](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF) · [llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/b12240)

Für den ersten Test eignet sich ein frisches Windows 11 (x64), etwa eine Test-VM. Vergleiche zuerst `Get-FileHash .\finamt-0.26.0-windows-x64-setup.exe -Algorithm SHA256` mit der mitgelieferten Prüfsumme. Öffne nach dem Setup finamt aus dem Startmenü. Unter **Belege** lädst du `fall-vollstaendig.json` und die Originale aus dem Ordner `beispielfall`. Öffne einen Beleg, berechne die Vorschau und speichere den Prüfentwurf. Ändere anschließend im Fragebogen eine Antwort auf **Unsicher** und berechne erneut. Der Teilentwurf bleibt verfügbar und die Jahresschätzung wird ausgesetzt.

Der Installer lässt sich aus dem Checkout mit Python ab 3.11, uv und [NSIS](https://nsis.sourceforge.io/Download) bauen. Optional `--makensis` mit dem absoluten Pfad zur Compilerdatei angeben.

```powershell
python scripts/windows/build_installer.py
./scripts/windows/test_install.ps1 -Installer ./dist/windows/finamt-0.26.0-windows-x64-setup.exe -CheckWindow
```

Der Test installiert unter einem temporären Pfad in einem frischen Benutzerprofil, prüft Startmenü, Beispielfall und lokale Oberfläche und deinstalliert danach wieder. `-WithAI` prüft zusätzlich den Modelldownload und eine lokale JSON-Antwort. Für einen interaktiven Windows-Test prüft `-CheckWindow` das Öffnen und Schließen des WebView2-Fensters. Der Test ohne Fenster eignet sich für die Windows-CI. Der Testbuild hat keine Codesignatur. Prüfe ihn in der Test-VM und beachte die Sicherheitseinstellungen des Rechners.

Aus einem Checkout lässt sich das Fenster auch ohne Setup öffnen.

```powershell
uv run --locked --extra windows-desktop finamt desktop
```

Der lokale Server startet beim Öffnen und endet beim Schließen des Fensters. Die beiden lokalen Sprachmodelle lassen sich wie in der Browseransicht über Umgebungsvariablen einschalten.

## Standardfragen und besondere Steuerfälle

Fragebogen `2025.1` klärt Wohnsitz, Veranlagungsart, Kinder, Auslandsbezug, weitere Einkünfte, Lohnersatzleistungen, besonderen Arbeitslohn, Versicherungswechsel, abweichende Arbeitswege und weitere Abzüge. Dazu kommt die Anzahl der gültigen Lohnsteuerbescheinigungen. Die Anzahl wird mit den bestätigten Bescheinigungen verglichen. Eine Bescheinigung mit Steuerklasse II löst eine zusätzliche Prüfung zur Frage nach Kindern aus. Die bestätigten Antworten stehen unter `intake` in der Falldatei.

Die Fallansicht und die CLI wenden dieselbe Prüfung an. Offene Antworten, fehlende Bescheinigungen oder ein Sachverhalt ohne passenden Regelpfad lassen den Fall als Teilentwurf bestehen. Der Entwurf nennt den jeweiligen Grund. Originalbelege und bestätigte Beträge bleiben abrufbar. Ein neues Steuerjahr oder ein zusätzlicher Regelpfad braucht eigene Referenzfälle für Berechnungen, Grenzen und Belegzuordnung.

Der Altersentlastungsbetrag ist im unterstützten Arbeitnehmerprofil abgedeckt. Das Jahresregelwerk leitet Prozentsatz und Höchstbetrag aus dem bestätigten Geburtsdatum ab und berechnet den Betrag aus dem regulären Bruttoarbeitslohn. [§ 24a EStG](https://www.gesetze-im-internet.de/estg/__24a.html)

## Zeitvergleich mit WISO Steuer

Erzeuge zwei fiktive Fälle aus ihren Originaldateien.

```bash
uv run python examples/einkommensteuer-2025/prepare_comparison.py vergleichsfaelle
```

| Fall | Unterlagen | Prüfpunkte |
| --- | --- | --- |
| `standardfall` | Lohnbescheinigung, Arbeitskalender, Pendelstrecke, Angaben zur Person und Steuersituation | 46.250,30 € Arbeitslohn, 160 Tage an der ersten Tätigkeitsstätte, 40 überwiegend im Homeoffice |
| `belegfall` | Dieselben Unterlagen sowie Fortbildungsrechnung und Zahlung, Arbeitgebererstattung, Dienstreise, Spende, Handwerkerrechnung und Kontoauszug | 265 € Fortbildung nach Erstattung, 44,80 € Reisekosten nach Erstattung, 150 € Spende, 350 € begünstigte Handwerkerkosten |

Beginne in beiden Anwendungen mit einem leeren Fall und denselben Unterlagen. Erfasse aktive Bearbeitungszeit, Wartezeit, Korrekturen und fehlende Werte. Prüfe nach Abschluss die Beträge am jeweiligen Beleg. Halte Installationszeit und Modell-Download fest, wenn sie beim ersten Durchlauf anfallen. Stoppe mit den fiktiven Daten vor dem Versand. Für einen Vergleich bis zur Abgabe zählt bei finamt auch die manuelle Übertragung aus dem Prüfentwurf. Der amtliche Datenabruf braucht einen eigenen Test mit vorher eingerichteter Berechtigung.

## ELSTER-Referenzprüfung für 2025

Der [ELSTER-Entwicklerbereich](https://www.elster.de/elsterweb/entwickler/login) stellt die Schnittstellenbeschreibung und das ERiC-SDK bereit. Benötigt werden die Beschreibung für die unbeschränkte Einkommensteuer 2025, das zugehörige XSD mit seinen Abhängigkeiten, die dokumentierte Datenartversion und ein offizielles synthetisches Referenz-XML. Verwende ein SDK für die lokale Plattform und das zur Referenz passende Schema.

```bash
uv run python scripts/validate_est_reference.py referenz.xml \
  --schema /pfad/zum/referenzschema.xsd \
  --eric-home /pfad/zur/eric-bibliothek \
  --datenart-version "$FINAMT_EST_REFERENZVERSION"
```

Setze `FINAMT_EST_REFERENZVERSION` auf die dokumentierte Datenartversion. Das Werkzeug prüft dasselbe XML zuerst gegen das XSD und ruft dann ERiC mit `ERIC_VALIDIERE` auf. Halte SDK-Version, Datenartversion und Ergebnis für die Abnahme fest. Auf dieser Grundlage kann der nächste Schritt die Formularfelder samt Rechenweg auf die amtlichen XML-Felder abbilden und einen synthetischen Fall für das ELSTER-Testverfahren erzeugen.

## CLI und Beispielfälle

Der synthetische [erweiterte Beispielfall](../../examples/einkommensteuer-2025/fall-vollstaendig.json) enthält alle für die Jahresschätzung erforderlichen Angaben. Die [kleine Anlage-N-Variante](../../examples/einkommensteuer-2025/fall.json) enthält Arbeitslohn, Pendelstrecke und Homeoffice.

```bash
uv run finamt est examples/einkommensteuer-2025/fall-vollstaendig.json > pruefentwurf.json
uv run finamt est-extract lohnsteuerbescheinigung.pdf
uv run --extra dev pytest
```

In `documents` stehen Pfad und SHA-256-Hash jedes Originals. Relative Pfade werden vom Ordner der Falldatei aus aufgelöst. Ein PDF-Verweis braucht eine Seitennummer ab 1 und eine Fundstelle. Bei anderen Dateien genügt eine eindeutige Textfundstelle. Geldbeträge und Entfernungen sind Zeichenketten mit Dezimalpunkt, etwa `"46250.30"` oder `"21.70"`. Leere Bescheinigungsfelder bleiben weg.

`reviewed_standard_case` bestätigt den Abgleich mit den Belegen. Erfasst werden die Positionen 3–6, 17–18, 20 und 22–27 gültiger Lohnsteuerbescheinigungen. Identische Dateien und wiederholte Transfertickets werden abgewiesen. Bei Korrekturen ist die gültige Bescheinigung maßgeblich. Versorgungsbezüge, Entschädigungen und Lohnersatzleistungen liegen außerhalb der Jahresschätzung.

Erfasst werden eine Strecke zur ersten Tätigkeitsstätte und ein Verkehrsmittel für alle dort angegebenen Hin- und Rückfahrten. Ein Kalendertag wird einmal erfasst. `permanently_without_other_workplace` gilt, wenn für die Tätigkeit dauerhaft kein anderer Arbeitsplatz zur Verfügung steht. Bei zeitweise fehlendem Arbeitsplatz gelten die allgemeinen Bedingungen. Der aktuelle Fallumfang setzt voraus, dass für die erfassten Tage keine konkurrierenden Kosten für ein häusliches Arbeitszimmer oder Unterkunftskosten aus doppelter Haushaltsführung angesetzt werden. Öffentliche Fahrkartenkosten betreffen die bestätigten Zahlungen für Arbeitswege im Steuerjahr. Zuschüsse von Jobcenter oder Arbeitsagentur, Sammelbeförderung, halbe Wege und gemischte Strecken folgen in Etappe 2.

`forms` enthält die Vorschau der amtlichen Zeilen für Anlage N, ESt 1 A, Vorsorgeaufwand, Sonderausgaben sowie Haushaltsnahe Aufwendungen und bei Bedarf Sonstiges. `fields` bleibt die Liste der Zeilen aus Anlage N. `summary` enthält die Zwischenergebnisse, `assessment` die optionale Jahresschätzung. `trace` verbindet jeden Wert mit den verwendeten Eingaben und Jahresregeln. CLI und Fallansicht prüfen Hashes, Seitenreferenzen und lesbare Lohn-PDFs. Die Fallansicht bietet zusätzlich die optionale Modellprüfung.

## Grenzen des Stands

Die Jahresschätzung deckt 2025 für eine in Deutschland wohnhafte Person ohne Kinder, mit Einzelveranlagung und ausschließlich regulärem inländischem Arbeitslohn ab. Unterstützt werden eine Pendelstrecke mit einem Verkehrsmittel, inländische Dienstreisen im dokumentierten Standardprofil und ein Versicherungsstatus für das ganze Jahr. Wechselnde Pendelstrecken, gemischte Verkehrsmittel, doppelte Haushaltsführung, Auslandssachverhalte, weitere Einkunftsarten und Zusammenveranlagung sind weitere Etappen.

Die amtlichen Zeilennummern dienen der Sichtprüfung. Zur validierten ELSTER-Abgabe fehlen im Fork die ESt-Schnittstellenbeschreibung mit Datenartversion, die native ERiC-Testumgebung und die Abnahme mit synthetischen Referenzfällen. Der Entwurf bleibt bis dahin ein JSON-Export für die Prüfung.

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
