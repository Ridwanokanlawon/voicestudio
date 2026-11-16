"use strict";
const $ = (id) => document.getElementById(id);
const S = { engines: [], engine: null, voice: {}, session: null, job: null, episodes: [], label: "script",
            peaks: null, lastCloud: 0, cloudGap: 3, playing: null };

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
function renderEngines() {
  const box = $("engines"); box.replaceChildren();
  for (const e of S.engines) {
    const ready = e.status.state === "ready";
    const radio = el("input", { type: "radio", name: "engine", value: e.id });
    radio.checked = e.id === S.engine;
    const row = el("label", { class: "engine" + (e.id === S.engine ? " sel" : "") }, radio,
      el("span", { class: "name", text: e.name }),
      el("span", { class: "badge " + (e.kind === "cloud" ? "cloud" : "local"), text: e.badge }),
      el("span", { class: "st" + (e.status.state === "error" ? " bad" : ""),
                   text: (ready ? "Ready. " : e.status.state === "loading" ? "Loading. " : "") + (e.status.detail || "") }));
    radio.onchange = () => { S.engine = e.id; store.set("vs-engine", e.id); renderEngines(); renderVoices(); syncControls(); };
    box.append(row);
  }
  const yarn = S.engines.find((e) => e.kind === "local") || S.engines[0];
  const pill = $("enginePill");
  if (yarn) {
    pill.textContent = `${yarn.name}: ${yarn.status.state === "ready" ? yarn.status.detail || "ready" : yarn.status.state}`;
    pill.className = "pill " + (yarn.status.state === "ready" ? "ok" : yarn.status.state === "error" ? "bad" : "");
  }
}
function renderVoices() {
  const e = currentEngine(), box = $("voices"); box.replaceChildren();
  if (!e) return;
  if (!S.voice[e.id]) S.voice[e.id] = store.get("vs-voice-" + e.id) || e.voices[0].id;
  for (const v of e.voices) {
    box.append(el("button", { class: "voice" + (S.voice[e.id] === v.id ? " sel" : ""), type: "button",
      onclick: () => { S.voice[e.id] = v.id; store.set("vs-voice-" + e.id, v.id); renderVoices(); } },
      document.createTextNode(v.label), el("small", { text: v.note || "" })));
  }
}
function syncControls() {
  const e = currentEngine(); if (!e) return;
  const cloud = e.kind === "cloud";
  $("rateNote").textContent = e.rate_note || "";
  $("gapWrap").hidden = cloud;
  const note = $("cloudNote"); note.hidden = !cloud;
  note.textContent = cloud ? `Cloud safety rules: one request per click, no retries, at least ${S.cloudGap} seconds between requests, and a voice-safe check before sending.` : "";
  const ready = e.status.state === "ready";
  $("genBtn").disabled = $("previewBtn").disabled = !ready || !!S.job;
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
      gap_ms: +$("gap").value, preview, mp3: $("mp3").checked, label: S.label } });
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
    S.job = null; $("progress").hidden = true; syncControls();
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
    "No analytics or telemetry. The only network calls are Azure requests you start and the update check above.";
  renderEngines(); renderVoices(); syncControls();
  return st;
}
(async function init() {
  setTheme(store.get("vs-theme") || "dark");
  try { await refresh(); await loadHistory(); } catch (e) { showError("Cannot reach the Voice Studio server. Is it still running?"); }
  setInterval(() => { if (S.engines.some((e) => e.status.state === "loading")) refresh().catch(() => {}); }, 2500);
  checkUpdate(false);
})();
