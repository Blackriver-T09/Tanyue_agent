# Unitree G1 Emote Loop

本项目提供一个本地可运行的抽象动作 loop，body 默认对接 Unitree G1，手部仍使用现有 LinkerHand 适配层。

当前抽象动作映射：

- `惊讶` -> Unitree `hands up` + `open_palm`
- `求饶` -> Unitree `two-hand kiss` + `open_palm`
- `轻蔑` -> Unitree `reject` + `open_palm`

## 快速开始

```bash
pip install -e .
python -m pytest
python -m loop.run_emote --name 惊讶 --dry-run
python -m loop.cli
```

## Live 模式

先生成配置文件：

```bash
python -m loop.run_emote --name 惊讶 --write-example-config live_config.json
```

关键字段：

- `network_interface`: Unitree DDS 网卡名
- `use_live`: 是否默认启用真机模式
- `enable_hands`: 是否初始化 LinkerHand
- `hand_joint`: LinkerHand 型号
- `can`: CAN 口
- `modbus`: RS485 口

真机前建议先跑：

```bash
python -m loop.hw_check
python -m loop.hw_check --config live_config.json --live
python -m loop.run_emote --name 惊讶 --config live_config.json --live
```

## MuJoCo 仿真

仿真默认模型：

- `unitree_ros/robots/g1_description/g1_23dof_rev_1_0.urdf`
- `unitree_ros/robots/g1_description/g1_23dof_rev_1_0.xml`

默认仿真不会直接加载 free-base 原始 XML，而是会自动生成一个 fixed-base 派生 XML 作为 MuJoCo 运行模型，避免 G1 在没有平衡控制器时直接倒地。这个 fixed-base 处理只用于本地仿真，不影响真机。

安装依赖并启动：

```bash
pip install .[sim]
python -m loop.sim.run_sim --headless --steps 100
python -m loop.sim.run_sim
python -m loop.sim.demo_actions --action wave_left_arm
python -m loop.sim.demo_actions --action twist_waist
python -m loop.sim.demo_actions --emote 惊讶
python -m loop.sim.demo_actions --emote 求饶
python -m loop.sim.demo_actions --emote 轻蔑
```
