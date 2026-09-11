"use strict";

const lastEl = document.getElementById("last");
const subEl = document.getElementById("sub");
const cardsEl = document.getElementById("cards");
const histEl = document.getElementById("history");

function level(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("divert")) return "bad";
  if (s.includes("limited")) return "warn";
  if (s === "normal") return "ok";
  return "unk";
}

function fmtIso(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  return d.toLocaleString();
}

function render(snap) {
  const hospitals = snap.hospitals || {};
  const names = Object.keys(hospitals);
  subEl.textContent = names.length ? `${names.length} hospitals tracked` : "";
  lastEl.textContent = snap.last_received ? "Updated " + fmtIso(snap.last_received) : "No data yet";

  cardsEl.innerHTML = "";
  if (!names.length) {
    cardsEl.innerHTML = '<div class="empty">Waiting for the first status email.</div>';
    return;
  }
  for (const name of names) {
    const st = hospitals[name];
    const status = (st && st.status) || "Unknown";
    const cls = level(status);
    const card = document.createElement("div");
    card.className = "card " + cls;
    card.innerHTML = `
      <div class="name">${escapeHtml(name)}</div>
      <div class="status"><span class="badge">●</span> ${escapeHtml(status)}</div>
      <div class="seen">As of ${fmtIso(st.seen_at)}</div>`;
    cardsEl.appendChild(card);
  }
}

function renderHistory(events) {
  histEl.innerHTML = "";
  for (const e of events.slice().reverse()) {
    const cls = level(e.new_status);
    const li = document.createElement("li");
    li.className = cls;
    li.innerHTML = `
      <span class="when">${fmtIso(e.ts)}</span>
      <span class="hosp">${escapeHtml(e.hospital)}</span>
      <span class="arrow">${escapeHtml(e.old_status)} → <span class="new">${escapeHtml(e.new_status)}</span></span>`;
    histEl.appendChild(li);
  }
  if (!events.length) {
    histEl.innerHTML = '<li class="when">No changes recorded yet.</li>';
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function refresh() {
  try {
    const snap = await (await fetch("/api/snapshot", { cache: "no-store" })).json();
    if (snap.error) throw new Error(snap.error);
    render(snap);
  } catch (e) {
    cardsEl.innerHTML = `<div class="empty">${escapeHtml(e.message || e)}</div>`;
  }
  try {
    const hist = await (await fetch("/api/history", { cache: "no-store" })).json();
    if (Array.isArray(hist)) renderHistory(hist);
  } catch (e) { /* history is best-effort */ }
}

refresh();
setInterval(refresh, 60000);