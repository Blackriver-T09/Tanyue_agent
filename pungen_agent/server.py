from __future__ import annotations

import argparse
import json
import mimetypes
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .action_library import build_action_library_payload
from .agent import PunGenAgent
from .azure_llm import azure_inference
from .console import render_console_page
from .drama import ShortDramaSession
from .execution import ExecutionError, ExecutionModule, ExecutionRequest
from .hardware_adapter import (
    DryRunHardwareAdapter,
)
from .hyper3d import Hyper3DClient, Hyper3DConfig, Hyper3DError
from .observation import JsonlObservationRecorder
from .operations import build_meme_catalog_payload, build_system_status_payload
from .tanyue_adapter import TanyueCharacterAdapter


DEFAULT_SESSION_ID = "default"
PACKAGE_ROOT = Path(__file__).resolve().parent
ASSET_ROOT = PACKAGE_ROOT / "assets"
STATIC_ROOT = PACKAGE_ROOT / "static"


def make_execution_module(
    observation_path: str | Path | None = None,
) -> ExecutionModule:
    path = Path(observation_path) if observation_path is not None else (
        PACKAGE_ROOT / "runtime" / "observations.jsonl"
    )
    return ExecutionModule(
        adapters=[DryRunHardwareAdapter(), TanyueCharacterAdapter()],
        recorder=JsonlObservationRecorder(path),
    )


def make_agent(
    use_azure_llm: bool = False,
    llm_inference=None,
) -> PunGenAgent:
    if llm_inference is None and use_azure_llm:
        llm_inference = azure_inference
    return PunGenAgent.from_default_library(llm_inference=llm_inference)


def render_demo_page(default_text: str = "棒棒糖") -> str:
    safe_default = escape(default_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PunGen Agent Demo</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1d232c;
      --muted: #667085;
      --line: #d9dee8;
      --accent: #c83f49;
      --accent-2: #256a8a;
      --ok: #2e7d5b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 20px 36px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 30px;
      line-height: 1.15;
    }}
    .sub {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .viewer-link {{
      color: var(--accent-2);
      font-size: 14px;
      text-decoration: none;
    }}
    .viewer-link:hover {{ text-decoration: underline; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
      gap: 18px;
      margin-top: 20px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    label {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin: 14px 0 6px;
    }}
    input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 11px 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }}
    textarea {{
      min-height: 92px;
      resize: vertical;
    }}
    button {{
      margin-top: 14px;
      width: 100%;
      border: 0;
      border-radius: 6px;
      padding: 12px 14px;
      background: var(--ink);
      color: #fff;
      font: inherit;
      cursor: pointer;
    }}
    button:disabled {{
      background: #98a2b3;
      cursor: wait;
    }}
    .button-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .secondary {{
      background: #475467;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .chip {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 10px;
      background: #fff;
      color: var(--accent-2);
      font-size: 13px;
      cursor: pointer;
    }}
    .result-top {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 78px;
      background: #fbfcfd;
    }}
    .metric strong {{
      display: block;
      font-size: 18px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }}
    .metric span {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .bars {{
      display: grid;
      gap: 10px;
      margin: 12px 0 16px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px 1fr 44px;
      gap: 10px;
      align-items: center;
      font-size: 13px;
    }}
    .bar {{
      height: 9px;
      background: #edf0f4;
      border-radius: 999px;
      overflow: hidden;
    }}
    .fill {{
      height: 100%;
      width: 0%;
      background: var(--accent);
    }}
    pre {{
      margin: 0;
      padding: 14px;
      background: #111827;
      color: #e6edf3;
      border-radius: 8px;
      overflow: auto;
      min-height: 240px;
      font-size: 12px;
      line-height: 1.45;
    }}
    .reason {{
      border-left: 3px solid var(--ok);
      padding-left: 12px;
      color: var(--muted);
      margin: 8px 0 16px;
      min-height: 22px;
    }}
    @media (max-width: 820px) {{
      header, .grid, .result-top {{ grid-template-columns: 1fr; display: grid; }}
      header {{ align-items: start; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>PunGen Agent</h1>
        <p class="sub">梗识别 -> 情感状态 -> 机械臂动作协议</p>
      </div>
      <a class="viewer-link" href="/viewer">Open 3D Viewer</a>
    </header>
    <div class="grid">
      <section>
        <form id="demo-form">
          <label for="text">用户输入</label>
          <textarea id="text">{safe_default}</textarea>
          <label for="scene">场景</label>
          <input id="scene" value="龙王短剧">
          <div class="button-row">
            <button id="submit" type="submit">Run Recognition</button>
            <button id="drama-turn" type="button">Drama Turn</button>
          </div>
          <button id="reset-drama" class="secondary" type="button">Reset Drama</button>
        </form>
        <div class="chips">
          <button class="chip" type="button" data-text="棒棒糖">棒棒糖</button>
          <button class="chip" type="button" data-text="黑白背带裤加篮球">篮球背带裤</button>
          <button class="chip" type="button" data-text="龙王你怎么能这样对 giegie">龙王 giegie</button>
          <button class="chip" type="button" data-text="退退退，龙王大人别过来">退退退</button>
          <button class="chip" type="button" data-text="你要不要听听你在说什么">离谱反问</button>
          <button class="chip" type="button" data-text="喝碗丝瓜汤冷静一下">丝瓜汤</button>
          <button class="chip" type="button" data-text="高雅人士企鹅舞安排一下">高雅人士企鹅舞</button>
          <button class="chip" type="button" data-text="我是秦始皇，今天星期四，V我50">疯狂星期四</button>
          <button class="chip" type="button" data-text="你们这个机器人用了什么技术？">遥遥领先</button>
          <button class="chip" type="button" data-text="我是秦始皇，给我打钱，封你做大将军">秦始皇</button>
          <button class="chip" type="button" data-text="No one knows Robot better than me，播放 YMCA">赛博川王开场</button>
          <button class="chip" type="button" data-text="这一波必须致敬">致敬</button>
          <button class="chip" type="button" data-text="今天下午三点开会">无梗安全待机</button>
        </div>
      </section>
      <section>
        <div class="result-top">
          <div class="metric"><strong id="meme">-</strong><span>meme_id</span></div>
          <div class="metric"><strong id="state">-</strong><span>dominant_state</span></div>
          <div class="metric"><strong id="action">-</strong><span>arm_action</span></div>
        </div>
        <div class="reason" id="reason">等待输入。</div>
        <div class="bars" id="bars"></div>
        <pre id="json">{{}}</pre>
      </section>
    </div>
  </main>
  <script>
    const form = document.querySelector("#demo-form");
    const text = document.querySelector("#text");
    const scene = document.querySelector("#scene");
    const submit = document.querySelector("#submit");
    const dramaTurn = document.querySelector("#drama-turn");
    const resetDrama = document.querySelector("#reset-drama");
    const jsonBox = document.querySelector("#json");
    const meme = document.querySelector("#meme");
    const state = document.querySelector("#state");
    const action = document.querySelector("#action");
    const reason = document.querySelector("#reason");
    const bars = document.querySelector("#bars");

    function renderBars(emotion) {{
      const dimensions = emotion.dimensions || {{}};
      const rows = Object.entries(dimensions)
        .filter(([, value]) => value > 0)
        .sort((a, b) => b[1] - a[1]);
      const heart = emotion.heart_value ?? 0;
      const html = [
        ["heart_value", heart / 100, heart.toFixed ? heart.toFixed(1) : heart]
      ].concat(rows).map(([name, raw, label]) => {{
        const value = Number(raw);
        const pct = Math.max(0, Math.min(100, value * 100));
        const shown = label ?? value.toFixed(2);
        return `<div class="bar-row"><span>${{name}}</span><div class="bar"><div class="fill" style="width:${{pct}}%"></div></div><span>${{shown}}</span></div>`;
      }}).join("");
      bars.innerHTML = html;
    }}

    function render(payload) {{
      const agentPayload = payload.agent_response || payload;
      meme.textContent = agentPayload.recognition.meme_id || "none";
      state.textContent = agentPayload.emotion.dominant_state;
      action.textContent = agentPayload.action.arm_action;
      if (payload.protocol_version === "pungen-scene/v0") {{
        reason.textContent = `${{payload.beat.label}}: ${{payload.performance_plan.stage_direction}}`;
      }} else {{
        reason.textContent = agentPayload.recognition.reason || "";
      }}
      renderBars(agentPayload.emotion);
      jsonBox.textContent = JSON.stringify(payload, null, 2);
    }}

    function setBusy(isBusy) {{
      submit.disabled = isBusy;
      dramaTurn.disabled = isBusy;
      resetDrama.disabled = isBusy;
    }}

    async function run() {{
      setBusy(true);
      try {{
        const response = await fetch("/respond", {{
          method: "POST",
          headers: {{"Content-Type": "application/json"}},
          body: JSON.stringify({{text: text.value, scene: scene.value}})
        }});
        render(await response.json());
      }} finally {{
        setBusy(false);
      }}
    }}

    async function runDrama(reset=false) {{
      setBusy(true);
      try {{
        const response = await fetch("/scene/turn", {{
          method: "POST",
          headers: {{"Content-Type": "application/json"}},
          body: JSON.stringify({{
            text: text.value,
            scene: scene.value,
            session_id: "browser-demo",
            reset
          }})
        }});
        render(await response.json());
      }} finally {{
        setBusy(false);
      }}
    }}

    form.addEventListener("submit", (event) => {{
      event.preventDefault();
      run();
    }});
    dramaTurn.addEventListener("click", () => runDrama(false));
    resetDrama.addEventListener("click", () => runDrama(true));
    document.querySelectorAll(".chip").forEach((button) => {{
      button.addEventListener("click", () => {{
        text.value = button.dataset.text;
        run();
      }});
    }});
    run();
  </script>
</body>
</html>"""


def render_3d_viewer_page() -> str:
    model_url = "/assets/hyper3d/cyber_trump_gen2_color_v2/base_basic_pbr.glb"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>赛博川王 3D Viewer</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
    body {{
      background: #101214;
      color: #f4f5f7;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    #viewer-canvas {{ display: block; width: 100%; height: 100%; touch-action: none; }}
    header {{
      position: fixed;
      inset: 0 0 auto 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 18px 22px;
      pointer-events: none;
    }}
    h1 {{ margin: 0; font-size: 22px; line-height: 1.2; font-weight: 700; }}
    .tag {{ color: #efb34c; font-size: 13px; }}
    .toolbar {{
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 3;
      display: flex;
      gap: 8px;
    }}
    button {{
      width: 42px;
      height: 42px;
      border: 1px solid #4b535c;
      border-radius: 6px;
      background: #171b1f;
      color: #f4f5f7;
      font: inherit;
      font-size: 17px;
      cursor: pointer;
    }}
    button:hover {{ border-color: #efb34c; }}
    #status {{
      position: fixed;
      left: 22px;
      bottom: 22px;
      z-index: 2;
      color: #aab2bb;
      font-size: 13px;
    }}
    #gesture-proxy {{
      position: fixed;
      inset: 0;
      z-index: 4;
      display: none;
      place-items: center;
      pointer-events: none;
      background: rgba(8, 10, 12, .2);
    }}
    #gesture-proxy.active {{ display: grid; }}
    .proxy-figure {{ position: relative; width: 180px; height: 250px; transform-origin: 50% 80%; }}
    .proxy-head {{ position: absolute; left: 55px; top: 10px; width: 70px; height: 78px; border: 5px solid #f4f5f7; border-radius: 46%; }}
    .proxy-body {{ position: absolute; left: 35px; top: 92px; width: 110px; height: 145px; border: 5px solid #f4f5f7; border-radius: 42px 42px 12px 12px; }}
    .proxy-arm {{ position: absolute; left: 18px; top: 117px; width: 92px; height: 20px; border-radius: 10px; background: #efb34c; transform-origin: 10px 10px; }}
    #gesture-proxy.active .proxy-arm {{ animation: cover-face 2.6s ease-in-out forwards; }}
    #gesture-proxy.active .proxy-figure {{ animation: turn-away 2.6s ease-in-out forwards; }}
    .proxy-label {{ position: absolute; top: 250px; width: 260px; left: -40px; text-align: center; color: #efb34c; font-size: 13px; font-weight: 700; }}
    @keyframes cover-face {{ 0%, 12% {{ transform: rotate(0deg); }} 42%, 72% {{ transform: translate(50px, -70px) rotate(-42deg); }} 100% {{ transform: translate(38px, -55px) rotate(-30deg); }} }}
    @keyframes turn-away {{ 0%, 55% {{ transform: rotateY(0); }} 100% {{ transform: rotateY(58deg) translateX(35px); }} }}
  </style>
  <script type="importmap">
    {{"imports": {{"three": "/static/vendor/three.module.js"}}}}
  </script>
</head>
<body>
  <header><h1>赛博川王</h1><span class="tag">Gen-2 · PBR · GLB</span></header>
  <canvas id="viewer-canvas"></canvas>
  <div id="status">Loading model...</div>
  <div id="gesture-proxy" aria-hidden="true"><div class="proxy-figure"><div class="proxy-head"></div><div class="proxy-body"></div><div class="proxy-arm"></div><div class="proxy-label">动作代理预演：捂脸 → 转身</div></div></div>
  <div class="toolbar">
    <button id="toggle-spin" type="button" title="暂停或继续自动旋转">Ⅱ</button>
    <button id="reset-view" type="button" title="重置视角">⌂</button>
  </div>
  <script type="module">
    import * as THREE from "three";
    import {{ GLTFLoader }} from "/static/vendor/GLTFLoader.js";
    import {{ OrbitControls }} from "/static/vendor/OrbitControls.js";

    const canvas = document.querySelector("#viewer-canvas");
    const status = document.querySelector("#status");
    const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.shadowMap.enabled = true;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101214);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 100);
    const defaultCamera = new THREE.Vector3(4.8, 2.6, 6.8);
    camera.position.copy(defaultCamera);

    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.target.set(0, 1.75, 0);
    controls.minDistance = 3.2;
    controls.maxDistance = 12;

    scene.add(new THREE.HemisphereLight(0xcfe7ff, 0x24201d, 2.1));
    const key = new THREE.DirectionalLight(0xffffff, 4.2);
    key.position.set(4, 7, 5);
    key.castShadow = true;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xef6a55, 3.1);
    rim.position.set(-5, 4, -4);
    scene.add(rim);
    const fill = new THREE.DirectionalLight(0x5aa9e6, 2.3);
    fill.position.set(-4, 2, 5);
    scene.add(fill);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(4.8, 96),
      new THREE.MeshStandardMaterial({{ color: 0x1a1e22, roughness: 0.82, metalness: 0.05 }})
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const root = new THREE.Group();
    scene.add(root);
    let spinning = true;
    let activePerformance = null;

    new GLTFLoader().load(
      "{model_url}",
      (gltf) => {{
        const model = gltf.scene;
        model.traverse((node) => {{
          if (node.isMesh) {{ node.castShadow = true; node.receiveShadow = true; }}
        }});
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const scale = 3.7 / Math.max(size.y, 0.001);
        model.scale.setScalar(scale);
        model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
        root.add(model);
        status.textContent = "cyber_trump · accordion_gesture";
        document.body.dataset.modelReady = "true";
      }},
      undefined,
      (error) => {{
        status.textContent = "Model failed to load";
        document.body.dataset.modelReady = "error";
        console.error(error);
      }}
    );

    function resize() {{
      const width = window.innerWidth;
      const height = window.innerHeight;
      renderer.setSize(width, height, false);
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
    }}
    window.addEventListener("resize", resize);
    resize();

    document.querySelector("#toggle-spin").addEventListener("click", (event) => {{
      spinning = !spinning;
      event.currentTarget.textContent = spinning ? "Ⅱ" : "▶";
    }});
    document.querySelector("#reset-view").addEventListener("click", () => {{
      camera.position.copy(defaultCamera);
      controls.target.set(0, 1.75, 0);
      root.rotation.set(0, 0, 0);
      controls.update();
    }});

    window.addEventListener("message", (event) => {{
      if (event.origin !== window.location.origin || event.data?.type !== "pungen:perform") return;
      const action = event.data.action || {{}};
      const articulated = false;
      const proxy = document.querySelector("#gesture-proxy");
      if ((action.action_id || action.arm_action) === "cover_face_then_turn_away") {{
        proxy.classList.remove("active");
        void proxy.offsetWidth;
        proxy.classList.add("active");
        window.setTimeout(() => proxy.classList.remove("active"), 2700);
      }}
      activePerformance = {{
        actionId: action.action_id || action.arm_action || "idle_listen",
        intensity: Math.max(0.15, Math.min(1, Number(action.intensity || 0.35))),
        startedAt: globalThis.performance.now(),
        durationMs: Math.max(1200, Number(action.duration_s || 2) * 1000),
      }};
      spinning = false;
      status.textContent = `Performing · ${{activePerformance.actionId}}`;
      event.source?.postMessage({{
        type: "pungen:performance-status",
        actionId: activePerformance.actionId,
        articulated,
        reason: "当前 GLB 为静态单网格，使用动作代理预演",
      }}, event.origin);
    }});

    function animate() {{
      requestAnimationFrame(animate);
      if (activePerformance && root.children.length) {{
        const elapsed = globalThis.performance.now() - activePerformance.startedAt;
        const phase = elapsed / activePerformance.durationMs;
        const wave = Math.sin(phase * Math.PI * 4) * activePerformance.intensity;
        if (activePerformance.actionId.includes("nod")) {{
          root.rotation.x = wave * 0.13;
        }} else if (activePerformance.actionId.includes("turn_away")) {{
          root.rotation.y = Math.sin(Math.min(1, phase) * Math.PI) * 0.65;
        }} else {{
          root.rotation.z = wave * 0.1;
          root.position.y = Math.abs(Math.sin(phase * Math.PI * 3)) * 0.1 * activePerformance.intensity;
        }}
        if (elapsed >= activePerformance.durationMs) {{
          activePerformance = null;
          root.rotation.set(0, 0, 0);
          root.position.set(0, 0, 0);
          status.textContent = "Performance complete";
        }}
      }} else if (spinning && root.children.length) root.rotation.y += 0.004;
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();
  </script>
</body>
</html>"""


def resolve_public_asset(request_path: str) -> Path | None:
    roots = {
        "/assets/": ASSET_ROOT,
        "/static/": STATIC_ROOT,
    }
    for prefix, root in roots.items():
        if not request_path.startswith(prefix):
            continue
        relative = unquote(request_path[len(prefix) :])
        if not relative or ".." in Path(relative).parts:
            return None
        candidate = (root / relative).resolve()
        if root.resolve() not in candidate.parents or not candidate.is_file():
            return None
        return candidate
    return None


def build_response_payload(
    request_payload: dict[str, Any],
    agent: PunGenAgent | None = None,
) -> tuple[int, dict[str, Any]]:
    text = request_payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return 400, {"error": "Request JSON must include a non-empty text field."}

    scene = request_payload.get("scene", "")
    if scene is None:
        scene = ""
    if not isinstance(scene, str):
        return 400, {"error": "scene must be a string when provided."}

    base_agent = agent or PunGenAgent.from_default_library()
    stateless_agent = PunGenAgent(
        base_agent.recognizer,
        action_planner=base_agent.action_planner,
        llm_inference=base_agent.llm_inference,
    )
    return 200, stateless_agent.respond(text.strip(), scene=scene.strip())


def build_scene_turn_payload(
    request_payload: dict[str, Any],
    session_store: dict[str, ShortDramaSession] | None = None,
    use_azure_llm: bool = False,
) -> tuple[int, dict[str, Any]]:
    text = request_payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return 400, {"error": "Request JSON must include a non-empty text field."}

    scene = request_payload.get("scene") or "龙王短剧"
    if not isinstance(scene, str):
        return 400, {"error": "scene must be a string when provided."}
    speaker = request_payload.get("speaker") or "player"
    if not isinstance(speaker, str):
        return 400, {"error": "speaker must be a string when provided."}

    session_id = request_payload.get("session_id") or DEFAULT_SESSION_ID
    if not isinstance(session_id, str):
        return 400, {"error": "session_id must be a string when provided."}

    store = session_store if session_store is not None else PunGenRequestHandler.scene_sessions
    if request_payload.get("reset") or session_id not in store:
        store[session_id] = ShortDramaSession(
            scene=scene.strip() or "龙王短剧",
            agent=make_agent(use_azure_llm=use_azure_llm),
        )

    session = store[session_id]
    return 200, session.step(text.strip(), speaker=speaker.strip() or "player")


def build_hardware_command_payload(
    request_payload: dict[str, Any],
    execution_module: ExecutionModule | None = None,
) -> tuple[int, dict[str, Any]]:
    action = request_payload.get("action")
    agent_response = request_payload.get("agent_response")
    if action is None and isinstance(agent_response, dict):
        action = agent_response.get("action")
    if action is None and (
        "action_id" in request_payload or "arm_action" in request_payload
    ):
        action = request_payload
    if not isinstance(action, dict):
        return 400, {"error": "Request JSON must include an action object."}

    targets = request_payload.get("targets")
    if targets is not None and (
        not isinstance(targets, list)
        or not all(isinstance(target, str) and target for target in targets)
    ):
        return 400, {"error": "targets must be a list of non-empty strings."}

    trace_id = request_payload.get("trace_id") or str(uuid.uuid4())
    idempotency_key = request_payload.get("idempotency_key") or str(uuid.uuid4())
    if not isinstance(trace_id, str) or not trace_id:
        return 400, {"error": "trace_id must be a non-empty string."}
    if not isinstance(idempotency_key, str) or not idempotency_key:
        return 400, {"error": "idempotency_key must be a non-empty string."}

    execution = execution_module or ExecutionModule(
        adapters=[DryRunHardwareAdapter(), TanyueCharacterAdapter()]
    )
    adapter_name = request_payload.get("adapter") or "dry_run"
    if not isinstance(adapter_name, str) or not adapter_name:
        return 400, {"error": "adapter must be a non-empty string."}
    request = ExecutionRequest(
        action_id=str(action.get("action_id") or action.get("arm_action") or ""),
        intensity=action.get("intensity", 0.2),
        duration_s=action.get("duration_s", 1.0),
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        targets=tuple(targets or ("unitree_body", "robot_arm", "dexterous_hand")),
    )
    try:
        result = execution.execute(request, adapter_name=adapter_name)
    except ExecutionError as exc:
        return 400, {"error": str(exc)}
    command = result["command"]
    public_result = {key: value for key, value in result.items() if key != "command"}
    response_payload = {
        "protocol_version": "pungen-hardware-response/v0",
        "command": command,
        "execution": public_result,
    }
    if adapter_name == "dry_run":
        response_payload["dry_run"] = public_result
    return 200, response_payload


def build_hyper3d_balance_payload(
    client: Hyper3DClient | None = None,
) -> tuple[int, dict[str, Any]]:
    try:
        active_client = client or Hyper3DClient(Hyper3DConfig.from_env())
        return 200, {"configured": True, "balance": active_client.check_balance()}
    except ValueError as exc:
        return 503, {"configured": False, "error": str(exc)}
    except Hyper3DError as exc:
        return 502, {"configured": True, "error": str(exc)}


def build_hyper3d_generation_payload(
    request_payload: dict[str, Any],
    client: Hyper3DClient | None = None,
) -> tuple[int, dict[str, Any]]:
    if request_payload.get("confirm_cost") is not True:
        return 400, {
            "error": "Set confirm_cost to true to submit a billable Hyper3D task."
        }
    prompt = request_payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return 400, {"error": "Request JSON must include a non-empty prompt field."}

    options = {
        "quality": request_payload.get("quality", "medium"),
        "mesh_mode": request_payload.get("mesh_mode", "Quad"),
        "geometry_file_format": request_payload.get("format", "glb"),
        "material": request_payload.get("material", "PBR"),
    }
    try:
        active_client = client or Hyper3DClient(Hyper3DConfig.from_env())
        submission = active_client.submit_text(prompt.strip(), **options)
    except ValueError as exc:
        return 503, {"configured": False, "error": str(exc)}
    except Hyper3DError as exc:
        return 502, {"configured": True, "error": str(exc)}
    return 202, {
        "protocol_version": "pungen-hyper3d/v0",
        "status": "submitted",
        "task_uuid": submission.task_uuid,
        "subscription_key": submission.subscription_key,
        "message": submission.message,
    }


def build_observation_payload(
    trace_id: str,
    execution_module: ExecutionModule,
) -> tuple[int, dict[str, Any]]:
    if not isinstance(trace_id, str) or not trace_id:
        return 400, {"error": "trace_id query parameter is required."}
    events = execution_module.recorder.list_events(trace_id=trace_id)
    summary: dict[str, int] = {}
    for event in events:
        level = event.evidence_level.value
        summary[level] = summary.get(level, 0) + 1
    return 200, {
        "protocol_version": "pungen-observations/v0",
        "trace_id": trace_id,
        "evidence_summary": summary,
        "events": [event.to_dict() for event in events],
    }


class PunGenRequestHandler(BaseHTTPRequestHandler):
    agent = PunGenAgent.from_default_library()
    scene_sessions: dict[str, ShortDramaSession] = {}
    use_azure_llm = False
    execution_module = make_execution_module()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = parsed.path
        if request_path == "/viewer":
            body = render_3d_viewer_page().encode("utf-8")
            self._write_bytes(200, body, "text/html; charset=utf-8")
            return
        public_asset = resolve_public_asset(request_path)
        if public_asset is not None:
            content_type = mimetypes.guess_type(public_asset.name)[0]
            self._write_bytes(
                200,
                public_asset.read_bytes(),
                content_type or "application/octet-stream",
            )
            return
        if request_path == "/observations":
            trace_id = (parse_qs(parsed.query).get("trace_id") or [""])[0]
            status, payload = build_observation_payload(
                trace_id,
                self.execution_module,
            )
            self._write_json(status, payload)
            return
        if request_path == "/system/status":
            self._write_json(200, build_system_status_payload(self.execution_module))
            return
        if request_path == "/memes":
            self._write_json(200, build_meme_catalog_payload())
            return
        if request_path == "/hyper3d/balance":
            status, payload = build_hyper3d_balance_payload()
            self._write_json(status, payload)
            return
        if request_path == "/actions":
            self._write_json(200, build_action_library_payload())
            return
        if request_path not in {"/", "/console", "/demo"}:
            self._write_json(
                404,
                {
                    "error": (
                        "Unknown endpoint. Use GET /console, GET /system/status, "
                        "GET /memes, GET /actions, or POST /respond."
                    )
                },
            )
            return
        page = render_demo_page() if request_path == "/demo" else render_console_page()
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path not in {
            "/respond",
            "/scene/turn",
            "/hardware/command",
            "/hyper3d/generate",
        }:
            self._write_json(
                404,
                {
                    "error": (
                        "Unknown endpoint. Use POST /respond, POST /scene/turn, "
                        "POST /hardware/command, or POST /hyper3d/generate."
                    )
                },
            )
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._write_json(400, {"error": f"Invalid JSON: {exc.msg}"})
            return
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "Request JSON must be an object."})
            return

        if self.path == "/scene/turn":
            status, response = build_scene_turn_payload(
                payload,
                session_store=self.scene_sessions,
                use_azure_llm=self.use_azure_llm,
            )
        elif self.path == "/hardware/command":
            status, response = build_hardware_command_payload(
                payload,
                execution_module=self.execution_module,
            )
        elif self.path == "/hyper3d/generate":
            status, response = build_hyper3d_generation_payload(payload)
        else:
            status, response = build_response_payload(payload, agent=self.agent)
        self._write_json(status, response)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._write_bytes(status, body, "application/json; charset=utf-8")

    def _write_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765, use_azure_llm: bool = False) -> None:
    PunGenRequestHandler.agent = make_agent(use_azure_llm=use_azure_llm)
    PunGenRequestHandler.use_azure_llm = use_azure_llm
    PunGenRequestHandler.scene_sessions = {}
    PunGenRequestHandler.execution_module = make_execution_module()
    server = ThreadingHTTPServer((host, port), PunGenRequestHandler)
    print(f"PunGen Agent server listening on http://{host}:{port}")
    print("POST /respond with JSON: {\"text\": \"棒棒糖\", \"scene\": \"龙王短剧\"}")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PunGen Agent HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--use-azure-llm",
        action="store_true",
        help="Attach live Azure OpenAI annotation using environment variables.",
    )
    args = parser.parse_args(argv)
    run_server(host=args.host, port=args.port, use_azure_llm=args.use_azure_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
