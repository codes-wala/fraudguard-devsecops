"use strict";
const $ = id => document.getElementById(id);
const VERDICTS = ["APPROVE", "REVIEW", "BLOCK", "REJECTED"];
let count = 0;

const presets = {
  normal: {amount: 1500, hour: 14, txn_last_hour: 1, account_age_days: 400, recent_amounts: "", is_foreign: 0, is_new_device: 0, is_blacklisted_merchant: 0},
  foreign: {amount: 85000, hour: 2, txn_last_hour: 2, account_age_days: 200, recent_amounts: "", is_foreign: 1, is_new_device: 1, is_blacklisted_merchant: 0},
  structuring: {amount: 20000, hour: 11, txn_last_hour: 3, account_age_days: 90, recent_amounts: "46000, 47500, 49000", is_foreign: 0, is_new_device: 0, is_blacklisted_merchant: 0},
  blacklist: {amount: 900, hour: 16, txn_last_hour: 1, account_age_days: 800, recent_amounts: "", is_foreign: 0, is_new_device: 0, is_blacklisted_merchant: 1},
  invalid: {amount: -50, hour: 27, txn_last_hour: 1, account_age_days: 100, recent_amounts: "", is_foreign: 0, is_new_device: 0, is_blacklisted_merchant: 0}
};

function make(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;   // textContent: never parsed as HTML
  return e;
}

function preset(name) {
  const p = presets[name];
  for (const f of ["amount", "hour", "txn_last_hour", "account_age_days", "recent_amounts"]) $(f).value = p[f];
  for (const f of ["is_foreign", "is_new_device", "is_blacklisted_merchant"]) $(f).checked = !!p[f];
}

function showError(message) {
  const box = $("result");
  box.replaceChildren(make("div", "err", message));
}

function showDecision(d) {
  const verdict = VERDICTS.includes(d.verdict) ? d.verdict : "REJECTED";
  const ml = d.ml_score === null ? "n/a" : Number(d.ml_score).toFixed(3);
  const pct = d.ml_score === null ? 0 : Math.round(d.ml_score * 100);
  const meter = make("div", "meter");
  const bar = document.createElement("div");
  bar.style.width = pct + "%";                    // CSSOM is allowed by a strict CSP
  meter.appendChild(bar);
  const list = make("ul");
  for (const r of d.reasons) list.appendChild(make("li", "", r));
  $("result").replaceChildren(
    make("span", "badge " + verdict, verdict),
    make("div", "sub gap", "ML fraud probability: " + ml + " · Rule risk points: " + d.risk_points),
    meter, list);
  return {verdict, ml};
}

function logRow(body, verdict, risk, ml) {
  count += 1;
  const tr = document.createElement("tr");
  const cells = [String(count), "₹" + body.amount, String(body.hour), String(body.txn_last_hour)];
  for (const c of cells) tr.appendChild(make("td", "", c));
  const td = document.createElement("td");
  td.appendChild(make("span", "badge small " + verdict, verdict));
  tr.appendChild(td);
  tr.appendChild(make("td", "", String(risk)));
  tr.appendChild(make("td", "", ml));
  $("log").prepend(tr);
}

async function assess() {
  const recent = $("recent_amounts").value.split(",").map(s => s.trim()).filter(Boolean).map(Number);
  const body = {
    amount: $("amount").value, hour: $("hour").value, txn_last_hour: $("txn_last_hour").value,
    account_age_days: $("account_age_days").value, recent_amounts: recent,
    is_foreign: $("is_foreign").checked, is_new_device: $("is_new_device").checked,
    is_blacklisted_merchant: $("is_blacklisted_merchant").checked
  };
  let response, d;
  try {
    response = await fetch("/api/assess", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    d = await response.json();
  } catch (e) {
    showError("Could not reach the server.");
    return;
  }
  if (!response.ok) { showError(d.error || "Request failed."); return; }
  const shown = showDecision(d);
  logRow(body, shown.verdict, d.risk_points, shown.ml);
}

document.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () => preset(b.dataset.preset)));
$("assess-btn").addEventListener("click", assess);
