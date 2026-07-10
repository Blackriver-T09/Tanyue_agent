# QUICKSTART

## 1. 创建并使用 venv

```bash
cd /home/bob/Documents/temp/utriee/g1loop
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -e '.[sim]'
```

如果 `.venv` 已经存在，直接复用即可。

## 2. 本地 dry-run

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m loop.run_emote --name 惊讶 --dry-run
./.venv/bin/python -m loop.run_emote --name 求饶 --dry-run
./.venv/bin/python -m loop.run_emote --name 轻蔑 --dry-run
```

当前 body 动作映射：

- `惊讶` -> Unitree `hands up`
- `求饶` -> Unitree `two-hand kiss`
- `轻蔑` -> Unitree `reject`

## 3. 生成 live 配置

```bash
./.venv/bin/python -m loop.run_emote --name 惊讶 --write-example-config live_config.json
```

`live_config.json` 重点字段：

- `network_interface`: Unitree DDS 网卡名，例如 `enp3s0`
- `use_live`: 是否默认启用真机模式
- `enable_hands`: 是否初始化 LinkerHand
- `hand_joint`: LinkerHand 型号
- `can`: CAN 口
- `modbus`: RS485 口
- `intensity`: 默认强度
- `repeat`: 默认重复次数

## 4. 真机前检查

先做 import-only：

```bash
./.venv/bin/python -m loop.hw_check
```

再做 live 检查：

```bash
./.venv/bin/python -m loop.hw_check --config live_config.json --live
```

## 5. 真机执行

```bash
./.venv/bin/python -m loop.run_emote --name 惊讶 --config live_config.json --live
./.venv/bin/python -m loop.run_emote --name 求饶 --config live_config.json --live
./.venv/bin/python -m loop.run_emote --name 轻蔑 --config live_config.json --live
```

建议首次只执行：

- `intensity=low`
- `repeat=1`
- 单个动作先从 `惊讶` 开始

## 6. MuJoCo 仿真

当前默认模型：

- `unitree_ros/robots/g1_description/g1_23dof_rev_1_0.urdf`
- `unitree_ros/robots/g1_description/g1_23dof_rev_1_0.xml`

默认仿真会自动生成 fixed-base 派生 XML，再用它启动 MuJoCo。这样不会因为 free-base 且无平衡控制而直接倒地。真机链路不使用这个 fixed-base 变体。

最小验证：

```bash
./.venv/bin/python -m loop.sim.run_sim --headless --steps 1
./.venv/bin/python -m loop.sim.demo_actions --headless --action wave_left_arm --hold-steps 1
```

GUI 仿真：

```bash
./.venv/bin/python -m loop.sim.run_sim
./.venv/bin/python -m loop.sim.demo_actions --action wave_left_arm
./.venv/bin/python -m loop.sim.demo_actions --action twist_waist
./.venv/bin/python -m loop.sim.demo_actions --action arms_open
./.venv/bin/python -m loop.sim.demo_actions --emote 惊讶
./.venv/bin/python -m loop.sim.demo_actions --emote 求饶
./.venv/bin/python -m loop.sim.demo_actions --emote 轻蔑
```

如果你想直接看抽象情绪在仿真里的效果，优先用 `--emote`。它会自动把情感名映射到仿真里的动作序列。
