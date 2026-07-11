from __future__ import annotations


def render_console_page() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PunGen Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef1f3;
      --surface: #ffffff;
      --surface-2: #f7f8f9;
      --ink: #17191c;
      --muted: #66707a;
      --line: #d6dce1;
      --sidebar: #17191c;
      --red: #c3423f;
      --teal: #19756f;
      --amber: #9a6415;
      --blue: #27658a;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input, textarea, select { font: inherit; letter-spacing: 0; }
    button { cursor: pointer; }
    .app { min-height: 100vh; display: grid; grid-template-columns: 224px minmax(0, 1fr); }
    aside { background: var(--sidebar); color: #fff; padding: 20px 14px; }
    .brand { padding: 4px 10px 22px; border-bottom: 1px solid #34383d; }
    .brand strong { display: block; font-size: 18px; }
    .brand span { display: block; margin-top: 5px; color: #aeb6bd; font-size: 12px; }
    nav { display: grid; gap: 4px; margin-top: 18px; }
    .nav-button {
      display: flex; align-items: center; gap: 10px; width: 100%; min-height: 42px;
      border: 0; border-radius: 5px; padding: 9px 10px; color: #cbd1d6;
      background: transparent; text-align: left;
    }
    .nav-button:hover, .nav-button.active { background: #2b3035; color: #fff; }
    .nav-button.active { border-left: 3px solid #ef6b61; padding-left: 7px; }
    .nav-button svg { width: 17px; height: 17px; flex: 0 0 auto; }
    main { min-width: 0; }
    .topbar {
      min-height: 64px; display: flex; align-items: center; justify-content: space-between;
      gap: 16px; padding: 12px 24px; background: var(--surface); border-bottom: 1px solid var(--line);
    }
    .topbar h1 { margin: 0; font-size: 20px; }
    .runtime-status { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--teal); }
    .workspace { padding: 20px 24px 32px; }
    .view { display: none; }
    .view.active { display: block; }
    .section-head { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .section-head h2 { margin: 0; font-size: 17px; }
    .section-head p { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
    .panel { background: var(--surface); border: 1px solid var(--line); border-radius: 7px; }
    .panel-head { padding: 13px 15px; border-bottom: 1px solid var(--line); font-size: 13px; font-weight: 650; }
    .panel-body { padding: 15px; }
    .live-grid { display: grid; grid-template-columns: minmax(300px, .9fr) minmax(380px, 1.1fr); gap: 14px; }
    .span-all { grid-column: 1 / -1; }
    label { display: block; color: var(--muted); font-size: 12px; margin: 0 0 6px; }
    input, textarea, select {
      width: 100%; border: 1px solid #bdc6ce; border-radius: 5px; background: #fff;
      color: var(--ink); padding: 9px 10px;
    }
    textarea { min-height: 104px; resize: vertical; }
    .field-row { display: grid; grid-template-columns: 1fr 160px; gap: 10px; margin-bottom: 12px; }
    .command-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .command {
      min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px;
      border: 1px solid var(--ink); border-radius: 5px; padding: 8px 12px; background: var(--ink); color: #fff;
    }
    .command.secondary { background: #fff; color: var(--ink); border-color: #aeb7bf; }
    .command:disabled { opacity: .45; cursor: not-allowed; }
    .command svg { width: 16px; height: 16px; }
    .metric-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: 1px solid var(--line); }
    .metric { padding: 13px; border-right: 1px solid var(--line); min-width: 0; }
    .metric:last-child { border-right: 0; }
    .metric b { display: block; overflow-wrap: anywhere; font-size: 14px; }
    .metric span { display: block; margin-top: 5px; color: var(--muted); font-size: 11px; }
    .result-log { margin: 0; min-height: 230px; max-height: 360px; overflow: auto; padding: 14px; background: #16191d; color: #d9e0e5; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .stage-result { min-height: 230px; display: grid; align-content: center; gap: 14px; padding: 24px; background: #17191c; color: #fff; }
    .stage-result.performing { animation: stage-pulse .8s ease-out; }
    .stage-kicker { color: #efb34c; font-size: 12px; font-weight: 700; text-transform: uppercase; }
    .stage-line { margin: 0; max-width: 880px; font-size: clamp(24px, 3vw, 40px); line-height: 1.18; overflow-wrap: anywhere; }
    .stage-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: #b8c0c7; font-size: 13px; }
    .heart-track { width: min(280px, 65vw); height: 8px; overflow: hidden; background: #3b4147; border-radius: 4px; }
    .heart-fill { width: 0; height: 100%; background: #ef6b61; transition: width .65s ease; }
    .capability-note { padding: 5px 8px; border: 1px solid #59616a; border-radius: 4px; color: #d4d9de; }
    .capability-note.fallback { border-color: #efb34c; color: #efb34c; }
    details.debug { border-top: 1px solid #343a40; background: #16191d; color: #d9e0e5; }
    details.debug summary { cursor: pointer; padding: 11px 14px; color: #aeb7bf; font-size: 12px; }
    details.debug .result-log { min-height: 120px; max-height: 280px; border-top: 1px solid #343a40; }
    @keyframes stage-pulse { 0% { box-shadow: inset 0 0 0 2px #efb34c; } 100% { box-shadow: inset 0 0 0 0 transparent; } }
    .viewer-frame { width: 100%; height: 460px; display: block; border: 0; background: #101214; }
    .pipeline { display: grid; grid-template-columns: repeat(6, minmax(105px, 1fr)); align-items: stretch; overflow-x: auto; }
    .pipeline-node { position: relative; padding: 16px 14px; border-right: 1px solid var(--line); min-width: 105px; }
    .pipeline-node:last-child { border-right: 0; }
    .pipeline-node b { display: block; font-size: 13px; }
    .pipeline-node span { display: block; margin-top: 5px; font-size: 11px; color: var(--muted); }
    .pipeline-node::after { content: "›"; position: absolute; right: -5px; top: 23px; color: var(--red); z-index: 1; }
    .pipeline-node:last-child::after { content: ""; }
    .badge { display: inline-flex; align-items: center; min-height: 23px; padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 650; }
    .badge.simulated { background: #fff1d9; color: #7a4b08; }
    .badge.ready { background: #def3ee; color: #115f59; }
    .badge.offline { background: #eceff1; color: #5d666e; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 11px 13px; border-bottom: 1px solid var(--line); text-align: left; font-size: 13px; vertical-align: top; }
    th { color: var(--muted); font-size: 11px; font-weight: 600; background: var(--surface-2); }
    tr:last-child td { border-bottom: 0; }
    .table-wrap { overflow-x: auto; }
    .evidence-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 14px; }
    .timeline { display: grid; gap: 10px; }
    .event { border-left: 3px solid var(--amber); padding: 8px 10px; background: var(--surface-2); }
    .event b { font-size: 12px; }
    .event p { margin: 4px 0 0; color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }
    .architecture-map { display: grid; gap: 12px; }
    .architecture-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .arch-module { min-height: 112px; padding: 15px; border: 1px solid var(--line); border-left: 4px solid var(--blue); background: var(--surface); }
    .arch-module.deep { border-left-color: var(--teal); }
    .arch-module.adapter { border-left-color: var(--amber); }
    .arch-module h3 { margin: 0; font-size: 14px; }
    .arch-module p { margin: 7px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .arch-flow { display: grid; grid-template-columns: repeat(6, minmax(100px, 1fr)); border: 1px solid var(--line); background: var(--surface); overflow-x: auto; }
    .empty { padding: 28px; color: var(--muted); text-align: center; font-size: 13px; }
    @media (max-width: 920px) {
      .app { grid-template-columns: 1fr; }
      aside { padding: 10px 12px; }
      .brand { display: flex; justify-content: space-between; align-items: center; padding: 4px 4px 10px; }
      nav { display: flex; overflow-x: auto; margin-top: 8px; }
      .nav-button { width: auto; white-space: nowrap; }
      .live-grid, .evidence-layout { grid-template-columns: 1fr; }
      .architecture-row { grid-template-columns: 1fr; }
      .viewer-frame { height: 390px; }
    }
    @media (max-width: 620px) {
      .topbar { padding: 11px 14px; }
      .workspace { padding: 14px; }
      .field-row { grid-template-columns: 1fr; }
      .metric-strip { grid-template-columns: 1fr 1fr; }
      .metric:nth-child(2) { border-right: 0; }
      .metric:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .viewer-frame { height: 350px; }
    }
  </style>
  <script src="/static/vendor/lucide.min.js"></script>
</head>
<body>
<div class="app">
  <aside>
    <div class="brand"><strong>PunGen Console</strong><span>Culture-to-Embodiment Runtime</span></div>
    <nav aria-label="Console views">
      <button class="nav-button active" data-view="live"><i data-lucide="radio"></i>Live</button>
      <button class="nav-button" data-view="devices"><i data-lucide="bot"></i>Devices</button>
      <button class="nav-button" data-view="knowledge"><i data-lucide="database"></i>Knowledge</button>
      <button class="nav-button" data-view="evidence"><i data-lucide="activity"></i>Evidence</button>
      <button class="nav-button" data-view="architecture"><i data-lucide="network"></i>Architecture</button>
    </nav>
  </aside>
  <main>
    <header class="topbar">
      <h1 id="page-title">Live Console</h1>
      <div class="runtime-status"><span class="dot"></span><span id="runtime-label">Connecting...</span><span id="mode-badge" class="badge simulated">SIMULATED</span></div>
    </header>
    <div class="workspace">
      <section class="view active" data-view="live">
        <div class="section-head"><div><h2>Interaction Run</h2><p id="run-id">No active trace</p></div></div>
        <div class="live-grid">
          <section class="panel">
            <div class="panel-head">Observation</div>
            <div class="panel-body">
              <div class="field-row">
                <div><label for="scene">Scene</label><input id="scene" value="评委展示开场"></div>
                <div><label for="adapter">Execution adapter</label><select id="adapter"><option value="dry_run">dry_run</option></select></div>
              </div>
              <label for="utterance">Utterance</label>
              <textarea id="utterance">No one knows Robot better than me，播放 YMCA</textarea>
              <div class="command-row">
                <button class="command" id="perform-now"><i data-lucide="sparkles"></i>一键表演</button>
                <button class="command secondary" id="run-decision"><i data-lucide="scan-search"></i>仅识别</button>
                <button class="command secondary" id="execute-action" disabled><i data-lucide="cpu"></i>仅执行</button>
              </div>
            </div>
          </section>
          <section class="panel" aria-live="polite">
            <div class="panel-head">现场回应</div>
            <div class="metric-strip">
              <div class="metric"><b id="metric-meme">-</b><span>meme</span></div>
              <div class="metric"><b id="metric-confidence">-</b><span>confidence</span></div>
              <div class="metric"><b id="metric-action">-</b><span>action</span></div>
              <div class="metric"><b id="metric-evidence">-</b><span>evidence</span></div>
            </div>
            <div class="stage-result" id="stage-result">
              <span class="stage-kicker" id="stage-kicker">等待用户输入</span>
              <h3 class="stage-line" id="stage-line">说一句话，让它接梗并演出来</h3>
              <div class="stage-meta">
                <span>心动值 <b id="heart-value">--</b></span>
                <div class="heart-track" aria-label="心动值"><div class="heart-fill" id="heart-fill"></div></div>
                <span class="capability-note" id="motion-capability">等待动作能力检查</span>
                <button class="command secondary" id="replay-voice" disabled><i data-lucide="volume-2"></i>重播回应</button>
              </div>
            </div>
            <details class="debug"><summary>开发者详情 JSON</summary><pre class="result-log" id="result-log">{}</pre></details>
          </section>
          <section class="panel span-all">
            <div class="panel-head">Runtime Flow</div>
            <div class="pipeline">
              <div class="pipeline-node"><b>Observation</b><span>voice · text · vision</span></div>
              <div class="pipeline-node"><b>Knowledge</b><span>culture snapshot</span></div>
              <div class="pipeline-node"><b>Decision</b><span>candidate · risk · fallback</span></div>
              <div class="pipeline-node"><b>Execution</b><span>safety · idempotency</span></div>
              <div class="pipeline-node"><b>Adapter</b><span>robot · arm · avatar</span></div>
              <div class="pipeline-node"><b>Evidence</b><span>trace · result · feedback</span></div>
            </div>
          </section>
          <section class="panel span-all">
            <div class="panel-head">Selected Embodied Asset</div>
            <iframe class="viewer-frame" id="embodied-stage" src="/viewer" title="Selected 3D asset"></iframe>
          </section>
        </div>
      </section>

      <section class="view" data-view="devices">
        <div class="section-head"><div><h2>Devices & Adapters</h2><p>Capability and evidence status</p></div><button class="command secondary" id="refresh-status"><i data-lucide="refresh-cw"></i>Refresh</button></div>
        <div class="panel table-wrap"><table><thead><tr><th>Target</th><th>Status</th><th>Adapter</th><th>Evidence</th></tr></thead><tbody id="device-rows"></tbody></table></div>
      </section>

      <section class="view" data-view="knowledge">
        <div class="section-head"><div><h2>Knowledge Catalog</h2><p><span id="meme-count">0</span> memes · <span id="action-count">0</span> actions</p></div></div>
        <div class="panel table-wrap"><table><thead><tr><th>Meme</th><th>Cues</th><th>Response mode</th><th>Voice</th><th>Actions</th><th>Asset</th></tr></thead><tbody id="meme-rows"></tbody></table></div>
      </section>

      <section class="view" data-view="evidence">
        <div class="section-head"><div><h2>Evidence Trace</h2><p>Mock, simulated and real evidence remain separate</p></div></div>
        <div class="evidence-layout">
          <section class="panel"><div class="panel-head">Trace Query</div><div class="panel-body"><label for="trace-query">Trace ID</label><input id="trace-query" placeholder="trace id"><button class="command" id="query-trace"><i data-lucide="search"></i>Query</button></div></section>
          <section class="panel"><div class="panel-head">Timeline</div><div class="panel-body timeline" id="timeline"><div class="empty">No trace selected</div></div></section>
        </div>
      </section>

      <section class="view" data-view="architecture">
        <div class="section-head"><div><h2>Production Architecture</h2><p>Stable interfaces with replaceable adapters</p></div></div>
        <div class="architecture-map">
          <div class="arch-flow">
            <div class="pipeline-node"><b>Observation</b><span>multimodal input</span></div>
            <div class="pipeline-node"><b>Knowledge</b><span>versioned culture graph</span></div>
            <div class="pipeline-node"><b>Decision</b><span>rules · retrieval · model</span></div>
            <div class="pipeline-node"><b>Execution</b><span>safety lifecycle</span></div>
            <div class="pipeline-node"><b>Adapter</b><span>device-specific SDK</span></div>
            <div class="pipeline-node"><b>Evidence</b><span>learning loop</span></div>
          </div>
          <div class="architecture-row">
            <article class="arch-module deep"><h3>Decision Module</h3><p>Observation and context in; calibrated decision, risk and fallback out.</p></article>
            <article class="arch-module deep"><h3>Execution Module</h3><p>Canonical action validation, idempotency, safety and execution lifecycle.</p></article>
            <article class="arch-module deep"><h3>Observation Module</h3><p>Trace persistence with explicit evidence levels and replayable events.</p></article>
          </div>
          <div class="architecture-row">
            <article class="arch-module adapter"><h3>Input Adapters</h3><p>Text, ASR, camera and event-stream observations.</p></article>
            <article class="arch-module adapter"><h3>Execution Adapters</h3><p>Unitree, robot arm, dexterous hand, avatar and dry-run.</p></article>
            <article class="arch-module adapter"><h3>External Adapters</h3><p>Hyper3D, LLM inference and future knowledge providers.</p></article>
          </div>
        </div>
      </section>
    </div>
  </main>
</div>
<script>
  const state = { agentResponse: null, traceId: "", speaking: false };
  const titles = { live: "Live Console", devices: "Devices", knowledge: "Knowledge", evidence: "Evidence", architecture: "Architecture" };
  const byId = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const makeId = () => globalThis.crypto?.randomUUID?.() || `trace-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  async function jsonRequest(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
    document.querySelectorAll(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
    byId("page-title").textContent = titles[name] || name;
  }

  async function refreshStatus() {
    const payload = await jsonRequest("/system/status");
    byId("runtime-label").textContent = payload.runtime.status === "ready" ? "Runtime ready" : payload.runtime.status;
    byId("meme-count").textContent = payload.knowledge.meme_count;
    byId("action-count").textContent = payload.knowledge.action_count;
    const adapter = payload.adapters[0] || {name: "none", evidence_level: "mock"};
    const adapterSelect = byId("adapter");
    const selectedAdapter = adapterSelect.value;
    adapterSelect.innerHTML = payload.adapters.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${escapeHtml(item.evidence_level)}</option>`).join("");
    if (payload.adapters.some((item) => item.name === selectedAdapter)) adapterSelect.value = selectedAdapter;
    const rows = Object.entries(payload.devices).map(([name, info]) => `<tr><td>${escapeHtml(name)}</td><td><span class="badge offline">${escapeHtml(info.status)}</span></td><td>${escapeHtml(adapter.name)}</td><td><span class="badge simulated">${escapeHtml(adapter.evidence_level)}</span></td></tr>`);
    byId("device-rows").innerHTML = rows.join("");
  }

  async function loadKnowledge() {
    const payload = await jsonRequest("/memes");
    byId("meme-rows").innerHTML = payload.memes.map((meme) => `<tr><td><b>${escapeHtml(meme.name)}</b><br><span>${escapeHtml(meme.id)}</span></td><td>${escapeHtml([...meme.aliases, ...meme.symbols].slice(0, 5).join(" · "))}</td><td>${escapeHtml(meme.response_mode)}</td><td>${escapeHtml(meme.character_id || "-")}</td><td>${escapeHtml(meme.actions.join(", "))}</td><td>${meme.asset_id ? "linked" : "-"}</td></tr>`).join("");
  }

  function renderStage(payload) {
    const line = payload.action?.line || payload.recognition?.line || "我还没接住这个梗，再给我一点线索。";
    const heart = Math.round(Number(payload.emotion?.heart_value || 0));
    byId("stage-kicker").textContent = `${payload.recognition?.meme_name || "未识别"} · ${payload.emotion?.dominant_state || "neutral"}`;
    byId("stage-line").textContent = line;
    byId("heart-value").textContent = heart;
    byId("heart-fill").style.width = `${Math.max(0, Math.min(100, heart))}%`;
    byId("replay-voice").disabled = !line;
    byId("stage-result").classList.remove("performing");
    requestAnimationFrame(() => byId("stage-result").classList.add("performing"));
  }

  function speakResponse() {
    const line = state.agentResponse?.action?.line || state.agentResponse?.recognition?.line;
    if (!line || !("speechSynthesis" in globalThis)) return;
    globalThis.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(line);
    utterance.lang = "zh-CN";
    utterance.rate = 1.02;
    utterance.pitch = state.agentResponse?.emotion?.dominant_state === "dramatic" ? 0.88 : 1.08;
    globalThis.speechSynthesis.speak(utterance);
  }

  function triggerEmbodiedStage() {
    const frame = byId("embodied-stage");
    frame.contentWindow?.postMessage({
      type: "pungen:perform",
      action: state.agentResponse?.action || {},
      emotion: state.agentResponse?.emotion || {},
    }, globalThis.location.origin);
  }

  window.addEventListener("message", (event) => {
    if (event.origin !== globalThis.location.origin || event.data?.type !== "pungen:performance-status") return;
    const capability = byId("motion-capability");
    if (event.data.articulated) {
      capability.textContent = "骨骼动作已执行";
      capability.classList.remove("fallback");
    } else {
      capability.textContent = `动作代理预演 · ${event.data.reason || "静态模型无骨骼"}`;
      capability.classList.add("fallback");
    }
  });

  async function runDecision() {
    byId("run-decision").disabled = true;
    try {
      const payload = await jsonRequest("/respond", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: byId("utterance").value, scene: byId("scene").value})});
      state.agentResponse = payload;
      state.traceId = makeId();
      byId("run-id").textContent = state.traceId;
      byId("trace-query").value = state.traceId;
      byId("metric-meme").textContent = payload.recognition.meme_id || "none";
      byId("metric-confidence").textContent = Number(payload.recognition.confidence || 0).toFixed(2);
      byId("metric-action").textContent = payload.action.action_id;
      byId("metric-evidence").textContent = "real_software";
      byId("result-log").textContent = JSON.stringify(payload, null, 2);
      renderStage(payload);
      byId("execute-action").disabled = !payload.recognition.meme_id;
      return payload;
    } catch (error) {
      byId("result-log").textContent = JSON.stringify({error: error.message}, null, 2);
    } finally { byId("run-decision").disabled = false; }
  }

  async function executeAction() {
    if (!state.agentResponse) return;
    byId("execute-action").disabled = true;
    try {
      const payload = await jsonRequest("/hardware/command", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({adapter: byId("adapter").value, agent_response: state.agentResponse, trace_id: state.traceId, idempotency_key: `${state.traceId}-execution`})});
      byId("metric-evidence").textContent = payload.execution.evidence_level;
      byId("result-log").textContent = JSON.stringify(payload, null, 2);
      if (payload.execution.adapter === "dry_run") triggerEmbodiedStage();
      if (payload.execution.motion_fidelity) {
        const capability = byId("motion-capability");
        capability.textContent = `${payload.execution.status} · ${payload.execution.tanyue_motion} · ${payload.execution.motion_fidelity}`;
        capability.classList.toggle("fallback", !payload.execution.executed || payload.execution.motion_fidelity !== "exact");
      }
      await queryTrace();
      return payload;
    } catch (error) {
      byId("result-log").textContent = JSON.stringify({error: error.message}, null, 2);
    } finally { byId("execute-action").disabled = false; }
  }

  async function performNow() {
    const button = byId("perform-now");
    button.disabled = true;
    button.innerHTML = '<i data-lucide="loader-circle"></i>正在接梗…';
    globalThis.lucide?.createIcons();
    try {
      const decision = await runDecision();
      if (!decision?.recognition?.meme_id) return;
      speakResponse();
      await executeAction();
      button.innerHTML = '<i data-lucide="rotate-ccw"></i>再演一次';
    } finally {
      button.disabled = false;
      globalThis.lucide?.createIcons();
    }
  }

  async function queryTrace() {
    const traceId = byId("trace-query").value.trim();
    if (!traceId) return;
    const payload = await jsonRequest(`/observations?trace_id=${encodeURIComponent(traceId)}`);
    const timeline = byId("timeline");
    timeline.innerHTML = "";
    if (!payload.events.length) { timeline.innerHTML = '<div class="empty">No events found</div>'; return; }
    payload.events.forEach((event) => {
      const item = document.createElement("div");
      item.className = "event";
      const title = document.createElement("b");
      title.textContent = `${event.stage} · ${event.evidence_level}`;
      const detail = document.createElement("p");
      detail.textContent = JSON.stringify(event.payload);
      item.append(title, detail);
      timeline.append(item);
    });
  }

  document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  byId("run-decision").addEventListener("click", runDecision);
  byId("perform-now").addEventListener("click", performNow);
  byId("execute-action").addEventListener("click", executeAction);
  byId("replay-voice").addEventListener("click", speakResponse);
  byId("query-trace").addEventListener("click", queryTrace);
  byId("refresh-status").addEventListener("click", refreshStatus);
  Promise.all([refreshStatus(), loadKnowledge()]).catch((error) => { byId("runtime-label").textContent = error.message; });
  globalThis.lucide?.createIcons();
</script>
</body>
</html>"""
