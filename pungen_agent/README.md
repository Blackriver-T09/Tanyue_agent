# PunGen Agent MVP

PunGen Agent is a small demo framework for meme-aware embodied interaction. It
turns a user utterance into:

1. a recognized meme,
2. an emotion state,
3. a robot/virtual-avatar action JSON payload.

The default MVP path is dependency-free and uses only Python standard library
code, so it can run quickly during a hackathon demo. The optional Azure OpenAI
annotation mode requires the `openai` Python package.

## Quick Start

Run one recognition from the command line:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 python3 -m pungen_agent.cli "棒棒糖"
```

Run the local HTTP adapter:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 python3 -m pungen_agent.server --port 8765
```

Open the production operations console:

```text
http://127.0.0.1:8765/
```

The console provides five operational views: live decision/execution, device
and adapter status, reviewable meme knowledge, trace evidence, and the system
architecture. The original lightweight demo remains available at `/demo`, and
the standalone 3D stage remains at `/viewer`.

Console APIs:

- `GET /system/status`: runtime, adapter, device, knowledge, and evidence status.
- `GET /memes`: reviewable meme catalog used by the recognizer.
- `POST /respond`: utterance to meme, emotion, and bounded action.
- `POST /hardware/command`: validated execution request; currently dry-run only.
- `GET /observations?trace_id=...`: evidence events for one execution trace.

## Production Architecture

```text
Voice/Text -> Input Gateway -> Knowledge + Recognition -> Emotion + Decision
                                                        |
                                                        v
Robot/Arm <- Vendor SDK Adapter <- Safe Execution Module <- Action Library
     |                                      |
     +---------- device acknowledgement ----+
                                            v
                              Observation / Evidence Store
```

Vendor-specific code belongs behind an adapter. A Unitree, robot-arm, or
dexterous-hand adapter consumes `pungen-hardware/v0`, applies its SDK mapping,
and returns an acknowledgement with an evidence level. Only a verified device
acknowledgement may be recorded as `real_robot`; dry-run remains `simulated`.

### Tanyue Character Bridge

PunGen can deliver its canonical actions to the adjacent
`Tanyue_agent-utriee` project through its existing Character Bridge:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 python3 \
  pungen_agent/Tanyue_agent-utriee/character/scripts/character_bridge.py \
  --host 127.0.0.1 --port 8893
```

Select `tanyue_character` in the console before running a performance. The
adapter maps PunGen action IDs to Tanyue motion IDs and posts a batch to
`POST http://127.0.0.1:8893/api/command?wait=1`. The character page acknowledges
the SSE event only after applying the command. `browser_applied` means the VRM
software accepted the motion and sets `executed=true`; missing subscribers or
assets remain `bridge_queued_no_browser_ack` with `executed=false`. Both are
`real_external`, never `real_robot`.

The checked-in Tanyue directory currently lacks the referenced VRM and FBX
files. `cover_face_then_turn_away` therefore maps to `talking_on_phone` with
`motion_fidelity=approximate`: the hand approaches the face, but the missing
turn-away segment still requires a new rigged FBX motion.

## Unitree Voice Demo Runtime

The primary demo path no longer depends on the web avatar:

```text
Microphone -> Aliyun realtime ASR -> PunGen symbolic recognition
           -> G1 voice pack by character_id / built-in TTS -> G1 high-level motion
```

Run one hardware smoke turn first:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
python3 -m pungen_agent.unitree_live en7 \
  --text "你懂不懂机器人" \
  --trump-wav /path/to/licensed-trump-16k-mono.wav
```

Start continuous microphone interaction:

```bash
export DASHSCOPE_API_KEY="..."
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
python3 -m pungen_agent.unitree_live en7 \
  --backend funasr \
  --trump-wav /path/to/licensed-trump-16k-mono.wav \
  --ymca-wav /path/to/licensed-ymca-16k-mono.wav
```

Both audio files must be licensed `16 kHz / mono / PCM16 WAV`. Without a Trump
voice pack, the runtime falls back to G1 built-in TTS. Without an YMCA track,
the dance command can still be issued but music reports `track_not_configured`.

Current G1 SDK mappings are deliberately conservative:

- `accordion_gesture` -> `LocoClient.WaveHand(False)`, approximate.
- `ymca_dance` -> `LocoClient.WaveHand(True)`, approximate.

The checked-in high-level SDK does not expose native accordion or YMCA actions.
Successful RPC return is recorded as a real external command, not confirmed
physical motion. Proactive meme insertion/timing remains a future stage; this
runtime only responds to final ASR turns.

Then call:

```bash
curl -sS http://127.0.0.1:8765/respond \
  -H 'Content-Type: application/json' \
  -d '{"text":"棒棒糖","scene":"龙王短剧"}'
```

Robot adapter teams can inspect the action contract:

```bash
curl -sS http://127.0.0.1:8765/actions
```

Convert an agent response or action into the shared hardware command contract:

```bash
curl -sS http://127.0.0.1:8765/hardware/command \
  -H 'Content-Type: application/json' \
  -d '{"action":{"action_id":"accordion_gesture","intensity":0.78,"duration_s":3.2,"safety":"safe_no_contact"}}'
```

Run a stateful drama turn:

```bash
curl -sS http://127.0.0.1:8765/scene/turn \
  -H 'Content-Type: application/json' \
  -d '{"text":"棒棒糖","scene":"龙王短剧","session_id":"demo","reset":true}'
```

## Response Protocol

The HTTP and CLI output share the same JSON protocol:

```json
{
  "protocol_version": "pungen-agent/v0",
  "input": {
    "text": "棒棒糖",
    "scene": "龙王短剧"
  },
  "recognition": {
    "meme_id": "xinteng_giegie",
    "meme_name": "心疼 giegie / 绿茶委屈名场面",
    "character_id": "doubao",
    "confidence": 0.72,
    "match_type": "symbolic",
    "matched_symbols": ["棒棒糖"],
    "reason": "棒棒糖到 giegie 属于约定俗成的文化符号索引，不是语义相似。"
  },
  "emotion": {
    "dominant_state": "fake_grievance",
    "heart_value": 48.4
  },
  "action": {
    "arm_action": "cover_face_then_turn_away",
    "intensity": 0.72,
    "duration_s": 2.6,
    "line": "你怎么能这样对 giegie",
    "safety": "safe_no_contact"
  }
}
```

Robot and avatar integrations should read `action.arm_action`,
`action.intensity`, `action.duration_s`, and `action.line`. Low-confidence input
returns `idle_listen` with `safe_no_contact`. Voice playback should prefer
`recognition.character_id` first; `meme_id` is no longer the voice selection
key.

`action.performance_tier` controls the demo amplitude: `voice_only` caps motion
at 0.35, `small_motion` caps it at 0.55, and `show_opening` allows a bounded
stage action. Current examples include Crazy Thursday/V我50, 遥遥领先, 我是秦始皇,
and the cyber-Trump accordion opening.

The `/actions` endpoint returns all available action IDs with labels,
descriptions, safety constraints, recommended intensity, duration, and suggested
adapter parameters.

The `/hardware/command` endpoint is intentionally dry-run only. It converts the
common action into target blocks for `unitree_body`, `robot_arm`, and
`dexterous_hand`, and rejects anything except `safe_no_contact`. Device teams
should translate those target blocks inside their SDK-specific bridge; this core
agent does not directly enable motors.

Hardware requests now pass through the Execution Module. Supply stable tracing
and idempotency values when integrating a caller:

```bash
curl -sS http://127.0.0.1:8765/hardware/command \
  -H 'Content-Type: application/json' \
  -d '{
    "trace_id":"demo-turn-001",
    "idempotency_key":"demo-turn-001-arm",
    "action":{"action_id":"accordion_gesture","intensity":0.7,"duration_s":3.2}
  }'
```

The same adapter and idempotency key return the cached result. Reusing a key for
a different action is rejected. Unknown actions cannot self-declare themselves
safe; every action must exist in the reviewed action library.

Execution observations persist under the git-ignored `pungen_agent/runtime/`
directory and can be queried by trace:

```bash
curl -sS 'http://127.0.0.1:8765/observations?trace_id=demo-turn-001'
```

Every observation has an explicit evidence level: `mock`, `simulated`,
`real_software`, `real_external`, `real_robot`, or `production`. The current
`DryRunHardwareAdapter` always emits `simulated`; a successful dry-run must never
be reported as real robot execution.

The `/scene/turn` endpoint keeps a short-drama session alive by `session_id`.
It returns `pungen-scene/v0`, including the current story beat, emotional arc,
robot performance plan, underlying single-turn agent response, and turn history.

For demo-ready meme triggers and a 60-second script, see `MEME_PLAYBOOK.md`.

## Data Model

Edit `pungen_agent/data/memes.json` to add memes. The important fields are:

- `aliases`: direct names or catchphrases.
- `symbols`: non-semantic cultural cues, such as props, colors, gestures, or
  visual details.
- `contexts`: scenes where the meme is appropriate.
- `emotion_deltas`: how the meme changes the emotion state.
- `character_id`: voice pack key to use for playback. Supported keys are
  `dingzhen`, `doubao`, `kobe`, and `trump`. If a meme has no fixed persona,
  pick one of the four and keep it stable in the data file.
- `actions`: robot/avatar action IDs for the adapter team.

This is deliberately a symbolic-cultural index first. LLM reranking and vector
retrieval can be added later, but the demo should keep the current JSON protocol
stable.

## Optional Hyper3D Rodin Assets

The Hyper3D integration can generate GLB/FBX/OBJ assets for virtual characters,
robot props, or stage previews. `Hyper3DConfig.from_env()` checks the process
environment first, then automatically reads the git-ignored project
`.env.local`:

```bash
HYPER3D_API_KEY=YOUR_ROTATED_KEY
```

Checking balance does not submit a generation task:

```bash
python3 -m pungen_agent.hyper3d_cli balance
```

The running PunGen HTTP service exposes the same configured client:

```bash
curl -sS http://127.0.0.1:8765/hyper3d/balance

curl -sS http://127.0.0.1:8765/hyper3d/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"A cyber accordion robot","quality":"low","confirm_cost":true}'
```

The generation endpoint rejects requests unless `confirm_cost` is exactly
`true`, because successful Rodin generation consumes account credits.

Text-to-3D and Image-to-3D submissions are explicit. Without `--wait`, the CLI
returns the task UUID immediately. With `--wait`, it polls until completion and
prints the official download URLs:

```bash
python3 -m pungen_agent.hyper3d_cli text \
  "A stage-ready cyber accordion robot mascot, clean silhouette" \
  --quality low --wait

python3 -m pungen_agent.hyper3d_cli image /absolute/path/to/robot.png \
  --prompt "A safe non-contact stage robot prop" \
  --quality medium --format glb --wait
```

The client uses the asynchronous `/rodin`, `/status`, and `/download` workflow,
sets `tier=Gen-2`, validates enum values before network access, redacts the key
from config representations, and applies request timeouts. It does not submit
anything when the PunGen HTTP demo starts.

## Optional Azure OpenAI Annotation

Keep Azure credentials in environment variables. Do not hard-code API keys in
source files.

```bash
export AZURE_API_BASE="https://YOUR-RESOURCE.cognitiveservices.azure.com"
export AZURE_API_KEY="YOUR_ROTATED_KEY"
export AZURE_DEPLOYMENT_NAME="gpt-5"
export AZURE_API_VERSION="2024-12-01-preview"
```

Use the wrapper directly:

```python
from pungen_agent.azure_llm import azure_inference

content = azure_inference(
    "You are a helpful assistant.",
    "Hello, please tell me a joke.",
)
print(content)
```

Attach it to PunGen Agent only when you want a live LLM call:

```python
from pungen_agent import PunGenAgent
from pungen_agent.azure_llm import azure_inference

agent = PunGenAgent.from_default_library(llm_inference=azure_inference)
response = agent.respond("棒棒糖", scene="龙王短剧")
print(response["llm_annotation"])
```

Or enable it in the local demo server:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 python3 -m pungen_agent.server --port 8765 --use-azure-llm
```
