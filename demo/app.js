const DATA_FILES = {
  snapshot: "data/openfda_snapshot.json",
  liveReceipt: "data/live_ingestion_receipt.json",
  mockBrief: "data/sample_account_brief.json",
};
const OPENFDA_ENDPOINT = "https://api.fda.gov/drug/enforcement.json";
const QUALITY_KEYWORDS = ["cgmp", "sterility", "contamination", "impurity", "foreign substance", "subpotent", "superpotent", "labeling"];
const state = { accounts: [], selectedName: null, provider: "salesforce" };

function parseOpenFdaDate(value) {
  if (!/^\d{8}$/.test(value || "")) return null;
  return new Date(`${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}T00:00:00Z`);
}

function isoDate(date) { return date ? date.toISOString().slice(0, 10) : null; }
function daysBetween(a, b) { return Math.max(Math.floor((b.getTime() - a.getTime()) / 86400000), 0); }

function recencyPoints(latest, asOf) {
  if (!latest) return 0;
  const age = daysBetween(latest, asOf);
  if (age <= 30) return 25;
  if (age <= 90) return 18;
  if (age <= 180) return 10;
  return 3;
}

function buildAccounts(records, asOf) {
  const grouped = new Map();
  records.forEach((record) => {
    const name = String(record.recalling_firm || "").trim();
    const recallNumber = String(record.recall_number || "").trim();
    if (!name || !recallNumber) return;
    const key = name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!grouped.has(key)) grouped.set(key, { name, records: [], state: record.state || "—" });
    grouped.get(key).records.push(record);
  });

  return [...grouped.values()].map((account) => {
    const latest = account.records.map((record) => parseOpenFdaDate(record.report_date)).filter(Boolean).sort((a, b) => b - a)[0] || null;
    const severityMap = { "Class I": 35, "Class II": 22, "Class III": 10 };
    const severity = Math.max(...account.records.map((record) => severityMap[record.classification] || 0));
    const recency = recencyPoints(latest, asOf);
    const distinctEvents = new Set(account.records.map((record) => String(record.event_id || record.recall_number))).size;
    const frequency = distinctEvents >= 5 ? 20 : distinctEvents >= 3 ? 14 : distinctEvents === 2 ? 8 : 4;
    const ongoing = account.records.some((record) => String(record.status || "").toLowerCase() === "ongoing") ? 10 : 0;
    const evidenceText = account.records.map((record) => String(record.reason_for_recall || "").toLowerCase()).join(" ");
    const matchedKeywords = QUALITY_KEYWORDS.filter((keyword) => evidenceText.includes(keyword));
    const quality = matchedKeywords.length ? 10 : 0;
    const score = Math.min(severity + recency + frequency + ongoing + quality, 100);
    const classifications = [...new Set(account.records.map((record) => record.classification).filter(Boolean))];
    const latestRecord = [...account.records].sort((a, b) => String(b.report_date).localeCompare(String(a.report_date)))[0];
    return { ...account, score, latest, latestRecord, classifications, breakdown: { severity, recency, frequency, ongoing, quality, distinctEvents } };
  }).sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}

function evidenceUrl(recallNumber) {
  return `${OPENFDA_ENDPOINT}?search=${encodeURIComponent(`recall_number:"${recallNumber}"`)}&limit=1`;
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function renderRows(query = "") {
  const normalized = query.toLowerCase().trim();
  const accounts = state.accounts.filter((account) => `${account.name} ${account.state} ${account.classifications.join(" ")}`.toLowerCase().includes(normalized));
  const rows = document.querySelector("#account-rows");
  rows.innerHTML = accounts.map((account) => `
    <tr tabindex="0" data-account="${escapeHtml(account.name)}" class="${account.name === state.selectedName ? "selected" : ""}">
      <td>${escapeHtml(account.name)}<br><small>${escapeHtml(account.state)}</small></td>
      <td class="score-cell">${account.score}</td><td>${account.records.length}</td>
      <td>${isoDate(account.latest) || "—"}</td><td>${escapeHtml(account.classifications.join(", ") || "—")}</td>
    </tr>`).join("");
  document.querySelector("#table-empty").hidden = accounts.length > 0;
  rows.querySelectorAll("tr").forEach((row) => {
    const select = () => selectAccount(row.dataset.account);
    row.addEventListener("click", select);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); }
    });
  });
}

function selectAccount(name) {
  const account = state.accounts.find((item) => item.name === name);
  if (!account) return;
  state.selectedName = account.name;
  document.querySelector("#detail-name").textContent = account.name;
  document.querySelector("#detail-score").textContent = account.score;
  document.querySelector("#detail-score-bar").style.width = `${account.score}%`;
  document.querySelector("#detail-evidence").textContent = account.latestRecord.reason_for_recall || "Reason not supplied";
  document.querySelector("#detail-source").href = evidenceUrl(account.latestRecord.recall_number);
  const labels = [["Severity", account.breakdown.severity], ["Recency", account.breakdown.recency], ["Frequency", account.breakdown.frequency], ["Ongoing", account.breakdown.ongoing], ["Quality", account.breakdown.quality], ["Events", account.breakdown.distinctEvents]];
  document.querySelector("#score-breakdown").innerHTML = labels.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("");
  renderRows(document.querySelector("#account-search").value);
  renderIntegrationPreview();
}

function integrationPayload(provider, account) {
  const externalKey = `openfda:${account.name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()}`;
  const common = { external_key: externalKey, account_name: account.name, gtm_score: account.score, score_policy: "openfda-v1", latest_signal_date: isoDate(account.latest), signal_count: account.records.length, source: "openfda", data_boundary: "real public signals; displayed brief is labelled mock" };
  if (provider === "salesforce") return { mode: "preview", would_write: false, payload: { Name: common.account_name, GTM_External_Key__c: common.external_key, GTM_Score__c: common.gtm_score, GTM_Score_Policy__c: common.score_policy, Latest_GTM_Signal_Date__c: common.latest_signal_date, GTM_Signal_Count__c: common.signal_count, GTM_Data_Boundary__c: common.data_boundary } };
  if (provider === "hubspot") return { mode: "preview", would_write: false, properties: { name: common.account_name, gtm_external_key: common.external_key, gtm_score: String(common.gtm_score), gtm_score_policy: common.score_policy, latest_gtm_signal_date: common.latest_signal_date, gtm_signal_count: String(common.signal_count), gtm_data_boundary: common.data_boundary } };
  return { mode: "preview", would_write: false, payload: common };
}

function renderIntegrationPreview() {
  const account = state.accounts.find((item) => item.name === state.selectedName);
  if (account) document.querySelector("#integration-json").textContent = JSON.stringify(integrationPayload(state.provider, account), null, 2);
}

function renderReceipt(receipt) {
  document.querySelector("#raw-records").textContent = receipt.raw_records_received;
  document.querySelector("#signals-persisted").textContent = receipt.signals_inserted + receipt.signals_updated;
  document.querySelector("#accounts-scored").textContent = receipt.scored_accounts_in_store;
  document.querySelector("#receipt-date").textContent = `Live ingestion run: ${new Date(receipt.run_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
}

function renderBrief(artifact) {
  const brief = artifact.output;
  document.querySelector("#brief-qualification").textContent = brief.qualification;
  document.querySelector("#brief-role").textContent = brief.role_target;
  document.querySelector("#brief-angle").textContent = brief.outreach_angle;
}

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

async function loadCommittedEvidence() {
  const [snapshot, receipt, mockBrief] = await Promise.all([loadJson(DATA_FILES.snapshot), loadJson(DATA_FILES.liveReceipt), loadJson(DATA_FILES.mockBrief)]);
  state.accounts = buildAccounts(snapshot.records, new Date(snapshot.fetched_at));
  state.selectedName = state.accounts[0]?.name || null;
  renderReceipt(receipt); renderBrief(mockBrief); renderRows();
  if (state.selectedName) selectAccount(state.selectedName);
}

async function refreshFromOpenFda() {
  const button = document.querySelector("#refresh-live");
  const note = document.querySelector("#refresh-note");
  button.disabled = true; note.classList.remove("error"); note.textContent = "Requesting the latest 25 public records from openFDA…";
  try {
    const response = await fetch(`${OPENFDA_ENDPOINT}?limit=25&sort=report_date:desc`);
    if (!response.ok) throw new Error(`openFDA returned HTTP ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload.results) || payload.results.length === 0) throw new Error("openFDA returned no result records");
    const validRecords = payload.results.filter((record) => String(record.recalling_firm || "").trim() && String(record.recall_number || "").trim());
    state.accounts = buildAccounts(validRecords, new Date()); state.selectedName = state.accounts[0]?.name || null;
    renderRows(document.querySelector("#account-search").value); if (state.selectedName) selectAccount(state.selectedName);
    document.querySelector("#raw-records").textContent = payload.results.length;
    document.querySelector("#signals-persisted").textContent = validRecords.length;
    document.querySelector("#accounts-scored").textContent = state.accounts.length;
    document.querySelector("#receipt-date").textContent = `Browser verification: ${new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
    note.textContent = `Verified ${payload.results.length} current public records in this browser; ${validRecords.length} passed identity checks. This read-only result was not persisted.`;
  } catch (error) {
    note.classList.add("error"); note.textContent = `${error.message}. The committed, reproducible evidence remains displayed.`;
  } finally { button.disabled = false; }
}

document.querySelector("#account-search").addEventListener("input", (event) => renderRows(event.target.value));
document.querySelector("#refresh-live").addEventListener("click", refreshFromOpenFda);
document.querySelectorAll(".provider-tab").forEach((tab) => tab.addEventListener("click", () => {
  state.provider = tab.dataset.provider;
  document.querySelectorAll(".provider-tab").forEach((item) => { const active = item === tab; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); });
  renderIntegrationPreview();
}));

loadCommittedEvidence().catch((error) => {
  const note = document.querySelector("#refresh-note"); note.classList.add("error");
  note.textContent = `${error.message}. Run the documented local preview command so the JSON evidence is staged with this page.`;
});
