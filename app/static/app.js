"use strict";
const $ = (id) => document.getElementById(id);
const S = { engines: [], engine: null, voice: {}, session: null, job: null, episodes: [], label: "script",
            peaks: null, lastCloud: 0, cloudGap: 3, playing: null, params: {}, prof: null, cmp: [] };

async function api(path, opts = {}) {
  const o = { method: opts.method || (opts.body ? "POST" : "GET"), headers: {} };
  if (opts.body) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opts.body); }
  let r;
  try { r = await fetch(path, o); }
  catch (e) { throw new Error("Voice Studio is not running. Start it again from the Desktop shortcut, then reload this page."); }
  let data = null;
  try { data = await r.json(); } catch (e) { /* no body */ }
  if (!r.ok) throw new Error((data && data.detail) || `Error ${r.status}`);
  return data;
}
function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* fine */ } } };
const fmt = (s) => { s = Math.max(0, s || 0); return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; };
function showError(msg) { const e = $("formError"); e.textContent = msg || ""; e.hidden = !msg; }

/* ---------- theme ---------- */
function setTheme(t) { document.documentElement.dataset.theme = t; store.set("vs-theme", t); drawWave(); }
$("themeBtn").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");

/* ---------- engines and voices ---------- */
function currentEngine() { return S.engines.find((e) => e.id === S.engine); }
const STATE_TEXT = { ready: "Ready. ", loading: "", idle: "", missing: "", unconfigured: "", error: "Problem: " };
function activate(id) { return api(`/api/engines/${id}/activate`, { method: "POST" }).then(() => refresh()).catch(() => {}); }
function renderEngines() {
  const box = $("engines"); box.replaceChildren();
  for (const e of S.engines) {
    const radio = el("input", { type: "radio", name: "engine", value: e.id });
    radio.checked = e.id === S.engine;
    const row = el("label", { class: "engine" + (e.id === S.engine ? " sel" : "") }, radio,
      el("span", { class: "name", text: e.name }),
      el("span", { class: "badge " + (e.kind === "cloud" ? "cloud" : "local"), text: e.badge }),
      el("span", { class: "st" + (e.status.state === "error" || e.status.state === "missing" ? " bad" : ""),
                   text: (STATE_TEXT[e.status.state] || "") + (e.status.detail || "") }));
    radio.onchange = () => { S.engine = e.id; store.set("vs-engine", e.id); renderEngines(); renderVoices(); renderParams(); syncControls();
      if (e.kind === "local" && ["idle", "error"].includes(e.status.state)) activate(e.id); };
    box.append(row);
  }
  const cur = currentEngine(), pill = $("enginePill");
  if (cur) {
    const st = cur.status.state;
    pill.textContent = `${cur.name}: ${st === "ready" ? cur.status.detail || "ready" : st === "loading" ? "Loading engine..." : st === "idle" ? "not loaded" : st === "missing" ? "not installed" : st === "unconfigured" ? "needs a key" : "problem"}`;
    pill.className = "pill " + (st === "ready" ? "ok" : st === "error" || st === "missing" ? "bad" : "");
  }
}
function renderVoices() {
  const e = currentEngine(), box = $("voices"); box.replaceChildren();
  if (!e) return;
  const ids = e.voices.map((v) => v.id);
  const saved = S.voice[e.id] || store.get("vs-voice-" + e.id);
  S.voice[e.id] = ids.includes(saved) ? saved : ids[0];
  for (const v of e.voices) {
    box.append(el("button", { class: "voice" + (S.voice[e.id] === v.id ? " sel" : ""), type: "button",
      onclick: () => { S.voice[e.id] = v.id; store.set("vs-voice-" + e.id, v.id); renderVoices(); } },
      document.createTextNode(v.label), el("small", { text: v.note || "" })));
  }
  $("noProfiles").hidden = !(e.uses_profiles && !ids.some((i) => i.startsWith("p:")));
}
function paramValues(e) {
  if (!S.params[e.id]) { try { S.params[e.id] = JSON.parse(store.get("vs-params-" + e.id) || "{}"); } catch (x) { S.params[e.id] = {}; } }
  const out = {};
  for (const p of e.params) out[p.id] = S.params[e.id][p.id] != null ? S.params[e.id][p.id] : p.default;
  return out;
}
function setParam(e, id, v) { paramValues(e); S.params[e.id][id] = v; store.set("vs-params-" + e.id, JSON.stringify(S.params[e.id])); }
function renderParams() {
  const e = currentEngine(), list = $("paramList"); list.replaceChildren();
  $("params").hidden = !e || !e.params.length;
  if (!e) return;
  const vals = paramValues(e);
  $("paramsReset").hidden = !e.params.some((p) => p.type === "range");
  for (const p of e.params) {
    if (p.type === "range") {
      const out = el("output", { text: (+vals[p.id]).toFixed(2) });
      const inp = el("input", { type: "range", min: p.min, max: p.max, step: p.step, value: vals[p.id], "aria-label": p.label });
      inp.oninput = () => { out.textContent = (+inp.value).toFixed(2); setParam(e, p.id, +inp.value); };
      list.append(el("div", { class: "slider" }, el("div", { class: "label" }, el("span", { text: p.label }), out), inp,
        p.hint ? el("p", { class: "hint", text: p.hint }) : null));
    } else {
      const sel = el("select", { "aria-label": p.label });
      for (const o of p.options) sel.append(el("option", { value: o.id, text: o.label }));
      sel.value = vals[p.id]; sel.onchange = () => { setParam(e, p.id, sel.value); renderCompare(); };
      list.append(el("div", { class: "slider" }, el("div", { class: "label" }, el("span", { text: p.label })), sel));
    }
  }
}
$("paramsReset").onclick = () => { const e = currentEngine(); if (!e) return;
  for (const p of e.params) if (p.type === "range") setParam(e, p.id, p.default); renderParams(); };
$("noProfilesBtn").onclick = () => openProfiles();
function syncControls() {
  const e = currentEngine(); if (!e) return;
  const cloud = e.kind === "cloud";
  $("rateNote").textContent = e.rate_note || "";
  $("gapWrap").hidden = cloud;
  const note = $("cloudNote"); note.hidden = !cloud;
  note.textContent = cloud ? `Cloud safety rules: one request per click, no retries, at least ${S.cloudGap} seconds between requests, and a voice-safe check before sending.` : "";
  const usable = !["missing", "unconfigured"].includes(e.status.state);
  $("genBtn").disabled = $("previewBtn").disabled = $("cmpBtn").disabled = !usable || !!S.job;
  $("cmpBtn").disabled = !!S.job;
  runCheck();
}
for (const [id, out, unit] of [["rate", "rateOut", "%"], ["pause", "pauseOut", " ms"], ["gap", "gapOut", " ms"]]) {
  $(id).oninput = () => { $(out).textContent = (id === "rate" ? Math.round($(id).value * 100) : $(id).value) + unit; };
}

/* ---------- script input ---------- */
$("openBtn").onclick = () => $("fileIn").click();
$("clearBtn").onclick = () => { $("script").value = ""; S.episodes = []; S.label = "script"; $("episodeSel").hidden = true; runCheck(); };
function parseEpisodes(md) {
  const heads = [...md.matchAll(/^## (EP\d+) \|[ \t]*(.*?)[ \t]*$/gm)], eps = [];
  heads.forEach((h, i) => {
    const body = md.slice(h.index + h[0].length, i + 1 < heads.length ? heads[i + 1].index : md.length);
    const vo = body.split("\n").filter((l) => l.startsWith("> ")).map((l) => l.slice(2).trim());
    if (vo.length) eps.push({ id: h[1], title: h[2], text: vo.join(" ") });
  });
  return eps;
}
function loadText(text, name) {
  text = text.replace(/^\uFEFF/, "").replace(/\r/g, "");
  S.episodes = parseEpisodes(text);
  const sel = $("episodeSel"); sel.replaceChildren();
  if (S.episodes.length) {
    for (const [i, ep] of S.episodes.entries()) sel.append(el("option", { value: i, text: `${ep.id} | ${ep.title}` }));
    sel.hidden = false; pickEpisode(0);
  } else {
    sel.hidden = true; S.label = (name || "script").replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_-]+/g, "").slice(0, 40) || "script";
    $("script").value = text; runCheck();
  }
  showError("");
}
async function openFile(f) {
  if (!f) return;
  try {
    if (!/\.(txt|md|docx)$/i.test(f.name)) throw new Error("Use a .txt, .md or .docx file.");
    if (/\.docx$/i.test(f.name)) {            // Word files are unpacked by the local server
      const buf = new Uint8Array(await f.arrayBuffer());
      let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
      loadText((await api("/api/parse", { body: { name: f.name, b64: btoa(bin) } })).text, f.name);
    } else loadText(await f.text(), f.name);    // text files are read right here in the browser
  } catch (e) { showError(e.message); }
}
$("fileIn").onchange = (ev) => { const f = ev.target.files[0]; ev.target.value = ""; openFile(f); };
$("pasteBtn").onclick = async () => {
  try { const t = await navigator.clipboard.readText(); if (!t.trim()) throw new Error("The clipboard has no text."); loadText(t, "script"); }
  catch (e) { showError(e.name === "NotAllowedError" ? "Allow clipboard access when the browser asks, or click in the script box and press Ctrl+V." : e.message); }
};
const box = $("script");
box.addEventListener("paste", (e) => {           // Ctrl+V of a copied file opens it; copied text pastes as usual
  const f = e.clipboardData && [...e.clipboardData.files][0];
  if (f) { e.preventDefault(); openFile(f); return; }
  const t = e.clipboardData && e.clipboardData.getData("text");
  if (t && !box.value.trim() && parseEpisodes(t).length) { e.preventDefault(); loadText(t, "script"); }
});
["dragenter", "dragover"].forEach((n) => box.addEventListener(n, (e) => { e.preventDefault(); box.classList.add("drop"); }));
["dragleave", "drop"].forEach((n) => box.addEventListener(n, () => box.classList.remove("drop")));
box.addEventListener("drop", (e) => { const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) { e.preventDefault(); openFile(f); } });
function pickEpisode(i) { const ep = S.episodes[i]; if (!ep) return; $("script").value = ep.text; S.label = ep.id; runCheck(); }
$("episodeSel").onchange = (e) => pickEpisode(+e.target.value);

/* ---------- voice-safe check (local, never blocks) ---------- */
let checkTimer = null, lastCheck = { warnings: [] };
function runCheck() { clearTimeout(checkTimer); checkTimer = setTimeout(doCheck, 350); }
async function doCheck() {
  const text = $("script").value;
  if (!text.trim()) { $("scriptMeta").textContent = "0 words"; $("safe").hidden = true; lastCheck = { warnings: [] }; return lastCheck; }
  try {
    const r = await api("/api/check", { body: { text } });
    lastCheck = r;
    const secs = r.words / 2.5 + r.pauses * ($("pause").value / 1000);
    $("scriptMeta").textContent = `${r.words} words, ${r.sentences} sentences, ${r.pauses} pause${r.pauses === 1 ? "" : "s"}, about ${fmt(secs)} spoken`;
    const cloud = currentEngine() && currentEngine().kind === "cloud";
    renderWarnings($("safe"), r.warnings, cloud
      ? "Voice-safe check: review these before sending to the cloud engine."
      : "Voice-safe check: fine for YarnGPT (it runs on this PC). These lines would matter for a cloud engine.");
    return r;
  } catch (e) { return lastCheck; }
}
function renderWarnings(box, warnings, heading) {
  box.replaceChildren(); box.hidden = !warnings.length;
  if (!warnings.length) return;
  box.append(el("div", { class: "head", text: heading }));
  for (const w of warnings) {
    const q = el("q"); const i = w.sentence.toLowerCase().indexOf(w.match.toLowerCase());
    if (i >= 0 && w.category !== "money_words") {
      q.append(w.sentence.slice(0, i), el("mark", { text: w.sentence.slice(i, i + w.match.length) }), w.sentence.slice(i + w.match.length));
    } else q.textContent = w.sentence;
    box.append(el("div", { class: "item" + (w.level === "note" ? " note" : "") },
      el("b", { text: `Sentence ${w.index + 1}: ${w.reason}` + (w.category === "money_words" ? ` (${w.match})` : "") +
        (w.level === "note" ? " (already described, low risk)" : "") }), q, el("span", { text: w.suggestion })));
  }
}
$("script").addEventListener("input", runCheck);

/* ---------- generate / preview ---------- */
function confirmCloud(warnings) {
  return new Promise((resolve) => {
    renderWarnings($("safeList"), warnings, "");
    const d = $("safeDlg");
    $("safeSend").onclick = () => { d.close(); resolve(true); };
    $("safeEdit").onclick = () => { d.close(); resolve(false); };
    d.oncancel = () => resolve(false);
    d.showModal();
  });
}
async function generate(preview) {
  const e = currentEngine(); if (!e || S.job) return;
  showError("");
  const text = $("script").value;
  if (!text.trim()) return showError("Add some text first.");
  if (e.kind === "cloud") {
    clearTimeout(checkTimer);
    const r = await doCheck();
    const check = preview ? r.warnings.filter((w) => w.index === 0) : r.warnings;
    if (check.length && !(await confirmCloud(check))) return;
  }
  try {
    const job = await api("/api/generate", { body: {
      text, engine: e.id, voice: S.voice[e.id], rate: +$("rate").value, pause_ms: +$("pause").value,
      gap_ms: +$("gap").value, preview, mp3: $("mp3").checked, label: S.label, params: paramValues(e) } });
    watch(job, preview);
  } catch (err) { showError(err.message); }
}
$("genBtn").onclick = () => generate(false);
$("previewBtn").onclick = () => generate(true);

function watch(job, preview) {
  S.job = job.id; syncControls();
  $("progress").hidden = false;
  const tick = async () => {
    let j;
    try { j = await api("/api/jobs/" + job.id); } catch (e) { j = { status: "error", error: e.message, total: 1, done: 0 }; }
    $("barFill").style.width = `${Math.round(100 * (j.done || 0) / Math.max(1, j.total))}%`;
    $("progText").textContent = j.message || "";
    if (!preview && j.session) { S.session = j.session; renderSession(j.current); }
    if (j.status === "running") return setTimeout(tick, 500);
    S.job = null; $("progress").hidden = true; syncControls(); refresh().catch(() => {});
    if (j.status === "error") showError(j.error);
    else if (j.message && j.message !== "Done") showError(j.message);
    if (preview && j.session && j.session.sentences[0] && j.session.sentences[0].url) {
      $("previewBox").hidden = false; const a = $("previewAudio"); a.src = j.session.sentences[0].url; a.play().catch(() => {});
    }
    if (!preview && j.session) { S.session = j.session; renderSession(); loadFinal(); loadHistory(); }
  };
  tick();
}

/* ---------- sentence editor ---------- */
const sentAudio = new Audio();
sentAudio.onended = sentAudio.onpause = () => { S.playing = null; markPlaying(); };
function markPlaying() { document.querySelectorAll(".mini-play").forEach((b) => b.classList.toggle("on", b.dataset.i === String(S.playing))); }
function renderSession(current) {
  const s = S.session; if (!s || s.preview) return;
  $("resultCard").hidden = false;
  const list = $("sentences"); const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.si : null;
  const drafts = {}; list.querySelectorAll("input[data-si]").forEach((i) => { if (i.dataset.dirty) drafts[i.dataset.si] = i.value; });
  list.replaceChildren();
  $("sentHint").textContent = s.merged
    ? "The cloud engine returned this take as one piece, so sentences cannot be redone one at a time. Press Generate to redo it."
    : "Play each sentence. If one sounds wrong, fix the text if needed and press Regenerate. Only that sentence is redone, then the full file is rebuilt as a new version.";
  for (const x of s.sentences) {
    const input = el("input", { type: "text", value: x.text, "data-si": x.index, "aria-label": `Sentence ${x.index + 1} text` });
    if (drafts[x.index] != null) { input.value = drafts[x.index]; input.dataset.dirty = "1"; }
    input.oninput = () => { input.dataset.dirty = "1"; };
    const working = x.state === "working" || (current === x.index && x.state !== "done");
    const sub = x.error ? el("div", { class: "sub bad", text: x.error })
      : x.flag ? el("div", { class: "sub warn", text: "Possible glitch: " + x.flag })
      : el("div", { class: "sub", text: working ? "Generating" : x.state === "pending" ? "Waiting" : x.state === "merged" ? "Included in the first clip" : `${x.dur}s` });
    const play = el("button", { class: "mini-play", type: "button", "data-i": x.index, "aria-label": `Play sentence ${x.index + 1}`,
      onclick: () => {
        if (!x.url) return;
        if (S.playing === x.index) { sentAudio.pause(); return; }
        $("mainAudio").pause(); sentAudio.src = x.url; sentAudio.play().catch(() => {}); S.playing = x.index; markPlaying();
      } });
    play.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
    play.disabled = !x.url;
    const regen = el("button", { class: "btn small", type: "button", text: "Regenerate",
      onclick: () => regenerate(x.index, input.dataset.dirty ? input.value : null) });
    regen.disabled = !!S.job || s.merged || x.state === "pending" && !x.error;
    list.append(el("li", { class: x.error ? "err" : x.flag ? "flag" : "" },
      el("span", { class: "n", text: x.index + 1 }), play, el("div", { class: "txt" }, input, sub), regen));
  }
  if (focused != null) { const f = list.querySelector(`input[data-si="${focused}"]`); if (f) f.focus(); }
  markPlaying();
}
async function regenerate(index, text) {
  if (S.job) return;
  showError("");
  const s = S.session;
  if (s.engine_kind === "cloud" && text) {
    const r = await api("/api/check", { body: { text } });
    if (r.warnings.length && !(await confirmCloud(r.warnings))) return;
  }
  try {
    const job = await api(`/api/sessions/${s.id}/regenerate`, { body: { index, text } });
    document.querySelectorAll("#sentences input").forEach((i) => { if (+i.dataset.si === index) delete i.dataset.dirty; });
    watch(job, false);
  } catch (e) { showError(e.message); }
}

/* ---------- player and waveform ---------- */
const main = $("mainAudio");
async function loadFinal() {
  const f = S.session && S.session.final; if (!f) return;
  main.src = f.url;
  $("saveMp3Btn").hidden = !f.mp3;
  $("resultMeta").textContent = `${f.wav}  |  48 kHz mono WAV, ${fmt(f.duration)}` +
    (f.lufs != null ? `, ${f.lufs} LUFS` : "") + (f.version > 1 ? `, version ${f.version}` : "") + (f.mp3 ? "  |  MP3 saved next to it" : "");
  try {
    const buf = await (await fetch(f.url)).arrayBuffer();
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const data = (await ctx.decodeAudioData(buf)).getChannelData(0); ctx.close();
    const n = 900, step = Math.max(1, Math.floor(data.length / n)); S.peaks = new Float32Array(n);
    for (let i = 0; i < n; i++) { let m = 0; for (let j = i * step, e = Math.min(data.length, j + step); j < e; j += 8) { const v = Math.abs(data[j]); if (v > m) m = v; } S.peaks[i] = m; }
  } catch (e) { S.peaks = null; }
  drawWave();
}
function drawWave() {
  const c = $("wave"); if (!c || $("resultCard").hidden) return;
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = 96;
  c.width = w * dpr; c.height = h * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim(), muted = css.getPropertyValue("--muted").trim();
  if (!S.peaks) return;
  const bars = Math.floor(w / 3), pos = main.duration ? main.currentTime / main.duration : 0;
  const max = Math.max(0.05, ...S.peaks);
  for (let i = 0; i < bars; i++) {
    const p = S.peaks[Math.floor(i / bars * S.peaks.length)] / max, bh = Math.max(2, p * (h - 8));
    g.fillStyle = i / bars < pos ? accent : muted;
    g.globalAlpha = i / bars < pos ? 1 : 0.55;
    g.fillRect(i * 3, (h - bh) / 2, 2, bh);
  }
  g.globalAlpha = 1;
}
function tickTime() {
  $("time").textContent = `${fmt(main.currentTime)} / ${fmt(main.duration || (S.session && S.session.final && S.session.final.duration))}`;
  $("playIcon").setAttribute("d", main.paused ? "M8 5v14l11-7z" : "M6 5h4v14H6zm8 0h4v14h-4z");
  drawWave();
}
main.ontimeupdate = main.onplay = main.onpause = main.onloadedmetadata = main.onended = tickTime;
$("playBtn").onclick = () => { sentAudio.pause(); main.paused ? main.play().catch(() => {}) : main.pause(); };
document.querySelector(".wave-wrap").onclick = (e) => {
  if (!main.duration) return; const r = $("wave").getBoundingClientRect();
  main.currentTime = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * main.duration;
};
window.addEventListener("resize", drawWave);
(function raf() { if (!main.paused) drawWave(); requestAnimationFrame(raf); })();

async function saveAs(fmtName) {
  const f = S.session && S.session.final; if (!f) return;
  const name = fmtName === "mp3" ? f.name.replace(/\.wav$/, ".mp3") : f.name;
  const url = `/api/sessions/${S.session.id}/final?fmt=${fmtName}`;
  try {
    if (window.showSaveFilePicker) {
      const h = await window.showSaveFilePicker({ suggestedName: name,
        types: [{ description: fmtName.toUpperCase() + " audio", accept: { [fmtName === "mp3" ? "audio/mpeg" : "audio/wav"]: ["." + fmtName] } }] });
      const w = await h.createWritable(); await w.write(await (await fetch(url)).blob()); await w.close();
    } else { const a = el("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove(); }
  } catch (e) { if (e.name !== "AbortError") showError(e.message); }
}
$("saveAsBtn").onclick = () => saveAs("wav");
$("saveMp3Btn").onclick = () => saveAs("mp3");
$("openFolderBtn").onclick = () => S.session && api(`/api/sessions/${S.session.id}/open`, { method: "POST" }).catch((e) => showError(e.message));

/* ---------- history ---------- */
async function loadHistory() {
  const rows = await api("/api/history"), box = $("history"); box.replaceChildren();
  if (!rows.length) return box.append(el("p", { class: "hint", text: "Nothing generated yet." }));
  for (const h of rows) {
    const acts = el("div", { class: "row" });
    if (h.exists) acts.append(el("a", { href: `/api/sessions/${h.id}/final?fmt=wav`, text: "WAV", download: "" }));
    if (h.exists && h.mp3) acts.append(el("a", { href: `/api/sessions/${h.id}/final?fmt=mp3`, text: "MP3", download: "" }));
    if (h.editable) acts.append(el("button", { class: "btn small", type: "button", text: "Open", onclick: async () => {
      try { S.session = await api("/api/sessions/" + h.id); renderSession(); await loadFinal(); $("resultCard").scrollIntoView({ behavior: "smooth" }); }
      catch (e) { showError(e.message); } } }));
    box.append(el("div", { class: "h-row" },
      el("div", { class: "when", text: new Date(h.date).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) }),
      el("div", {}, el("div", { class: "ex", text: (h.label !== "script" ? h.label + ": " : "") + h.excerpt }),
        el("div", { class: "who", text: `${h.engine}, ${h.voice}, ${fmt(h.duration)}  |  ${h.exists ? h.wav : "file moved or deleted"}` })),
      acts));
  }
}

/* ---------- settings ---------- */
$("settingsBtn").onclick = () => $("settingsDlg").showModal();
$("quitBtn").onclick = async () => { if (confirm("Stop Voice Studio?")) { await api("/api/quit", { method: "POST" }).catch(() => {}); document.body.innerHTML = '<p style="padding:40px">Voice Studio has stopped. You can close this tab.</p>'; } };
const azMsg = (t) => { $("azMsg").textContent = t; };
$("azSave").onclick = async () => {
  try { await api("/api/settings/azure", { body: { key: $("azKey").value || null, region: $("azRegion").value || null } });
    $("azKey").value = ""; azMsg("Saved to Windows Credential Manager."); refresh(); } catch (e) { azMsg(e.message); }
};
$("azTest").onclick = async () => {
  azMsg("Testing");
  try { const r = await api("/api/settings/azure/test", { body: { key: $("azKey").value || null, region: $("azRegion").value || null } }); azMsg(r.message); }
  catch (e) { azMsg(e.message); }
};
$("azForget").onclick = async () => { if (!confirm("Remove the Azure key and region from Credential Manager?")) return;
  await api("/api/settings/azure", { method: "DELETE" }); azMsg("Removed."); refresh(); };
const upMsg = (t) => { $("upMsg").textContent = t; };
$("upSave").onclick = async () => {
  try { await api("/api/update/settings", { body: { repo: $("upRepo").value, auto_check: $("upAuto").checked } }); upMsg("Saved."); }
  catch (e) { upMsg(e.message); }
};
async function checkUpdate(force) {
  try {
    const r = await api("/api/update/check" + (force ? "?force=true" : ""));
    if (r.error) { if (force) upMsg(r.error); return; }
    if (!r.configured) { if (force) upMsg("Add the repository first, then check again."); return; }
    if (r.skipped) return;
    $("upApply").hidden = !r.newer;
    const pill = $("updatePill"); pill.hidden = !r.newer;
    if (r.newer) { pill.textContent = `Update ${r.latest} available`; upMsg(`Version ${r.latest} is available (you have ${r.current}). ${r.notes || ""}`); }
    else if (force) upMsg(`You have the latest version (${r.current}).`);
  } catch (e) { if (force) upMsg(e.message); }
}
$("upCheck").onclick = () => checkUpdate(true);
$("updatePill").onclick = () => $("settingsDlg").showModal();
$("upApply").onclick = async () => {
  if (!confirm("Install the update now? The current app files are backed up first, then replaced. You will need to restart Voice Studio.")) return;
  upMsg("Downloading and installing");
  try { const r = await api("/api/update/apply", { method: "POST" }); upMsg(r.message + (r.backup ? ` Backup: ${r.backup}` : "")); $("upApply").hidden = true; $("updatePill").hidden = true; }
  catch (e) { upMsg(e.message); }
};

/* ---------- A/B compare ---------- */
function renderCompare() {
  const box = $("cmpRows"); if (!box) return;
  if (!S.cmp.length) { try { S.cmp = JSON.parse(store.get("vs-cmp") || "[]"); } catch (x) { S.cmp = []; } }
  while (S.cmp.length < 3) S.cmp.push({ engine: "", voice: "", opt: "" });
  box.replaceChildren();
  S.cmp.forEach((row, i) => {
    const eSel = el("select", { "aria-label": `Compare ${i + 1} engine` }, el("option", { value: "", text: i ? "None" : "Choose engine" }));
    for (const e of S.engines) if (!["missing", "unconfigured"].includes(e.status.state)) eSel.append(el("option", { value: e.id, text: e.name }));
    const e = S.engines.find((x) => x.id === row.engine && eSel.querySelector(`option[value="${x.id}"]`));
    eSel.value = e ? e.id : ""; if (!e) row.engine = "";
    const vSel = el("select", { "aria-label": `Compare ${i + 1} voice` }), oSel = el("select", { "aria-label": `Compare ${i + 1} option` });
    const selParam = e && e.params.find((p) => p.type === "select");
    if (e) {
      for (const v of e.voices) vSel.append(el("option", { value: v.id, text: v.label }));
      if (!e.voices.some((v) => v.id === row.voice)) row.voice = e.voices[0] ? e.voices[0].id : "";
      vSel.value = row.voice;
      if (selParam) {
        for (const o of selParam.options) oSel.append(el("option", { value: o.id, text: o.label }));
        if (!selParam.options.some((o) => o.id === row.opt)) row.opt = paramValues(e)[selParam.id];
        oSel.value = row.opt;
      }
    }
    vSel.disabled = !e; oSel.disabled = !selParam; if (!selParam) oSel.append(el("option", { text: e ? "No extra option" : "" }));
    const save = () => store.set("vs-cmp", JSON.stringify(S.cmp));
    eSel.onchange = () => { row.engine = eSel.value; row.voice = ""; row.opt = ""; save(); renderCompare(); };
    vSel.onchange = () => { row.voice = vSel.value; save(); };
    oSel.onchange = () => { row.opt = oSel.value; save(); };
    box.append(el("div", { class: "cmp-row" }, el("span", { class: "n", text: "ABC"[i] }), eSel, vSel, oSel));
  });
}
$("cmpBtn").onclick = async () => {
  if (S.job) return;
  const msg = (t) => { $("cmpMsg").textContent = t || ""; };
  const text = $("script").value;
  if (!text.trim()) return msg("Add some text first.");
  const choices = [];
  for (const row of S.cmp) {
    const e = S.engines.find((x) => x.id === row.engine); if (!e || !row.voice) continue;
    const params = paramValues(e), sp = e.params.find((p) => p.type === "select");
    if (sp && row.opt) params[sp.id] = row.opt;
    choices.push({ engine: e.id, voice: row.voice, params, cloud: e.kind === "cloud" });
  }
  if (!choices.length) return msg("Choose at least one engine and voice.");
  if (choices.some((c) => c.cloud)) {
    clearTimeout(checkTimer); const r = await doCheck();
    const w = r.warnings.filter((x) => x.index < 2);
    if (w.length && !(await confirmCloud(w))) return;
  }
  try {
    const job = await api("/api/compare", { body: { text, choices, rate: +$("rate").value, pause_ms: +$("pause").value, gap_ms: +$("gap").value } });
    S.job = job.id; syncControls(); $("cmpResults").replaceChildren();
    const tick = async () => {
      let j; try { j = await api("/api/jobs/" + job.id); } catch (e) { j = { status: "error", message: e.message, results: [] }; }
      msg(j.status === "running" ? j.message : j.status === "error" ? j.message : `Compared: "${j.text}"`);
      const box = $("cmpResults"); box.replaceChildren();
      (j.results || []).forEach((r, i) => {
        const right = r.state === "done" ? el("audio", { controls: "", src: r.url, preload: "auto" })
          : el("span", { class: r.state === "error" ? "error" : "hint", text: r.state === "error" ? r.error : "Waiting" });
        box.append(el("div", { class: "cmp-res" }, el("div", {}, el("b", { text: "ABC"[i] + "  " }), document.createTextNode(r.label)), right));
      });
      if (j.status === "running") return setTimeout(tick, 700);
      S.job = null; syncControls(); refresh().catch(() => {});
    };
    tick();
  } catch (e) { msg(e.message); }
};

/* ---------- voice profiles ---------- */
const REC = { ctx: null, stream: null, node: null, src: null, chunks: [], t0: 0, timer: null, token: null, url: null };
const profMsg = (t) => { const e = $("profMsg"); e.textContent = t || ""; e.hidden = !t; };
function openProfiles() { $("passage").textContent = S.prof.passage; $("consentText").textContent = S.prof.consent; resetRec(); loadProfiles(); $("profilesDlg").showModal(); }
$("profilesBtn").onclick = openProfiles;
$("profClose").onclick = () => { stopRec(true); $("profilesDlg").close(); };
$("profilesDlg").addEventListener("close", () => stopRec(true));
async function loadProfiles() {
  const rows = await api("/api/profiles"), box = $("profList"); box.replaceChildren();
  if (!rows.length) box.append(el("p", { class: "hint", text: "No voice profiles yet." }));
  for (const p of rows) {
    const audio = el("audio", { controls: "", preload: "none", src: `/api/profiles/${p.id}/audio` });
    box.append(el("div", { class: "h-row" },
      el("div", {}, el("div", { class: "ex", text: p.name }), el("div", { class: "when", text: `${new Date(p.created).toLocaleDateString([], { dateStyle: "medium" })}, ${p.duration}s` })),
      audio,
      el("div", { class: "row" },
        el("button", { class: "btn small", type: "button", text: "Rename", onclick: async () => {
          const name = prompt("New name for this voice profile", p.name); if (!name) return;
          try { await api(`/api/profiles/${p.id}`, { method: "PATCH", body: { name } }); loadProfiles(); refresh(); } catch (e) { profMsg(e.message); } } }),
        el("button", { class: "btn small ghost", type: "button", text: "Delete", onclick: async () => {
          if (!confirm(`Delete the voice profile "${p.name}" and its recording? This cannot be undone.`)) return;
          try { await api(`/api/profiles/${p.id}`, { method: "DELETE" }); loadProfiles(); refresh(); } catch (e) { profMsg(e.message); } } }))));
  }
}
function resetRec() {
  REC.token = null; $("recSave").hidden = true; $("recReport").hidden = true; $("recTime").textContent = ""; $("meterWrap").hidden = true;
  $("profConsent").checked = false; $("profSave").disabled = true; $("recBtn").textContent = "Record"; profMsg("");
}
function wavBlob(chunks, sr) {
  const n = chunks.reduce((a, c) => a + c.length, 0), buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const w = (o, t) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
  let o = 44; for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) { const x = Math.max(-1, Math.min(1, c[i])); v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7FFF, true); }
  return new Blob([buf], { type: "audio/wav" });
}
async function blobB64(blob) {
  const buf = new Uint8Array(await blob.arrayBuffer()); let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(bin);
}
async function startRec() {
  resetRec();
  try {
    REC.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  } catch (e) { return profMsg("The microphone could not be opened. Allow microphone access for this page in the browser, and check that a microphone is connected."); }
  REC.ctx = new (window.AudioContext || window.webkitAudioContext)();
  REC.src = REC.ctx.createMediaStreamSource(REC.stream);
  REC.node = REC.ctx.createScriptProcessor(4096, 1, 1);
  REC.chunks = []; REC.t0 = Date.now();
  REC.node.onaudioprocess = (ev) => {
    const d = ev.inputBuffer.getChannelData(0); REC.chunks.push(new Float32Array(d));
    let m = 0; for (let i = 0; i < d.length; i += 16) m = Math.max(m, Math.abs(d[i]));
    const bar = $("meter"); bar.style.width = Math.min(100, m * 100) + "%"; bar.classList.toggle("hot", m > 0.97);
  };
  REC.src.connect(REC.node); REC.node.connect(REC.ctx.destination);
  $("recBtn").textContent = "Stop"; $("meterWrap").hidden = false; $("recTime").classList.add("live");
  REC.timer = setInterval(() => {
    const s = (Date.now() - REC.t0) / 1000; $("recTime").textContent = `Recording ${s.toFixed(0)}s (aim for about 20)`;
    if (s >= 40) stopRec(false);
  }, 250);
}
async function stopRec(discard) {
  if (!REC.ctx) return;
  clearInterval(REC.timer); $("recTime").classList.remove("live");
  const sr = REC.ctx.sampleRate, chunks = REC.chunks;
  try { REC.node.disconnect(); REC.src.disconnect(); REC.stream.getTracks().forEach((t) => t.stop()); await REC.ctx.close(); } catch (e) { /* already closed */ }
  REC.ctx = null; $("recBtn").textContent = "Record"; $("meterWrap").hidden = true;
  if (!discard) await checkTake(wavBlob(chunks, sr));
}
$("recBtn").onclick = () => (REC.ctx ? stopRec(false) : startRec());
$("recAgain").onclick = () => startRec();
$("importBtn").onclick = () => $("importIn").click();
$("importIn").onchange = async (ev) => {
  const f = ev.target.files[0]; ev.target.value = ""; if (!f) return;
  resetRec();
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const ab = await ctx.decodeAudioData(await f.arrayBuffer()); ctx.close();
    const mono = new Float32Array(ab.length);
    for (let c = 0; c < ab.numberOfChannels; c++) { const d = ab.getChannelData(c); for (let i = 0; i < d.length; i++) mono[i] += d[i] / ab.numberOfChannels; }
    await checkTake(wavBlob([mono], ab.sampleRate));
  } catch (e) { profMsg("That file could not be read. Use a WAV or MP3 recording of your own voice."); }
};
async function checkTake(blob) {
  $("recTime").textContent = "Checking the recording";
  try {
    const r = await api("/api/profiles/check", { body: { b64: await blobB64(blob) } });
    const box = $("recReport"); box.replaceChildren(); box.hidden = false;
    $("recTime").textContent = `${r.duration}s of speech`;
    if (r.ok) {
      box.append(el("div", { class: "item good" }, el("b", { text: "Good recording" }),
        el("span", { text: ` ${r.duration} seconds of speech, no clipping, low background noise.` + (r.trimmed_s > 0.2 ? ` ${r.trimmed_s}s of silence was trimmed from the ends.` : "") })));
      REC.token = r.token; if (REC.url) URL.revokeObjectURL(REC.url); REC.url = URL.createObjectURL(blob);
      $("recAudio").src = REC.url; $("recSave").hidden = false;
    } else {
      for (const pr of r.problems) box.append(el("div", { class: "item" }, el("b", { text: "Please record again" }), el("q", { text: pr })));
      box.append(el("button", { class: "btn", type: "button", text: "Record again", onclick: startRec }));
    }
  } catch (e) { profMsg(e.message); $("recTime").textContent = ""; }
}
const saveReady = () => { $("profSave").disabled = !($("profConsent").checked && $("profName").value.trim() && REC.token); };
$("profConsent").onchange = saveReady; $("profName").oninput = saveReady;
$("profSave").onclick = async () => {
  try {
    await api("/api/profiles", { body: { token: REC.token, name: $("profName").value, consent: $("profConsent").checked } });
    $("profName").value = ""; resetRec(); await loadProfiles(); await refresh();
  } catch (e) { profMsg(e.message); }
};

/* ---------- startup ---------- */
async function refresh() {
  const st = await api("/api/state");
  S.engines = st.engines; S.cloudGap = st.cloud_gap;
  if (!S.engine || !S.engines.find((e) => e.id === S.engine)) {
    const saved = store.get("vs-engine"); S.engine = (S.engines.find((e) => e.id === saved) || S.engines[0] || {}).id;
  }
  $("ver").textContent = "v" + st.version;
  $("mp3").disabled = !st.mp3; if (!st.mp3) $("mp3").parentElement.title = "MP3 export needs the lameenc package (run Setup.bat).";
  if (document.activeElement !== $("azRegion")) $("azRegion").value = st.azure.region;
  $("azKey").placeholder = st.azure.configured ? "A key is saved. Paste a new one to replace it." : "Paste Key 1";
  if (document.activeElement !== $("upRepo")) $("upRepo").value = st.update.repo;
  $("upAuto").checked = st.update.auto_check;
  $("about").textContent = `Voice Studio ${st.version}. Runs on this PC at 127.0.0.1 only. Output folder: ${st.out_root}. ` +
    "No analytics or telemetry. The only network calls are Azure requests you start and the update check above. Voice profiles stay on this PC.";
  S.prof = st.profiles;
  renderEngines(); renderVoices(); renderParams(); syncControls(); renderCompare();
  return st;
}
(async function init() {
  setTheme(store.get("vs-theme") || "dark");
  try {
    await refresh(); await loadHistory();
    const e = currentEngine();
    if (e && e.kind === "local" && e.status.state === "idle") activate(e.id);
  } catch (e) { showError("Cannot reach the Voice Studio server. Is it still running?"); }
  setInterval(() => { const c = currentEngine();
    if (!S.job && (S.engines.some((e) => e.status.state === "loading") || (c && c.kind === "local" && c.status.state === "idle"))) refresh().catch(() => {}); }, 2000);
  checkUpdate(false);
})();
