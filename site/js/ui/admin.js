// Yönetim paneli (yalnızca yönetim parolasıyla girildiğinde): özet yazma, özetleri abonelere yayınlama,
// abone listesi ve kurulum durumu.
//
// Panel hiçbir şeyi doğrudan değiştirmez. Her işlem şifreli bir komuta çevrilir ve GitHub'daki günlük
// iş akışına yollanır (js/github.js); iş akışı komutu uygular, siteyi yeniden yayınlar. Bu yüzden bir
// işlemin sitede görünmesi birkaç dakika sürer; panel o sırada durumu izler ve bitince sayfayı yeniler.
import { adminInfo, loadBriefs, refreshAdminInfo, sealCommand } from "../data.js";
import { dayKey, esc, fmtDate } from "../format.js";
import { actionsUrl, dispatch, findRun, latestRunId } from "../github.js";
import { tt } from "../i18n.js";
import { icon } from "../icons.js";
import { copyText } from "../llmexport.js";
import { renderMarkdown } from "../md.js";
import { update } from "../state.js";
import { periodLabel, weekStart } from "./briefs.js";

const SECTIONS = ["write", "briefs", "subs", "status"];
const DRAFT_KEY = "qin.admin.draft";      // yarım kalan özet (bu cihazda)
const TEST_KEY = "qin.admin.test";        // deneme e-postasının gideceği adres
const PENDING_KEY = "qin.admin.pending";  // süren işlem (sayfa yenilense de izlenir)
const DONE_KEY = "qin.admin.done";        // az önce biten işlem (yenileme sonrası sonucu göstermek için)
const MAX_PAYLOAD = 60000;                // iş akışı girdisinin sınırı 65 535 karakter
const POLL_MS = 6000;
const START_WAIT = 3 * 60000;             // komuttan sonra çalışmanın listede görünmesi için beklenen süre
const PUBLISH_WAIT = 10 * 60000;          // çalışma bittikten sonra sonucun sitede görünmesi için beklenen süre

let root = null;
let section = "write";
let briefs = [];
let editing = null;       // düzenlenen özetin kimliği
let draft = null;         // { id, kind, date, title, body } — id: aynı taslağın iki kez eklenmesini önler
let confirming = null;    // onay bekleyen işlem ("send:12", "delete:12", "save-send", "unsub")
let pending = null;       // { id, label, phase, since, before, url, clearDraft, go }
let manual = null;        // { payload } — GitHub anahtarı yokken komut elle çalıştırılır
let notice = null;        // { ok, lines }
let picked = new Set();   // abone listesinde işaretli adresler
let sending = false;      // komut hazırlanırken ikinci tıklamayı yok say
let timer = 0;

const store = {
  get(area, key) { try { return JSON.parse(area.getItem(key)); } catch { return null; } },
  set(area, key, value) { try { value == null ? area.removeItem(key) : area.setItem(key, JSON.stringify(value)); } catch { /* yoksay */ } },
};
const randomId = () => [...crypto.getRandomValues(new Uint8Array(12))].map((b) => b.toString(16).padStart(2, "0")).join("");
const emptyDraft = () => ({ id: randomId(), kind: "weekly", date: dayKey(new Date()), title: "", body: "" });
const savedDraft = () => { const d = store.get(localStorage, DRAFT_KEY); return d ? { ...d, id: d.id ?? randomId() } : emptyDraft(); };
const mailOk = () => !!adminInfo()?.mail;
const subs = () => adminInfo()?.subscribers ?? [];

// ───────────── çizim ─────────────
function statusBar() {
  if (pending) {
    const secs = Math.floor((Date.now() - pending.since) / 1000);
    const clock = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
    return `
      <div class="adm-bar busy" role="status">
        <i class="spin"></i>
        <div><b>${esc(pending.label)}</b><span>${esc(tt(`admin.phase.${pending.phase}`))}</span></div>
        <span class="adm-clock">${clock}</span>
        ${pending.url ? `<a class="link" href="${esc(pending.url)}" target="_blank" rel="noopener noreferrer">${esc(tt("admin.run"))}</a>` : ""}
      </div>`;
  }
  const parts = [];
  if (notice) {
    parts.push(`
      <div class="adm-bar ${notice.ok ? "ok" : "bad"}" role="status">
        ${icon(notice.ok ? "check" : "close")}
        <div><b>${esc(tt(notice.ok ? "admin.done" : "admin.failed"))}</b>${notice.lines.filter(Boolean).map((l) => `<span>${esc(l)}</span>`).join("")}</div>
        <button type="button" class="ghost" data-act="dismiss">${esc(tt("admin.close"))}</button>
      </div>`);
  }
  if (manual) {
    parts.push(`
      <div class="adm-bar manual">
        <div><b>${esc(tt("admin.manual.title"))}</b><span>${esc(tt("admin.manual.text"))}</span></div>
        <textarea readonly rows="3" aria-label="${esc(tt("admin.manual.copy"))}">${esc(manual.payload)}</textarea>
        <div class="adm-actions">
          <button type="button" class="primary" data-act="copy-command">${icon("copy")}${esc(tt("admin.manual.copy"))}</button>
          ${adminInfo().repo ? `<a class="btn ghost" href="${esc(actionsUrl(adminInfo()))}" target="_blank" rel="noopener noreferrer">${esc(tt("admin.manual.open"))}</a>` : ""}
          ${notice ? "" : `<button type="button" class="ghost" data-act="dismiss">${esc(tt("admin.close"))}</button>`}
        </div>
      </div>`);
  }
  return parts.join("");
}

function confirmRow(key, text, yes) {
  return confirming === key ? `
    <span class="adm-confirm" role="alert">
      <span>${esc(text)}</span>
      <button type="button" class="danger" data-act="yes">${esc(yes)}</button>
      <button type="button" class="ghost" data-act="no">${esc(tt("admin.cancel"))}</button>
    </span>` : "";
}

function writeSection() {
  const d = draft;
  const canSend = mailOk() && subs().length > 0;
  const old = editing != null ? briefs.find((b) => b.id === editing) : null;
  return `
    <div class="adm-write">
      <form class="adm-form" data-form="brief" novalidate>
        ${old ? `<p class="adm-editing">${esc(tt("admin.editing", { t: old.t }))}</p>` : ""}
        <div class="adm-fields">
          <fieldset class="seg" ${old?.o === "llm" ? "disabled" : ""}>
            <legend class="sr-only">${esc(tt("admin.kind"))}</legend>
            ${["daily", "weekly"].map((k) => `<label><input type="radio" name="kind" value="${k}" ${d.kind === k ? "checked" : ""}><span>${esc(tt(`brief.kind.${k}`))}</span></label>`).join("")}
          </fieldset>
          <label class="adm-date">${esc(tt("admin.date"))}<input type="date" name="date" value="${esc(d.date)}" ${old?.o === "llm" ? "disabled" : ""} required></label>
        </div>
        <label>${esc(tt("admin.title"))}<input type="text" name="title" maxlength="200" value="${esc(d.title)}" autocomplete="off" required></label>
        <label>${esc(tt("admin.body"))}<textarea name="body" rows="16" spellcheck="false" required>${esc(d.body)}</textarea></label>
        <p class="adm-hint">${esc(tt("admin.body.hint"))}</p>
        <p class="adm-error" role="alert" data-error></p>
        <div class="adm-actions">
          <button type="submit" data-act="save">${esc(tt(old ? "admin.update" : "admin.save"))}</button>
          <button type="button" class="ghost" data-act="ask" data-key="save-send" ${canSend ? "" : "disabled"}
                  title="${esc(canSend ? "" : tt(mailOk() ? "admin.nosubs" : "admin.nomail"))}">${icon("mail")}${esc(tt("admin.save.send"))}</button>
          ${old ? `<button type="button" class="ghost" data-act="cancel-edit">${esc(tt("admin.cancel"))}</button>` : ""}
          ${confirmRow("save-send", tt("admin.confirm.send", { n: subs().length }), tt("admin.send.yes"))}
        </div>
      </form>
      <section class="adm-preview" aria-label="${esc(tt("admin.preview"))}">
        <h3>${esc(tt("admin.preview"))}</h3>
        <div class="reader"><h2 data-preview-title>${esc(d.title)}</h2><div class="prose" data-preview>${renderMarkdown(d.body)}</div></div>
      </section>
    </div>`;
}

function briefsSection() {
  if (!briefs.length) return `<p class="adm-empty">${esc(tt("brief.empty.admin"))}</p>`;
  const canSend = mailOk() && subs().length > 0;
  const rows = briefs.map((b) => {
    const sent = b.sent ? tt("admin.sent", { n: b.n, d: fmtDate(new Date(b.sent)) }) : tt("admin.notsent");
    return `
      <li class="adm-brief" data-id="${b.id}">
        <div class="adm-brief-main">
          <p class="brief-row-meta"><b class="k-${b.k}">${esc(tt(`brief.kind.${b.k}`))}</b>${esc(periodLabel(b))}
            <span>${esc(tt(`brief.origin.${b.o}`, null, b.o))}</span>
            <span class="${b.sent ? "is-sent" : ""}">${b.sent ? icon("check") : ""}${esc(sent)}</span></p>
          <h3>${esc(b.t)}</h3>
        </div>
        <div class="adm-brief-acts">
          <button type="button" class="ghost" data-act="view">${esc(tt("admin.view"))}</button>
          <button type="button" class="ghost" data-act="edit">${icon("edit")}${esc(tt("admin.edit"))}</button>
          <button type="button" class="ghost" data-act="test" ${mailOk() ? "" : "disabled"} title="${esc(mailOk() ? tt("admin.test.hint") : tt("admin.nomail"))}">${esc(tt("admin.test"))}</button>
          <button type="button" class="${b.sent ? "ghost" : "primary"}" data-act="ask" data-key="send:${b.id}" ${canSend ? "" : "disabled"}
                  title="${esc(canSend ? "" : tt(mailOk() ? "admin.nosubs" : "admin.nomail"))}">${icon("mail")}${esc(tt(b.sent ? "admin.resend" : "admin.publish"))}</button>
          <button type="button" class="ghost icon" data-act="ask" data-key="delete:${b.id}" aria-label="${esc(tt("admin.delete"))}" title="${esc(tt("admin.delete"))}">${icon("trash")}</button>
        </div>
        ${confirmRow(`send:${b.id}`, tt("admin.confirm.send", { n: subs().length }), tt("admin.send.yes"))}
        ${confirmRow(`delete:${b.id}`, tt("admin.confirm.delete"), tt("admin.delete"))}
      </li>`;
  }).join("");
  return `
    ${canSend ? "" : `<p class="adm-warn">${esc(tt(mailOk() ? "admin.nosubs" : "admin.nomail"))}</p>`}
    <ul class="adm-briefs">${rows}</ul>`;
}

function subsSection() {
  const list = subs();
  return `
    ${adminInfo().locked ? `<p class="adm-warn">${esc(tt("admin.subs.locked"))}</p>` : ""}
    <div class="adm-subs">
      <form class="adm-form" data-form="subs" novalidate>
        <label>${esc(tt("admin.subs.add"))}<textarea name="emails" rows="4" spellcheck="false" placeholder="ad@ornek.com"></textarea></label>
        <p class="adm-hint">${esc(tt("admin.subs.hint"))}</p>
        <p class="adm-error" role="alert" data-error></p>
        <div class="adm-actions"><button type="submit">${esc(tt("admin.subs.addbtn"))}</button></div>
        <label class="adm-test">${esc(tt("admin.test.address"))}<input type="email" name="test" value="${esc(store.get(localStorage, TEST_KEY) ?? "")}" placeholder="sen@ornek.com" autocomplete="email"></label>
        <p class="adm-hint">${esc(tt("admin.test.note"))}</p>
      </form>
      <section>
        <h3>${esc(tt("admin.subs.count", { n: list.length }))}</h3>
        ${list.length ? `
        <ul class="adm-sublist">${list.map((e) => `<li><label><input type="checkbox" name="sub" value="${esc(e)}" ${picked.has(e) ? "checked" : ""}><span>${esc(e)}</span></label></li>`).join("")}</ul>
        <div class="adm-actions">
          <button type="button" class="ghost" data-act="ask" data-key="unsub">${icon("trash")}${esc(tt("admin.subs.remove"))}</button>
          ${confirmRow("unsub", tt("admin.confirm.unsub"), tt("admin.subs.remove"))}
        </div>` : `<p class="adm-empty">${esc(tt("admin.subs.none"))}</p>`}
      </section>
    </div>`;
}

function statusSection() {
  const info = adminInfo();
  const line = (ok, title, text) => `
    <li class="${ok ? "ok" : "off"}"><i class="lamp ${ok ? "ok" : "warn"}"></i><div><b>${esc(title)}</b><span>${esc(text)}</span></div></li>`;
  const llm = info.llm ?? {};
  const last = llm.last;
  return `
    <ul class="adm-checks">
      ${line(!!(info.token && info.repo), tt("admin.st.github"), info.token && info.repo ? tt("admin.st.github.ok", { repo: info.repo }) : tt("admin.st.github.off"))}
      ${line(!!info.mail, tt("admin.st.mail"), tt(info.mail ? "admin.st.mail.ok" : "admin.st.mail.off"))}
      ${line(!!llm.providers?.length, tt("admin.st.llm"), llm.providers?.length ? tt("admin.st.llm.ok", { list: llm.providers.join(", ") }) : tt("admin.st.llm.off"))}
    </ul>
    ${last ? `
    <section class="adm-log">
      <h3>${esc(tt("admin.st.llm.last", { d: new Date(last.at).toLocaleString() }))}</h3>
      <ul>${[...(last.lines ?? []), ...(last.errors ?? [])].map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    </section>` : ""}
    ${info.last ? `
    <section class="adm-log">
      <h3>${esc(tt("admin.st.last", { d: new Date(info.last.at).toLocaleString() }))}</h3>
      <ul>${info.last.log.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    </section>` : ""}
    <p class="adm-hint">${esc(tt("admin.st.note"))}</p>`;
}

function draw() {
  if (!root) return;
  const body = { write: writeSection, briefs: briefsSection, subs: subsSection, status: statusSection }[section]();
  root.classList.toggle("is-busy", !!pending);
  root.innerHTML = `
    <div class="adm-sheet" role="dialog" aria-modal="true" aria-labelledby="adm-h">
      <header class="adm-head">
        <h2 id="adm-h">${icon("admin")}${esc(tt("admin.heading"))}</h2>
        <nav class="adm-nav" aria-label="${esc(tt("admin.heading"))}">
          ${SECTIONS.map((s) => `<button type="button" data-section="${s}" aria-current="${s === section}">${esc(tt(`admin.nav.${s}`))}${s === "briefs" ? `<span>${briefs.length}</span>` : s === "subs" ? `<span>${subs().length}</span>` : ""}</button>`).join("")}
        </nav>
        <button type="button" class="adm-x" data-act="close" aria-label="${esc(tt("admin.close"))}">${icon("close")}</button>
      </header>
      <div class="adm-status" data-status>${statusBar()}</div>
      <div class="adm-body" ${pending ? "inert" : ""}>${body}</div>
    </div>`;
}

const drawStatus = () => { const el = root?.querySelector("[data-status]"); if (el) el.innerHTML = statusBar(); };

// ───────────── komut gönderme ve izleme ─────────────
// clearDraft: başarılı olursa kayıtlı taslak silinir. go: başarılı olursa panelin açılacağı bölüm.
async function run(ops, label, { clearDraft = false, go = null } = {}) {
  if (pending || sending) return;
  sending = true;
  const info = adminInfo();
  const id = randomId();
  let payload;
  try { payload = await sealCommand({ id, ts: new Date().toISOString(), ops }); } finally { sending = false; }
  confirming = null; notice = null; manual = null;
  if (payload.length > MAX_PAYLOAD) { notice = { ok: false, lines: [tt("admin.err.long")] }; return draw(); }
  if (!info.token || !info.repo) { manual = { payload }; return draw(); }

  pending = { id, label, phase: "send", since: Date.now(), before: 0, url: null, clearDraft, go };
  draw();
  try {
    pending.before = await latestRunId(info);
    await dispatch(info, payload);
  } catch (err) {                                       // anahtar geçersiz, ağ yok...: komut elle de çalıştırılabilir
    const key = { 401: "admin.err.401", 403: "admin.err.403", 404: "admin.err.404", 422: "admin.err.422" }[err.status] ?? "admin.err.net";
    pending = null;
    manual = { payload };
    notice = { ok: false, lines: [tt(key), err.status ? err.message : ""] };
    return draw();
  }
  pending.phase = "queued";
  store.set(sessionStorage, PENDING_KEY, pending);
  drawStatus();
  watch();
}

function watch() {
  clearInterval(timer);
  let last = 0;
  timer = setInterval(async () => {
    if (!pending) return clearInterval(timer);
    drawStatus();                                         // saat her saniye ilerler
    if (Date.now() - last < POLL_MS) return;
    last = Date.now();
    try {
      if (pending.phase !== "publish") {
        const found = await findRun(adminInfo(), pending.before);
        if (!pending) return;
        if (!found) {
          if (Date.now() - pending.since > START_WAIT) finish({ ok: false, lines: [tt("admin.err.norun"), tt("admin.err.maybe")] });
          return;
        }
        pending.url = found.url;
        if (found.status !== "completed") pending.phase = found.status === "in_progress" ? "running" : "queued";
        else if (found.conclusion === "success") { pending.phase = "publish"; pending.publishSince = Date.now(); }
        else return finish({ ok: false, lines: [tt("admin.err.run", { c: found.conclusion ?? "?" }), tt("admin.err.maybe")] });
        store.set(sessionStorage, PENDING_KEY, pending);
      } else {                                            // çalışma bitti: yeni veri yayına girdi mi?
        const info = await refreshAdminInfo();
        if (!pending) return;
        if (info?.last?.id === pending.id && !info.last.ok) {
          // Uygulanamadı: sayfa yenilenmez, yazılan metin yerinde kalır.
          finish({ ok: false, lines: [...info.last.log, tt("admin.err.partial")] });
        } else if (info?.last?.id === pending.id) {
          if (pending.clearDraft) store.set(localStorage, DRAFT_KEY, null);
          store.set(sessionStorage, DONE_KEY, { id: pending.id, section: pending.go ?? section });
          store.set(sessionStorage, PENDING_KEY, null);
          location.reload();                              // özet listesi ve site verisi baştan yüklensin
        } else if (Date.now() - (pending.publishSince ?? pending.since) > PUBLISH_WAIT) {
          finish({ ok: false, lines: [tt("admin.err.stale"), tt("admin.err.maybe")] });
        }
      }
    } catch { /* geçici ağ hatası: bir sonraki turda yeniden denenir */ }
  }, 1000);
}

function finish(result) {
  clearInterval(timer);
  const url = pending?.url;
  pending = null;
  store.set(sessionStorage, PENDING_KEY, null);
  notice = { ...result, lines: url ? [...result.lines, url] : result.lines };
  draw();
}

// ───────────── form işlemleri ─────────────
function readDraft(form) {
  const kind = form.elements.kind.value || draft.kind;
  draft = { id: draft.id, kind, date: form.elements.date.value || draft.date, title: form.elements.title.value, body: form.elements.body.value };
  if (editing == null) store.set(localStorage, DRAFT_KEY, draft);
}

function saveOp() {
  return { op: "brief.save", id: editing, draft: editing == null ? draft.id : null, kind: draft.kind, date: draft.date,
           title: draft.title.trim(), body: draft.body.trim() };
}

function validDraft() {
  const err = root.querySelector('[data-form="brief"] [data-error]');
  const missing = !draft.title.trim() ? "admin.err.title" : !draft.body.trim() ? "admin.err.body" : !/^\d{4}-\d{2}-\d{2}$/.test(draft.date) ? "admin.err.date" : null;
  err.textContent = missing ? tt(missing) : "";
  return !missing;
}

function parseEmails(text) {
  const all = text.split(/[\s,;]+/).map((e) => e.trim().toLowerCase()).filter(Boolean);
  const bad = all.filter((e) => !/^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(e));
  return { good: [...new Set(all.filter((e) => !bad.includes(e)))], bad };
}

function confirmed(key) {
  if (!key) return;
  if (key === "save-send") {
    readDraft(root.querySelector('[data-form="brief"]'));
    confirming = null;
    if (!validDraft()) { draw(); validDraft(); return; }      // onay kutusu kapanır, hata iletisi görünür
    return run([saveOp(), { op: "brief.send", id: "last", to: "all" }], tt("admin.label.savesend"), { clearDraft: editing == null, go: "briefs" });
  }
  if (key === "unsub") {
    const emails = [...picked];
    picked = new Set();
    return run([{ op: "sub.remove", emails }], tt("admin.label.unsub", { n: emails.length }));
  }
  const [what, id] = key.split(":");
  const brief = briefs.find((b) => b.id === +id);
  // again: daha önce gönderilmiş özetin bilerek yeniden yayınlanması (sunucu aksi halde ikinci gönderimi reddeder)
  if (what === "send") return run([{ op: "brief.send", id: +id, to: "all", again: !!brief?.sent }], tt("admin.label.send", { t: brief?.t ?? id }));
  if (what === "delete") return run([{ op: "brief.delete", id: +id }], tt("admin.label.delete", { t: brief?.t ?? id }));
}

function onClick(e) {
  if (e.target === root) return close();
  const nav = e.target.closest("[data-section]");
  if (nav) { section = nav.dataset.section; confirming = null; return draw(); }
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const act = btn.dataset.act;
  const id = +btn.closest("[data-id]")?.dataset.id;
  if (act === "close") return close();
  if (act === "dismiss") { notice = null; manual = null; return draw(); }
  if (act === "copy-command") { copyText(manual.payload).then((ok) => { btn.lastChild.textContent = tt(ok ? "export.copied" : "export.failed"); }); return; }
  if (act === "no") { confirming = null; return draw(); }
  if (act === "yes") return confirmed(confirming);
  if (act === "ask") {
    if (btn.dataset.key === "save-send") readDraft(root.querySelector('[data-form="brief"]'));
    if (btn.dataset.key === "unsub" && !picked.size) return;
    confirming = btn.dataset.key;
    return draw();
  }
  if (act === "cancel-edit") { editing = null; draft = savedDraft(); return draw(); }
  if (act === "view") { close(); return update({ tab: "briefs", brief: id }); }
  if (act === "edit") {
    const b = briefs.find((x) => x.id === id);
    editing = id; section = "write"; confirming = null;
    // Tarih özetin döneminden gelir (haftalıkta o haftanın pazartesisi); düzenleme dönemi değiştirmesin.
    draft = { id: null, kind: b.k, date: b.k === "daily" ? b.per : dayKey(weekStart(b.per)), title: b.t, body: b.b };
    return draw();
  }
  if (act === "test") {
    const to = store.get(localStorage, TEST_KEY);
    if (!to) { section = "subs"; draw(); root.querySelector('input[name="test"]').focus(); return; }
    return run([{ op: "brief.send", id, to: [to] }], tt("admin.label.test", { to }));
  }
}

function onSubmit(e) {
  e.preventDefault();
  const form = e.target;
  if (form.dataset.form === "brief") {
    readDraft(form);
    if (validDraft()) run([saveOp()], tt(editing == null ? "admin.label.save" : "admin.label.update"), { clearDraft: editing == null, go: "briefs" });
    return;
  }
  const { good, bad } = parseEmails(form.elements.emails.value);
  const err = form.querySelector("[data-error]");
  if (bad.length) { err.textContent = tt("admin.err.email", { list: bad.join(", ") }); return; }
  if (!good.length) { err.textContent = tt("admin.err.noemail"); return; }
  run([{ op: "sub.add", emails: good }], tt("admin.label.sub", { n: good.length }));
}

let previewTimer = 0;
function onInput(e) {
  if (e.target.name === "sub") { e.target.checked ? picked.add(e.target.value) : picked.delete(e.target.value); return; }
  const form = e.target.closest("form");
  if (!form) return;
  if (!form.dataset.form) return;
  if (form.dataset.form === "subs") {
    if (e.target.name === "test") store.set(localStorage, TEST_KEY, e.target.value.trim().toLowerCase() || null);
    return;
  }
  // Yapıştırılan metin "# Başlık" ile başlıyorsa başlık kendi kutusuna alınır.
  const body = form.elements.body;
  const head = /^\s*#\s+(.+)\n/.exec(body.value);
  if (e.target === body && head && !form.elements.title.value.trim()) {
    form.elements.title.value = head[1].replace(/[*_`]/g, "").trim();
    body.value = body.value.slice(head[0].length).replace(/^\s+/, "");
  }
  readDraft(form);
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    const view = root?.querySelector("[data-preview]");
    if (!view) return;
    view.innerHTML = renderMarkdown(draft.body);
    root.querySelector("[data-preview-title]").textContent = draft.title;
  }, 150);
}

function onKey(e) {
  if (e.key === "Escape" && root) { if (confirming) { confirming = null; draw(); } else close(); }
  // Tek satırlık kutuda Enter formu göndermesin: her gönderim birkaç dakikalık bir işlem başlatır.
  if (e.key === "Enter" && e.target.matches?.(".adm input:not([type=checkbox]):not([type=radio])")) e.preventDefault();
}

// ───────────── açma / kapama ─────────────
export async function openAdmin(startSection) {
  if (!adminInfo() || root) return;
  section = SECTIONS.includes(startSection) ? startSection : section;
  draft ??= savedDraft();
  root = document.createElement("div");
  root.className = "adm";
  document.body.append(root);
  document.body.classList.add("adm-open");
  root.addEventListener("click", onClick);
  root.addEventListener("submit", onSubmit);
  root.addEventListener("input", onInput);
  root.addEventListener("change", onInput);
  document.addEventListener("keydown", onKey);
  draw();
  try { briefs = await loadBriefs(); } catch { briefs = []; }
  if (root) draw();
  if (pending) watch();
}

function close() {
  clearInterval(timer);
  document.removeEventListener("keydown", onKey);
  document.body.classList.remove("adm-open");
  root?.remove();
  root = null;
  confirming = null;
}

// Sayfa açılışında: süren bir işlem varsa izlemeye devam eder, az önce biten işlemin sonucunu gösterir.
export function resumeAdmin() {
  const done = store.get(sessionStorage, DONE_KEY);
  const saved = store.get(sessionStorage, PENDING_KEY);
  if (done) {
    store.set(sessionStorage, DONE_KEY, null);
    const last = adminInfo().last;
    if (last?.id === done.id) notice = { ok: last.ok, lines: last.log };
    draft = savedDraft();
    return openAdmin(done.section);
  }
  if (saved) { pending = saved; return openAdmin(); }
}
