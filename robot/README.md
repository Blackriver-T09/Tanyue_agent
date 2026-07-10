# G1 Robot Actions

This directory contains the physical G1 action programs used by PunGen. The
canonical runtime lives in `../pungen_agent/unitree_live.py`.

## Build

The C++ Unitree SDK2 is required. The checked-in `robot_voice/references/`
directory currently contains only the Python SDK, so this target cannot be
built until the C++ SDK is installed.

```bash
cmake -S robot -B robot/build -DUNITREE_SDK2_DIR=/path/to/unitree_sdk2
cmake --build robot/build --target g1_trump_accordion
```

## Manual Safety Test

Manual mode pauses before every arm-control stage:

```bash
robot/build/g1_trump_accordion <robot-interface>
```

## PunGen Integration

Only after the manual test succeeds with a clear robot workspace, enable the
low-level action from the voice runtime:

```bash
python3 -m pungen_agent.unitree_live <robot-interface> \
  --accordion-bin robot/build/g1_trump_accordion \
  --enable-low-level-accordion \
  --trump-wav /path/to/trump-16k-mono.wav
```

The Python wrapper invokes the binary with `--auto` and the explicit
`--i-understand-low-level-arm-risk` acknowledgement. Without both flags the C++
program refuses automatic arm takeover. It also refuses to start if no
`rt/lowstate` message is received within five seconds.
