# Unitree G1 Voice Research Notes

Date: 2026-07-10

## Source Status

Requested support page:

```text
https://support.unitree.com/home/zh/G1_developer/VuiClient_Service
```

The page was saved locally as:

```text
robot_voice/docs/unitree_vui_client_service.html
```

However, command-line access is blocked by Tencent Cloud EdgeOne with status page `567`. English variants were attempted and saved too:

```text
robot_voice/docs/unitree_vui_client_service_en.html
robot_voice/docs/unitree_vui_client_interface_en.html
```

Those files currently contain the block page, not the actual documentation. The actionable local reference is therefore the official GitHub SDK source:

```text
robot_voice/references/unitree_sdk2_python
robot_voice/references/unitree_sdk2
```

GitHub source:

```text
https://github.com/unitreerobotics/unitree_sdk2_python
https://github.com/unitreerobotics/unitree_sdk2
```

## Relevant SDK Modules

For G1 voice output, use the G1 audio service, not the Go2 VUI service.

Python SDK:

```text
unitree_sdk2py.g1.audio.g1_audio_client.AudioClient
unitree_sdk2py.g1.audio.g1_audio_api
example/g1/audio/g1_audio_client_example.py
example/g1/audio/g1_audio_client_play_wav.py
example/g1/audio/wav.py
```

C++ SDK:

```text
include/unitree/robot/g1/audio/g1_audio_client.hpp
include/unitree/robot/g1/audio/g1_audio_api.hpp
example/g1/audio/g1_audio_client_example.cpp
example/g1/audio/wav.hpp
```

Go2/B2 VUI service still exists:

```text
unitree_sdk2py.go2.vui.vui_client.VuiClient
unitree_sdk2py.b2.vui.vui_client.VuiClient
```

The SDK README says VUI covers light and volume control, but G1 has a richer `AudioClient` for voice playback.

## G1 Audio Service

From `g1_audio_api.py` and `g1_audio_api.hpp`:

```text
AUDIO_SERVICE_NAME = "voice"
AUDIO_API_VERSION = "1.0.0.0"

ROBOT_API_ID_AUDIO_TTS = 1001
ROBOT_API_ID_AUDIO_ASR = 1002
ROBOT_API_ID_AUDIO_START_PLAY = 1003
ROBOT_API_ID_AUDIO_STOP_PLAY = 1004
ROBOT_API_ID_AUDIO_GET_VOLUME = 1005
ROBOT_API_ID_AUDIO_SET_VOLUME = 1006
ROBOT_API_ID_AUDIO_SET_RGB_LED = 1010
```

Main methods:

```python
AudioClient.Init()
AudioClient.TtsMaker(text: str, speaker_id: int)
AudioClient.GetVolume()
AudioClient.SetVolume(volume: int)
AudioClient.LedControl(R: int, G: int, B: int)
AudioClient.PlayStream(app_name: str, stream_id: str, pcm_data: bytes)
AudioClient.PlayStop(app_name: str)
```

DDS initialization pattern:

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

ChannelFactoryInitialize(0, network_interface)

client = AudioClient()
client.SetTimeout(10.0)
client.Init()
```

The `network_interface` is the NIC connected to the robot, for example `enp2s0` in the official examples.

## Built-in TTS

Official G1 Python example:

```python
audio_client.TtsMaker("大家好!我是宇树科技人形机器人。语音开发测试例程运行成功！ 很高兴认识你！", 0)
audio_client.TtsMaker("测试完毕，谢谢大家！", 0)
```

C++ example documents speaker IDs:

```cpp
client.TtsMaker("你好。我是宇树科技的机器人。例程启动成功", 0); // Auto play
client.TtsMaker("Hello. I'm a robot from Unitree Robotics...", 1); // English TTS
```

Likely speaker IDs:

- `0`: Chinese/default auto play
- `1`: English TTS

We should confirm on the physical G1.

## Streamed PCM Playback

This is the most relevant path for Tanyue, because `/Tanyue/voice` already produces/streams synthesized audio.

Official requirements from the examples:

- WAV must be PCM format
- 16-bit little-endian samples
- 16 kHz sample rate
- mono channel

Official Python stream helper:

```python
ret_code, _ = client.PlayStream(stream_name, stream_id, chunk)
client.PlayStop(stream_name)
```

Official Python chunk defaults:

```python
chunk_size = 96000
sleep_time = 1.0
```

At 16 kHz, 16-bit mono:

```text
16000 samples/sec * 2 bytes = 32000 bytes/sec
96000 bytes = 3 seconds
```

For lower latency voice interaction, we should not keep the official 3-second chunk size. A practical first target:

```text
chunk_ms = 100 to 200 ms
bytes_per_second = 32000
100 ms chunk = 3200 bytes
200 ms chunk = 6400 bytes
```

Robot testing will decide the smallest stable chunk.

## Upstream Python SDK Caveat

The current Python G1 SDK has this line:

```python
self.tts_index += self.tts_index
```

That keeps `tts_index` at `0` forever. The C++ SDK uses:

```cpp
json.index = tts_index++;
```

When we wrap `TtsMaker`, we should either:

- patch/monkey-patch the local client behavior in our wrapper, or
- call the lower-level `_Call` ourselves with a monotonic index.

Do not rely blindly on the Python SDK's `TtsMaker` index behavior.

## Relationship to `/Tanyue/voice`

`/Tanyue/voice` is not modified. It is useful as a reference for:

- remote TTS API streaming
- PCM chunk writing
- ffplay playback expectations
- LiveKit agent voice pipeline

Important existing format from `voice/remote_cosyvoice2_client.py`:

```text
ffplay -f s16le -ar 24000 -ch_layout mono -
```

So the Tanyue cloud TTS side may emit 24 kHz mono PCM. G1 examples require 16 kHz mono PCM. We will need a resampling step:

```text
24 kHz s16le mono -> 16 kHz s16le mono
```

Possible approaches:

- `ffmpeg` subprocess for robust streaming resample
- Python `audioop.ratecv` for a dependency-light prototype
- `scipy.signal.resample_poly` if scipy is already acceptable

## Proposed Local Architecture

Initial module shape inside `robot_voice`:

```text
robot_voice/
  unitree_g1_voice.py       # high-level wrapper around SDK2 AudioClient
  pcm_resampler.py          # 24k -> 16k PCM conversion helper
  stream_to_robot.py        # CLI test: text/TTS stream/file -> G1 speaker
  README.md
  docs/
  references/
```

High-level wrapper target:

```python
class UnitreeG1Voice:
    def __init__(self, network_interface: str, timeout: float = 10.0): ...
    def set_volume(self, volume: int) -> None: ...
    def get_volume(self) -> int: ...
    def say_builtin(self, text: str, speaker_id: int = 0) -> None: ...
    def play_pcm16_16k_mono(self, pcm: bytes, stream_name: str = "tanyue") -> None: ...
    def stop(self, stream_name: str = "tanyue") -> None: ...
    def led(self, r: int, g: int, b: int) -> None: ...
```

CLI target:

```sh
python robot_voice/stream_to_robot.py --interface enp2s0 --wav path/to/16k_mono.wav
python robot_voice/stream_to_robot.py --interface enp2s0 --text "你好，我是檀月"
python robot_voice/stream_to_robot.py --interface enp2s0 --stream-from-cosyvoice
```

## Open Questions for Robot Testing

- Exact robot network interface name on the development machine.
- Whether the target G1 firmware exposes the `voice` service by default.
- Minimum stable `PlayStream` chunk size.
- Whether `PlayStop(app_name)` or `PlayStop(stream_id)` is correct on G1 Python firmware. Python and C++ examples disagree in naming/comment:
  - Python client method sends `{"app_name": app_name}`
  - Python example calls `PlayStop("example")`
  - C++ example calls `PlayStop(stream_id)` but implementation parameter is `app_name`
- Whether built-in TTS voice quality is good enough, or we should always stream Tanyue/CosyVoice audio.
