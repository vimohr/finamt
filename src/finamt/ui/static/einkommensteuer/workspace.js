"use strict";

const el = (id) => document.getElementById(id);
const formValue = (form, name) => form.elements.namedItem(name).value.trim();
const emptyCase = () => ({
  schema_version: 1,
  tax_year: 2025,
  reviewed_standard_case: true,
  documents: {},
  wage_certificates: [],
});
const labels = {
  gross_wages: "Bruttoarbeitslohn", commute_deduction: "Entfernungspauschale",
  home_office_deduction: "Homeoffice-Tagespauschale", work_equipment: "Arbeitsmittel",
  training: "Fortbildung", professional_association: "Berufsverbände und Gewerkschaften",
  other_work: "Weitere Werbungskosten", travel_deduction: "Reisekosten",
  supported_expenses: "Erfasste Werbungskosten", employment_deduction: "Angesetzte Werbungskosten",
  employment_income: "Einkünfte aus nichtselbständiger Arbeit",
  taxable_income: "Zu versteuerndes Einkommen", insurance_deduction: "Abziehbare Vorsorgeaufwendungen",
  age_relief: "Altersentlastungsbetrag", total_income: "Gesamtbetrag der Einkünfte",
  special_expense_deduction: "Abziehbare weitere Sonderausgaben",
  tariff_income_tax: "Tarifliche Einkommensteuer", assessed_income_tax: "Einkommensteuer nach Ermäßigungen",
  assessed_solidarity: "Solidaritätszuschlag", assessed_church_tax: "Kirchensteuer",
  income_tax_balance: "Saldo Einkommensteuer", solidarity_balance: "Saldo Solidaritätszuschlag",
  church_tax_balance: "Saldo Kirchensteuer", tax_balance: "Voraussichtliche Nachzahlung (+) oder Erstattung (−)",
  wage_tax: "Einbehaltene Lohnsteuer", solidarity_surcharge: "Einbehaltener Solidaritätszuschlag",
  church_tax: "Einbehaltene Kirchensteuer",
  tax_free_commute_reimbursements: "Steuerfreie Arbeitgeberleistungen für Arbeitswege",
  flat_rate_taxed_commute_reimbursements: "Pauschal versteuerte Fahrtkostenzuschüsse",
  commute_days: "Tage an der ersten Tätigkeitsstätte", commute_distance_km: "Einfache Entfernung",
  commute_car_km: "Kilometer mit eigenem oder überlassenem Pkw", commute_other_km: "Kilometer mit anderen Verkehrsmitteln",
  commute_ticket_costs: "Öffentliche Fahrkartenkosten",
  home_office_regular_days: "Homeoffice-Tage ohne Besuch der Tätigkeitsstätte",
  home_office_no_other_workplace_days: "Homeoffice-Tage ohne anderen Arbeitsplatz",
  pension_employee: "Rentenversicherung, Arbeitnehmeranteil", pension_employer: "Rentenversicherung, Arbeitgeberanteil",
  health_payroll: "Gesetzliche Krankenversicherung laut Bescheinigung", care_payroll: "Pflegeversicherung laut Bescheinigung",
  unemployment_payroll: "Arbeitslosenversicherung laut Bescheinigung",
  church_tax_paid_total: "Gezahlte Kirchensteuer", church_tax_refunded: "Erstattete Kirchensteuer",
  household_minijob_costs: "Haushaltshilfe im Minijob", household_service_costs: "Haushaltsnahe Dienstleistungen",
  household_craft_costs: "Begünstigte Handwerkerkosten", household_craft_invoice_net: "Rechnungsbetrag nach Erstattung",
  charitable_domestic: "Spenden im Inland", charitable_eu_eea: "Spenden im EU-/EWR-Ausland",
  "taxpayer.first_name": "Vorname", "taxpayer.last_name": "Nachname", "taxpayer.date_of_birth": "Geburtsdatum",
  "taxpayer.street": "Straße", "taxpayer.house_number": "Hausnummer", "taxpayer.postcode": "Postleitzahl",
  "taxpayer.city": "Wohnort", "taxpayer.religion": "Religionsschlüssel", "taxpayer.occupation": "Beruf",
  "taxpayer.tax_id": "Steuer-ID", "taxpayer.tax_number": "Steuernummer", "taxpayer.iban": "IBAN",
  "taxpayer.tax_office": "Zuständiges Finanzamt",
};
const wagePositions = {
  "3": "Bruttoarbeitslohn", "4": "Lohnsteuer", "5": "Solidaritätszuschlag", "6": "Kirchensteuer",
  "17": "Steuerfreie Leistungen für Arbeitswege", "18": "Pauschal besteuerte Fahrtkostenzuschüsse",
  "20": "Steuerfreie Verpflegungszuschüsse", "22a": "AG-Anteil gesetzliche Rente",
  "22b": "AG-Zuschuss Versorgungswerk", "23a": "AN-Anteil gesetzliche Rente",
  "23b": "AN-Anteil Versorgungswerk", "24a": "AG-Zuschuss gesetzliche Krankenversicherung",
  "24b": "AG-Zuschuss private Krankenversicherung", "24c": "AG-Zuschuss gesetzliche Pflegeversicherung",
  "25": "AN-Beitrag gesetzliche Krankenversicherung", "26": "AN-Beitrag Pflegeversicherung",
  "27": "AN-Beitrag Arbeitslosenversicherung",
};
const categories = {
  expenses: {
    work_supplies: "Verbrauchsmaterial für die Arbeit", professional_association: "Berufsverband oder Gewerkschaft",
    training: "Berufliche Fortbildung", initial_training: "Erstausbildung außerhalb des Dienstverhältnisses",
    application: "Bewerbung", account_fees: "Berufliche Kontoführung", other_work: "Sonstige Werbungskosten",
  },
  travel_costs: {
    transport: "Dienstreise · Fahrtkosten", lodging: "Dienstreise · Übernachtung", incidentals: "Dienstreise · Nebenkosten",
    reimbursement: "Dienstreise · Erstattung für Fahrt oder Unterkunft",
    meal_reimbursement: "Dienstreise · zusätzliche Verpflegungserstattung",
  },
  donations: {
    charitable_domestic: "Gemeinnützige Spende im Inland", charitable_eu_eea: "Gemeinnützige Spende EU/EWR",
    political_party: "Spende an politische Partei", voters_group: "Spende an Wählervereinigung",
  },
  insurance_payments: {
    statutory_pension: "Zusatzbeitrag gesetzliche Rentenversicherung", professional_pension: "Versorgungswerk",
    basic_private_pension: "Basisrente (Rürup)", private_basic_health: "Private Krankenversicherung · Basisbeitrag",
    private_care: "Private Pflege-Pflichtversicherung", statutory_health: "Gesetzliche Krankenversicherung · weiterer Beitrag",
    statutory_health_no_sick_pay: "Gesetzliche Krankenversicherung · ohne Krankengeld",
    statutory_care: "Gesetzliche Pflegeversicherung · weiterer Beitrag", unemployment: "Zusätzliche Arbeitslosenversicherung",
    disability: "Berufs- oder Erwerbsunfähigkeitsversicherung", liability_accident_term_life: "Haftpflicht, Unfall oder Risikoleben",
    statutory_health_refund: "Erstattung gesetzliche Krankenversicherung mit Krankengeld",
    statutory_health_no_sick_pay_refund: "Erstattung gesetzliche Krankenversicherung ohne Krankengeld",
    statutory_care_refund: "Erstattung gesetzliche Pflegeversicherung", private_basic_health_refund: "Erstattung private Basisversicherung",
    private_care_refund: "Erstattung private Pflegeversicherung",
  },
  church_tax_payments: {
    paid: "Kirchensteuer · Zahlung für frühere Jahre", prepayment: "Kirchensteuer · Vorauszahlung für 2025",
    refunded: "Kirchensteuer · Erstattung im Jahr 2025",
  },
};
const stageMessages = {
  intake: "Beantworte die Fragen zur Steuersituation. Bei offenen Angaben zeige ich dir, was zu klären ist.",
  documents: "Du kannst jeden Beleg hier ansehen und eine bereits gespeicherte Falldatei laden.",
  payroll: "Wähle eine Bescheinigung aus. Ich schlage die erkannten Positionen vor. Prüfe sie neben dem Original, bevor du sie übernimmst.",
  expenses: "Gehen wir die Werbungskosten durch. Hattest du Dienstreisen, Fortbildungskosten oder Ausgaben für Arbeitsmittel?",
  profile: "Für die Jahresschätzung brauche ich noch die bestätigten Angaben zum Hauptvordruck und die Versicherungsart.",
  review: "Jetzt gehe ich mit dir durch die Vorschau. Klicke auf einen Belegverweis, um die Zahl am Original nachzuvollziehen.",
};
let taxCase = emptyCase();
const originalFiles = new Map();
let activeStage = "intake";
let intakeCatalogue = null;
let proposal = null;
let proposalVersion = null;
let wageEdit = null;
let workdayProposal = [];
let draft = null;
let revision = 0;
let walkthrough = [];
let walkIndex = 0;
const reviewedSections = new Set();
const chatHistory = [];
let objectUrl = null;

function button(label, handler) {
  const control = document.createElement("button");
  control.type = "button";
  control.textContent = label;
  control.addEventListener("click", handler);
  return control;
}

function notify(message, error = false) {
  el("notice").textContent = message;
  el("notice").classList.toggle("error", error);
  el("notice").hidden = !message;
}

function say(message, author = "assistant") {
  const bubble = document.createElement("p");
  bubble.className = author === "user" ? "turn user" : "turn";
  bubble.textContent = message;
  const conversation = el("conversation");
  conversation.append(bubble);
  conversation.scrollTop = conversation.scrollHeight;
}

function changeStage(stage) {
  activeStage = stage;
  document.querySelectorAll("[data-sheet]").forEach((sheet) => {
    sheet.hidden = sheet.dataset.sheet !== stage;
  });
  document.querySelectorAll("[data-step]").forEach((item) => {
    if (item.dataset.step === stage) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
  notify("");
  say(stageMessages[stage]);
}

async function request(path, options) {
  const response = await fetch("/einkommensteuer/api/" + path, options);
  const data = await response.json();
  if (!response.ok) {
    const reason = Array.isArray(data.detail)
      ? data.detail.map((error) => [error.field ?? error.loc?.join("."), error.message ?? error.msg].join(" · ")).join("\n")
      : data.detail;
    throw new Error(reason || "Die Anfrage konnte nicht verarbeitet werden.");
  }
  return data;
}

async function run(control, action) {
  control.disabled = true;
  notify("");
  try {
    await action();
  } catch (error) {
    notify(error.message, true);
  } finally {
    control.disabled = false;
  }
}

function resetWorkdayImport() {
  workdayProposal = [];
  el("workday-import-preview").hidden = true;
}

function changed() {
  revision += 1;
  resetWorkdayImport();
  draft = null;
  el("review-output").hidden = true;
  el("save-draft").disabled = true;
  el("candidate-controls").hidden = true;
  el("case-json").value = JSON.stringify(taxCase, null, 2);
  renderOriginals();
  renderWages();
  const count = ["expenses", "donations", "insurance_payments", "travel_costs", "household_costs",
    "work_assets", "church_tax_payments", "travel_mileage"].reduce((sum, key) => sum + (taxCase[key]?.length ?? 0), 0);
  el("expenses-count").textContent = count + " Ausgaben · " + (taxCase.workdays?.length ?? 0) + " erfasste Arbeitstage";
}

function renderOriginals() {
  for (const select of document.querySelectorAll("[data-doc-select]")) {
    const selected = select.value;
    select.replaceChildren(new Option("Beleg auswählen", ""));
    for (const [id, info] of Object.entries(taxCase.documents)) {
      const file = originalFiles.get(id);
      if (file && (!select.hasAttribute("data-csv-only") || /\.csv$/i.test(file.name))) {
        select.add(new Option(info.path, id));
      }
    }
    select.value = originalFiles.has(selected) ? selected : "";
  }
  updatePageOption();
  const documents = el("documents");
  documents.replaceChildren();
  for (const [id, info] of Object.entries(taxCase.documents)) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = info.path + (originalFiles.has(id) ? "" : " · Original fehlt");
    row.append(name);
    if (originalFiles.has(id)) row.append(button("Ansehen", () => viewOriginal(id)));
    documents.append(row);
  }
}

async function attach(file) {
  if (!/\.(?:pdf|txt|csv|png|jpe?g)$/i.test(file.name)) throw new Error("Dateityp für Beleg nicht unterstützt.");
  if (file.size > 12 * 1024 * 1024) throw new Error("Der Beleg ist größer als 12 MiB.");
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  let id = Object.keys(taxCase.documents).find((key) => taxCase.documents[key].sha256 === hash);
  if (!id) {
    if (Object.keys(taxCase.documents).length >= 50) throw new Error("Der Fall kann bis zu 50 Belege enthalten.");
    id = "beleg_" + hash.slice(0, 24);
    taxCase.documents[id] = {path: file.name, sha256: hash};
  }
  originalFiles.set(id, file);
}

async function viewOriginal(id, page = null, locator = "") {
  const file = originalFiles.get(id);
  if (!file) {
    notify("Bitte das Original zu diesem Verweis erneut auswählen.", true);
    return;
  }
  const dialog = el("original-dialog");
  const host = el("original-content");
  el("original-title").textContent = file.name;
  el("original-location").textContent = [page ? "Seite " + page : "", locator].filter(Boolean).join(" · ");
  host.replaceChildren();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  const ext = file.name.split(".").pop().toLowerCase();
  if (ext === "pdf") {
    objectUrl = URL.createObjectURL(new Blob([file], {type: "application/pdf"}));
    const frame = document.createElement("iframe");
    frame.title = "PDF-Original";
    frame.src = objectUrl + (page ? "#page=" + page : "");
    host.append(frame);
  } else if (["png", "jpg", "jpeg"].includes(ext)) {
    objectUrl = URL.createObjectURL(new Blob([file], {type: ext === "png" ? "image/png" : "image/jpeg"}));
    const image = document.createElement("img");
    image.alt = "Originalbeleg";
    image.src = objectUrl;
    host.append(image);
  } else {
    const text = document.createElement("pre");
    text.textContent = await file.slice(0, 250000).text();
    host.append(text);
  }
  if (!dialog.open) dialog.showModal();
}

function renderWages() {
  const list = el("wages");
  list.replaceChildren();
  for (const wage of taxCase.wage_certificates) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = taxCase.documents[wage.document]?.path ?? wage.document;
    row.append(
      name,
      button("Original", () => viewOriginal(wage.document, wage.page)),
      button("Bearbeiten", () => editWage(wage, [])),
      button("Eintrag entfernen", () => {
        taxCase.wage_certificates = taxCase.wage_certificates.filter((item) => item.document !== wage.document);
        if (wageEdit?.document === wage.document) el("payroll-edit").hidden = true;
        changed();
      }),
    );
    list.append(row);
  }
}

function editWage(wage, notes) {
  wageEdit = wage;
  const form = el("payroll-edit");
  form.elements.ticket.value = wage.transfer_ticket ?? "";
  form.elements.period.value = wage.period_end ?? "";
  form.elements.tax_class.value = wage.tax_class ?? "";
  form.elements.page.value = wage.page ?? "";
  for (const position of Object.keys(wagePositions)) {
    form.elements["wage_" + position].value = wage.amounts?.[position] ?? "";
  }
  el("payroll-caption").textContent = taxCase.documents[wage.document].path;
  el("payroll-notes").textContent = notes.join(" ");
  form.hidden = false;
}

function manualWage(id) {
  if (!id) return notify("Wähle zuerst einen Originalbeleg aus.", true);
  editWage(
    taxCase.wage_certificates.find((item) => item.document === id)
    ?? {document: id, page: /\.pdf$/i.test(taxCase.documents[id].path) ? 1 : null, amounts: {}},
    [],
  );
}

function source(form, prefix = "") {
  const id = formValue(form, prefix + "document");
  const reference = {document: id, locator: formValue(form, prefix + "locator")};
  if (/\.pdf$/i.test(taxCase.documents[id]?.path ?? "")) reference.page = Number(formValue(form, prefix + "page"));
  if (reference.page === 0) throw new Error("Gib die Seite im PDF an.");
  return reference;
}

function decimal(value) {
  const amount = value.replace(",", ".");
  if (!/^\d+(?:\.\d+)?$/.test(amount)) throw new Error("Gib einen Betrag ohne Tausendertrennzeichen ein, z. B. 1250,50.");
  return amount;
}

function add(collection, item) {
  (taxCase[collection] ??= []).push(item);
  changed();
}

function onForm(id, handler) {
  el(id).addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    run(event.submitter ?? form.querySelector('button[type="submit"]'), () => handler(form));
  });
}

function loadCase(json) {
  const incoming = JSON.parse(json);
  if (incoming?.schema_version !== 1 || incoming.tax_year !== 2025
      || !incoming.documents || Array.isArray(incoming.documents) || !Array.isArray(incoming.wage_certificates)) {
    throw new Error("Bitte eine Falldatei für 2025 im Format 1 verwenden.");
  }
  const filesByHash = new Map(
    [...originalFiles].map(([id, file]) => [taxCase.documents[id]?.sha256, file]),
  );
  for (const [id, info] of Object.entries(incoming.documents)) {
    if (!/^[A-Za-z0-9_-]+$/.test(id) || typeof info?.path !== "string" || !/^[a-f0-9]{64}$/.test(info.sha256)) {
      throw new Error("Mindestens ein Belegverweis in der Falldatei ist ungültig.");
    }
  }
  taxCase = incoming;
  originalFiles.clear();
  for (const [id, info] of Object.entries(taxCase.documents)) {
    if (filesByHash.has(info.sha256)) originalFiles.set(id, filesByHash.get(info.sha256));
  }
  wageEdit = null;
  el("payroll-edit").hidden = true;
  changed();
  loadProfile();
  loadIntake();
}

function loadIntake() {
  if (!intakeCatalogue) return;
  const form = el("scope-intake");
  form.reset();
  const intake = taxCase.intake;
  if (intake?.version === intakeCatalogue.version) {
    for (const {key} of intakeCatalogue.questions) form.elements.namedItem(key).value = intake.answers?.[key] ?? "";
    form.elements.wage_count.value = intake.wage_certificate_count ?? "";
  }
  el("intake-status").textContent = intake ? "Geladene Antworten werden bei der Vorschau erneut geprüft." : "";
  el("intake-findings").replaceChildren();
}

function loadProfile() {
  const form = el("profile");
  form.reset();
  const filing = taxCase.filing;
  if (!filing) return;
  for (const [key, value] of Object.entries(filing.taxpayer)) {
    const input = form.elements.namedItem(key);
    if (input) input.value = value ?? "";
  }
  form.elements.insurance.value = filing.insurance;
  form.elements.church.value = filing.religion_code ? filing.religion_code + ":" + filing.church_tax_region : "none";
  if (filing.case_facts?.document) {
    form.elements.document.value = filing.case_facts.document;
    form.elements.locator.value = filing.case_facts.locator;
    form.elements.page.value = filing.case_facts.page ?? "";
  }
  form.elements.reviewed.checked = filing.all_income_and_payments_reviewed;
}

function save(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function label(key) {
  for (const [suffix, text] of [["_classes_1_to_5", " · Steuerklassen I–V"], ["_class_6", " · Steuerklasse VI"]]) {
    if (key.endsWith(suffix)) return label(key.slice(0, -suffix.length)) + text;
  }
  return labels[key] ?? key.replaceAll("_", " ");
}

function formatted(entry) {
  if (entry.unit === "date") return String(entry.value).split("-").reverse().join(".");
  if (entry.unit === "EUR") return String(entry.value).replace(".", ",") + " €";
  return String(entry.value) + ({km: " km", days: " Tage", "%": " %"}[entry.unit] ?? "");
}

function traceDetails(key, seen = new Set()) {
  const host = document.createElement("div");
  if (!draft?.trace[key] || seen.has(key)) return host;
  const info = draft.trace[key];
  const title = document.createElement("p");
  title.textContent = label(key) + " · " + formatted(info);
  host.className = "trace";
  host.append(title);
  for (const source of info.sources ?? []) {
    const filename = taxCase.documents[source.document]?.path ?? source.document;
    host.append(button(filename + " · " + source.locator, () => viewOriginal(source.document, source.page, source.locator)));
  }
  if (info.legal_basis?.startsWith("https://")) {
    const link = document.createElement("a");
    link.href = info.legal_basis;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Amtliche Quelle";
    host.append(link);
  }
  if (info.inputs?.length) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Eingaben anzeigen (" + info.inputs.length + ")";
    details.append(summary);
    details.addEventListener("toggle", () => {
      if (!details.open || details.childElementCount > 1) return;
      const chain = new Set(seen).add(key);
      for (const input of info.inputs) details.append(traceDetails(input, chain));
    });
    host.append(details);
  }
  return host;
}

function showTrace(container, key) {
  const existing = container.querySelector(".trace");
  if (existing) existing.remove();
  else container.append(traceDetails(key));
}

function renderReview(data) {
  draft = data;
  reviewedSections.clear();
  walkthrough = [{
    title: "Werbungskosten und Arbeitslohn",
    intro: "Hier siehst du, welche Werbungskosten angesetzt wurden und was vom Arbeitslohn übrig bleibt.",
    fields: Object.entries(data.summary).map(([key, entry]) => ({key, ...entry})),
  }];
  if (data.assessment) walkthrough.push({
    title: "Voraussichtliche Steuer und Saldo",
    intro: "Die Vorschau berechnet die Jahressteuer aus deinen bestätigten Angaben und rechnet bereits gezahlte Beträge an.",
    fields: Object.entries(data.assessment.values).map(([key, entry]) => ({key, ...entry})),
  });
  for (const [title, fields] of Object.entries(data.forms)) {
    walkthrough.push({title, fields, intro: "Prüfe die vorbereiteten Angaben anhand der Formularzeilen und Originalbelege."});
  }
  walkIndex = 0;
  el("review-output").hidden = false;
  const issues = el("findings");
  issues.replaceChildren();
  for (const finding of data.review.findings) {
    const item = document.createElement("li");
    item.classList.toggle("blocker", finding.severity === "blocker");
    item.textContent = finding.message + " ";
    if (finding.trace) item.append(button("Fundstelle", () => showTrace(item, finding.trace)));
    if (finding.question || finding.code.startsWith("intake_")) {
      item.append(button("Zur Steuersituation", () => {
        changeStage("intake");
        if (finding.question) el("scope-intake").elements.namedItem(finding.question)?.focus();
      }));
    }
    issues.append(item);
  }
  const checked = data.review.status === "clarification_needed";
  const reviewer = {
    local_model: "Belegabgleich und zweiter lokaler Assistent ausgeführt.",
    rules_only: "Regelprüfung und erneutes Lesen der Lohnbelege ausgeführt.",
    unavailable: "Regelprüfung ausgeführt. Der zweite lokale Assistent war nicht erreichbar.",
  }[data.review.agent];
  el("review-agent").textContent = reviewer + (checked ? " Kläre die markierten Abweichungen." : "");
  el("findings-reviewed").checked = false;
  el("acknowledge-findings").hidden = checked || !(data.review.findings.length || data.review.agent === "unavailable");
  el("save-draft").disabled = false;
  say(checked ? "In der Vorschau sind Abweichungen markiert. Prüfe zuerst die Belege zu diesen Punkten."
    : "Die Vorschau ist erstellt. Wir beginnen mit Arbeitslohn und Werbungskosten und gehen danach die Anlagen durch.");
  renderWalk();
}

function renderWalk() {
  const step = walkthrough[walkIndex];
  if (!step) return;
  reviewedSections.add(walkIndex);
  el("walk-heading").textContent = step.title;
  el("walk-intro").textContent = step.intro;
  el("walk-prev").disabled = walkIndex === 0;
  el("walk-next").disabled = walkIndex + 1 === walkthrough.length;
  updateReviewConfirmation();
  const table = document.createElement("table");
  const header = table.createTHead().insertRow();
  for (const heading of ["Angabe", "Wert", "Herkunft"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = heading;
    header.append(cell);
  }
  const body = table.createTBody();
  for (const entry of step.fields) {
    const row = body.insertRow();
    row.insertCell().textContent = (entry.line ? "Zeile " + entry.line + " · " : "") + label(entry.key);
    const value = row.insertCell();
    value.className = "amount";
    value.textContent = formatted(entry);
    const trace = row.insertCell();
    trace.append(button("Prüfen", () => showTrace(trace, entry.trace)));
  }
  el("walk-result").replaceChildren(table);
}

function updateReviewConfirmation() {
  el("review-confirm").disabled = !draft?.assessment || draft.user_reviewed === true
    || draft.review.status === "clarification_needed" || reviewedSections.size !== walkthrough.length
    || (!el("acknowledge-findings").hidden && !el("findings-reviewed").checked);
}

el("scope-intake").addEventListener("input", () => {
  if (taxCase.intake) {
    delete taxCase.intake;
    changed();
  }
  el("intake-status").textContent = "Prüfe die aktuellen Antworten.";
  el("intake-findings").replaceChildren();
});
onForm("scope-intake", async (form) => {
  if (!intakeCatalogue) return;
  const answers = Object.fromEntries(intakeCatalogue.questions.map(({key}) => [key, formValue(form, key)]));
  const count = formValue(form, "wage_count");
  const intake = {version: intakeCatalogue.version, answers, wage_certificate_count: count ? Number(count) : null};
  taxCase.intake = intake;
  changed();
  const result = await request("intake", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(intake)});
  if (taxCase.intake !== intake) return;
  const message = {
    supported: "Deine Angaben passen zum unterstützten Profil. Als Nächstes prüfen wir die Belege.",
    needs_answers: "Einige Angaben brauchen noch Klärung. Du kannst inzwischen deine Belege erfassen.",
    outside_scope: "Der Fall braucht zusätzliche Steuerregeln. Du kannst die Belege und erfassten Angaben als Entwurf sichern.",
  }[result.status];
  el("intake-status").textContent = message;
  const findings = el("intake-findings");
  findings.replaceChildren();
  for (const finding of result.findings) {
    const item = document.createElement("li");
    item.textContent = finding.message;
    findings.append(item);
  }
  say(message);
});

request("intake").then((catalogue) => {
  intakeCatalogue = catalogue;
  for (const {key, prompt} of catalogue.questions) {
    const label = document.createElement("label");
    label.textContent = prompt;
    const select = document.createElement("select");
    select.name = key;
    select.required = true;
    select.append(new Option("Antwort wählen", ""), new Option("Ja", "yes"), new Option("Nein", "no"), new Option("Unsicher", "unsure"));
    label.append(select);
    el("intake-questions").append(label);
  }
  el("scope-intake").querySelector('button[type="submit"]').disabled = false;
  loadIntake();
}).catch(() => { el("intake-status").textContent = "Der Fragenkatalog konnte nicht geladen werden. Lade das Fenster erneut."; });

for (const item of document.querySelectorAll("[data-step], [data-next]")) {
  item.addEventListener("click", () => changeStage(item.dataset.step ?? item.dataset.next));
}

for (const [position, title] of Object.entries(wagePositions)) {
  const label = document.createElement("label");
  label.textContent = position + " · " + title;
  const input = document.createElement("input");
  input.name = "wage_" + position;
  input.inputMode = "decimal";
  input.required = position === "3";
  label.append(input);
  el("wage-amounts").append(label);
}

for (const [collection, entries] of Object.entries(categories)) {
  for (const [category, title] of Object.entries(entries)) {
    el("expense-category").add(new Option(title, collection + ":" + category));
  }
}

const mealLabels = {breakfast: "Frühstück", lunch: "Mittagessen", dinner: "Abendessen"};
for (const [kind, title] of Object.entries(mealLabels)) {
  const label = document.createElement("label");
  label.className = "checkbox";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.name = kind;
  label.append(checkbox, title);
  const amountLabel = document.createElement("label");
  amountLabel.hidden = true;
  amountLabel.textContent = "Eigene Zuzahlung für " + title + " in Euro";
  const amountInput = document.createElement("input");
  amountInput.inputMode = "decimal";
  amountInput.name = kind + "_amount";
  checkbox.addEventListener("change", () => { amountLabel.hidden = !checkbox.checked; });
  amountLabel.append(amountInput);
  el("meals").append(label, amountLabel);
}

el("originals").addEventListener("change", async (event) => {
  const input = event.currentTarget;
  const chosen = [...input.files];
  input.disabled = true;
  notify("");
  try {
    for (const file of chosen) await attach(file);
    if (chosen.length) say("Die ausgewählten Originale sind verfügbar. Wechsle zum Arbeitslohn oder erfasse weitere Ausgaben.");
  } catch (error) {
    notify(error.message, true);
  } finally {
    changed();
    input.value = "";
    input.disabled = false;
  }
});
el("case-file").addEventListener("change", (event) => {
  const input = event.currentTarget;
  run(input, async () => {
    const file = input.files[0];
    if (file) {
      if (file.size > 512000) throw new Error("Die Falldatei ist zu groß.");
      loadCase(await file.text());
      chatHistory.length = 0;
      el("conversation").replaceChildren();
      say("Der Fall ist geladen. Wähle die dazugehörigen Originalbelege aus.");
      notify("Falldaten geladen. Bitte die Originalbelege auswählen.");
    }
    input.value = "";
  });
});
el("original-dialog").addEventListener("close", () => {
  el("original-content").replaceChildren();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
});
el("payroll-manual").addEventListener("click", () => manualWage(formValue(el("payroll-read"), "document")));
el("payroll-original").addEventListener("click", () => viewOriginal(wageEdit.document, formValue(el("payroll-edit"), "page")));
onForm("payroll-read", async (form) => {
  const id = formValue(form, "document");
  const file = originalFiles.get(id);
  if (!file || !/\.pdf$/i.test(file.name)) throw new Error("Die Auslese braucht einen PDF-Beleg.");
  const body = new FormData();
  body.append("file", file);
  body.append("ocr", String(form.elements.ocr.checked));
  const result = await request("payroll", {method: "POST", body});
  const first = result.proposals[0];
  if (!first) {
    manualWage(id);
    el("payroll-notes").textContent = result.notes.join(" ");
    return;
  }
  const notes = [...result.notes, ...first.notes];
  if (result.proposals.length > 1) notes.push("Mehrere Seiten erkannt. Bitte jede Bescheinigung als eigene Datei erfassen.");
  if (first.missing.length) notes.push("Ergänze die fehlenden Felder am Original.");
  editWage({...first.certificate, document: id}, notes);
  say("Der Vorschlag ist bereit. Öffne das PDF, gleiche die Felder ab und bestätige sie.");
});

onForm("payroll-edit", (form) => {
  const wage = {
    document: wageEdit.document, transfer_ticket: formValue(form, "ticket"),
    period_end: formValue(form, "period"), tax_class: Number(formValue(form, "tax_class")), amounts: {},
    unsupported_positions: wageEdit.unsupported_positions ?? [],
  };
  if (formValue(form, "page")) wage.page = Number(formValue(form, "page"));
  if (!wage.period_end.startsWith("2025-")) throw new Error("Der Bescheinigungszeitraum muss 2025 enden.");
  for (const position of Object.keys(wagePositions)) {
    const input = formValue(form, "wage_" + position);
    if (input) wage.amounts[position] = decimal(input);
  }
  taxCase.wage_certificates = taxCase.wage_certificates.filter((item) => item.document !== wage.document);
  add("wage_certificates", wage);
  form.hidden = true;
  notify("Lohnsteuerbescheinigung übernommen.");
});

el("workday-import").elements.document.addEventListener("change", resetWorkdayImport);
onForm("workday-import", async (form) => {
  resetWorkdayImport();
  const id = formValue(form, "document");
  const file = originalFiles.get(id);
  if (!file) throw new Error("Wähle zuerst den Arbeitskalender aus.");
  const before = revision;
  const body = new FormData();
  body.append("file", file);
  body.append("document", id);
  const result = await request("workdays", {method: "POST", body});
  if (before !== revision || formValue(form, "document") !== id) return;
  if (result.sha256 !== taxCase.documents[id].sha256) throw new Error("Die CSV passt nicht zum Originalbeleg.");
  const existing = new Set((taxCase.workdays ?? []).map((entry) => entry.day));
  const duplicate = result.workdays.find((entry) => existing.has(entry.day));
  if (duplicate) throw new Error("Der Arbeitstag " + duplicate.day + " ist bereits erfasst.");
  workdayProposal = result.workdays;
  const attended = workdayProposal.filter((entry) => entry.attended_first_workplace).length;
  const atHome = workdayProposal.filter((entry) => entry.home_work === "predominantly").length;
  el("workday-import-counts").textContent = `${workdayProposal.length} Tage insgesamt · ${attended} mit Besuch der ersten Tätigkeitsstätte · ${atHome} überwiegend im Homeoffice`;
  el("workday-import-preview").hidden = false;
});
el("workday-import-original").addEventListener("click", () => {
  if (workdayProposal.length) viewOriginal(workdayProposal[0].sources[0].document);
});
el("workday-import-confirm").addEventListener("click", () => {
  if (!workdayProposal.length) return;
  const count = workdayProposal.length;
  (taxCase.workdays ??= []).push(...workdayProposal);
  changed();
  notify(count + " Arbeitstage übernommen.");
});

onForm("workday", (form) => {
  const day = formValue(form, "date");
  if (!day.startsWith("2025-")) throw new Error("Der Arbeitstag muss im Jahr 2025 liegen.");
  if (taxCase.workdays?.some((item) => item.day === day)) throw new Error("Erfasse jeden Arbeitstag einmal.");
  add("workdays", {day, attended_first_workplace: form.elements.attended.checked,
    home_work: formValue(form, "home"), permanently_without_other_workplace: form.elements.exception.checked,
    sources: [source(form)]});
  notify("Arbeitstag übernommen.");
});

onForm("commute", (form) => {
  const mode = formValue(form, "mode");
  taxCase.commute = {
    distance_km: decimal(formValue(form, "distance")), mode, source: source(form),
    public_transport_costs: mode === "public_transport" ? taxCase.commute?.public_transport_costs ?? [] : [],
  };
  changed();
  notify("Pendelstrecke übernommen.");
});

function updateExpenseReimbursement() {
  const form = el("expense");
  const eligible = formValue(form, "category").startsWith("expenses:");
  if (!eligible) form.elements.reimbursed.checked = false;
  el("expense-reimbursement-option").hidden = !eligible;
  const fields = el("expense-reimbursement-fields");
  fields.hidden = fields.disabled = !form.elements.reimbursed.checked;
}
el("expense-category").addEventListener("change", updateExpenseReimbursement);
el("expense").elements.reimbursed.addEventListener("change", updateExpenseReimbursement);
updateExpenseReimbursement();

onForm("expense", (form) => {
  const [collection, category] = formValue(form, "category").split(":");
  const paid_on = formValue(form, "date");
  if (!paid_on.startsWith("2025-")) throw new Error("Die Zahlung muss im Jahr 2025 liegen.");
  const item = {category, paid_on, amount: decimal(formValue(form, "amount")), source: source(form)};
  if (collection === "expenses") {
    item.description = formValue(form, "description");
    if (form.elements.reimbursed.checked) {
      const amount = decimal(formValue(form, "reimbursement_amount"));
      if (Number(amount) > Number(item.amount)) throw new Error("Die Erstattung darf die Ausgabe nicht übersteigen.");
      item.reimbursement = {
        amount, paid_on: formValue(form, "reimbursement_date"), source: source(form, "reimbursement_"),
      };
    }
  }
  if (collection === "donations") item.recipient = formValue(form, "description");
  add(collection, item);
  form.reset();
  updateExpenseReimbursement();
  notify("Ausgabe übernommen.");
});

onForm("asset", (form) => {
  const invoice = source(form);
  const usage = source(form, "usage_");
  const life = formValue(form, "life");
  const item = {
    description: formValue(form, "description"), acquired_on: formValue(form, "date"),
    amount: decimal(formValue(form, "amount")), source: invoice,
    vat: {amount: decimal(formValue(form, "vat")), source: invoice},
    professional_percent: decimal(formValue(form, "share")), usage_source: usage,
    asset_kind: formValue(form, "kind"), independently_usable: form.elements.independent.checked,
  };
  if (life) {
    item.useful_life_years = Number(life);
    item.useful_life_source = usage;
  }
  add("work_assets", item);
  notify("Arbeitsmittel übernommen.");
});

el("trip").elements.kind.addEventListener("change", (event) => {
  const minutes = el("trip").elements.minutes;
  minutes.disabled = event.target.value !== "day_trip";
  minutes.required = !minutes.disabled;
});
onForm("trip", (form) => {
  const day = formValue(form, "date");
  if (!day.startsWith("2025-")) throw new Error("Der Dienstreisetag muss im Jahr 2025 liegen.");
  if (taxCase.travel_days?.some((item) => item.day === day)) throw new Error("Erfasse die Verpflegungspauschale einmal pro Kalendertag.");
  const evidence = source(form);
  const kind = formValue(form, "kind");
  const meals = Object.keys(mealLabels).filter((meal) => form.elements[meal].checked).map((meal) => {
    const raw = formValue(form, meal + "_amount");
    return {kind: meal, source: evidence, own_payment: raw ? {amount: decimal(raw), source: evidence} : null};
  });
  const start = formValue(form, "start");
  const claim = {day, kind, source: evidence, employer_meals: meals};
  if (kind === "day_trip") claim.absent_minutes = Number(formValue(form, "minutes"));
  if (start) {
    claim.regularly_at_same_workplace_since = start;
    claim.assignment_source = evidence;
  }
  add("travel_days", claim);
  const mileageDate = el("trip-mileage").elements.date;
  if (!mileageDate.value) mileageDate.value = day;
  notify("Dienstreisetag übernommen.");
});

onForm("trip-mileage", (form) => {
  const evidence = source(form);
  const duplicate = taxCase.travel_mileage?.some(({source: entry}) => entry.document === evidence.document
    && (entry.page ?? null) === (evidence.page ?? null) && entry.locator === evidence.locator);
  if (duplicate) throw new Error("Diese Fundstelle ist bereits für Fahrtkilometer erfasst.");
  add("travel_mileage", {
    day: formValue(form, "date"), driven_km: decimal(formValue(form, "km")),
    vehicle: formValue(form, "vehicle"), source: evidence,
  });
  form.reset();
  notify("Fahrtkilometer übernommen.");
});

onForm("household", (form) => {
  const invoice = source(form);
  const paid_on = formValue(form, "date");
  if (!paid_on.startsWith("2025-")) throw new Error("Die Zahlung muss im Jahr 2025 liegen.");
  add("household_costs", {
    category: formValue(form, "kind"), description: formValue(form, "description"),
    paid_on, amount: decimal(formValue(form, "amount")), source: invoice,
    invoice_total: {amount: decimal(formValue(form, "invoice")), source: invoice},
    payment_source: source(form, "payment_"), payment_method: formValue(form, "method"),
    household_in_eu_eea: form.elements.eu.checked, publicly_funded: form.elements.funded.checked,
  });
  notify("Haushaltsnahe Leistung übernommen.");
});

onForm("profile", (form) => {
  const fields = ["first_name", "last_name", "date_of_birth", "occupation", "street", "house_number", "postcode", "city",
    "tax_id", "tax_number", "tax_office", "iban"];
  const taxpayer = Object.fromEntries(fields.map((key) => [key, formValue(form, key)]).filter((entry) => entry[1]));
  taxpayer.source = source(form);
  const church = formValue(form, "church");
  const [religion, region] = church.split(":");
  taxCase.filing = {
    ...(taxCase.filing ?? {}), taxpayer, case_facts: taxpayer.source,
    insurance: formValue(form, "insurance"), all_income_and_payments_reviewed: form.elements.reviewed.checked,
    church_tax_region: region ?? "none", religion_code: region ? religion : null,
  };
  changed();
  notify("Hauptvordruck übernommen.");
});

onForm("ask", async (form) => {
  const message = formValue(form, "message");
  const documentId = formValue(form, "document");
  const file = originalFiles.get(documentId);
  const withDocument = el("use-guide").checked && file && /\.(pdf|txt|csv)$/i.test(file.name);
  if (!message && !withDocument) return;
  const userMessage = message || "Bitte schau dir diesen Beleg an.";
  say(userMessage, "user");
  form.elements.message.value = "";
  const before = revision;
  el("candidate-controls").hidden = true;
  const progress = {
    history: chatHistory.slice(-6), originals: originalFiles.size, wages_confirmed: taxCase.wage_certificates.length,
    profile_confirmed: Boolean(taxCase.filing?.all_income_and_payments_reviewed),
    review_section: activeStage === "review" && draft ? walkthrough[walkIndex].title : null,
    review_blockers: draft?.review.findings.filter((entry) => entry.severity === "blocker").length ?? 0,
  };
  let result;
  if (withDocument) {
    const body = new FormData();
    body.append("file", file);
    body.append("document", documentId);
    body.append("stage", activeStage);
    body.append("message", message);
    body.append("progress_json", JSON.stringify(progress));
    if (/\.pdf$/i.test(file.name)) body.append("page", formValue(form, "page"));
    result = await request("document-guide", {method: "POST", body});
  } else {
    result = await request("guide", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({stage: activeStage, message, document: documentId || null,
        use_model: el("use-guide").checked, year: taxCase.tax_year, progress}),
    });
  }
  if (before !== revision) return;
  say(result.reply);
  chatHistory.push({role: "user", text: userMessage.slice(0, 1200)}, {role: "assistant", text: result.reply});
  if (chatHistory.length > 6) chatHistory.splice(0, chatHistory.length - 6);
  if (result.agent === "unavailable") say("Das lokale Modell war gerade nicht verfügbar.");
  if (result.candidate) {
    proposal = result.candidate;
    proposalVersion = before;
    const fact = proposal.facts;
    say(["Belegvorschlag", categories[proposal.collection]?.[fact.category] ?? fact.category,
      formatted({unit: "EUR", value: fact.amount}), fact.paid_on, fact.source.locator].join(" · "));
    el("candidate-controls").hidden = false;
  }
});
function updatePageOption() {
  const filename = taxCase.documents[el("chat-document").value]?.path ?? "";
  const visible = el("use-guide").checked && /\.pdf$/i.test(filename);
  el("chat-page-option").hidden = !visible;
  el("chat-page").hidden = !visible;
  el("chat-page").required = visible;
}
el("chat-document").addEventListener("change", updatePageOption);
el("use-guide").addEventListener("change", updatePageOption);
el("candidate-original").addEventListener("click", () => {
  if (proposalVersion !== revision) return;
  const reference = proposal.facts.source;
  viewOriginal(reference.document, reference.page, reference.locator);
});
el("accept-candidate").addEventListener("click", () => {
  if (proposal && proposalVersion === revision && originalFiles.has(proposal.facts.source.document)) {
    add(proposal.collection, proposal.facts);
    notify("Geprüfter Vorschlag übernommen.");
  }
  el("candidate-controls").hidden = true;
});
el("calculate").addEventListener("click", () => run(el("calculate"), async () => {
  if (!taxCase.wage_certificates.length) throw new Error("Bestätige zuerst mindestens eine Lohnsteuerbescheinigung.");
  const before = revision;
  const body = new FormData();
  body.append("case_json", JSON.stringify(taxCase));
  body.append("use_model", String(el("use-reviewer").checked));
  for (const [id, info] of Object.entries(taxCase.documents)) {
    if (!originalFiles.has(id)) throw new Error("Original fehlt · " + info.path);
    body.append("originals", originalFiles.get(id), id);
  }
  notify("Die Vorschau wird berechnet und geprüft.");
  const result = await request("preview", {method: "POST", body});
  if (before !== revision) throw new Error("Die Falldaten haben sich geändert. Berechne die Vorschau erneut.");
  notify("");
  renderReview(result);
}));
el("walk-next").addEventListener("click", () => { walkIndex += 1; renderWalk(); say(walkthrough[walkIndex].intro); });
el("walk-prev").addEventListener("click", () => { walkIndex -= 1; renderWalk(); });
el("findings-reviewed").addEventListener("change", updateReviewConfirmation);
el("review-confirm").addEventListener("click", () => {
  draft.user_reviewed = true;
  updateReviewConfirmation();
  say("Du hast alle Abschnitte durchgesehen. Der geprüfte Entwurf kann gespeichert werden.");
});
el("save-case").addEventListener("click", () => save("finamt-fall-2025.json", taxCase));
el("save-draft").addEventListener("click", () => { if (draft) save("finamt-pruefentwurf-2025.json", draft); });
el("apply-json").addEventListener("click", () => run(el("apply-json"), () => {
  loadCase(el("case-json").value);
  notify("Bearbeitete Angaben übernommen.");
}));
request("settings").then((data) => {
  el("model-option").hidden = !data.guide;
  el("use-guide").checked = data.guide;
  el("review-model-option").hidden = !data.reviewer;
  el("use-reviewer").checked = data.reviewer;
  el("model-hint").textContent = data.guide ? "" : "Geführte Erfassung aktiv.";
  updatePageOption();
}).catch(() => { el("model-hint").textContent = "Geführte Erfassung aktiv."; });
changed();
