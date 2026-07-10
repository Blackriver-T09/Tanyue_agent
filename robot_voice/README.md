# Tanyue Robot Voice

宇树机器人发声装置开发目录。当前阶段先保存官方资料、SDK 源码和接口调研结论，后续在这里实现从 Tanyue 语音流到宇树 G1 扬声器的播放链路。

## Local References

- `docs/unitree_vui_client_service.html`
  - 原始 URL: `https://support.unitree.com/home/zh/G1_developer/VuiClient_Service`
  - 当前命令行抓取结果为 Tencent EdgeOne 567 拦截页，保留用于记录抓取状态。
- `docs/unitree_vui_client_service_en.html`
  - 英文同页抓取尝试，同样被拦截。
- `references/unitree_github_repos.json`
  - Unitree Robotics GitHub 组织 repo 列表。
- `references/unitree_sdk2_python/`
  - 官方 Python SDK2 浅克隆。
- `references/unitree_sdk2/`
  - 官方 C++ SDK2 浅克隆。
- `docs/unitree_voice_research.md`
  - 当前对 G1 AudioClient / VUI / 音频播放接口的本地总结。

## Working Direction

优先走 G1 的 `AudioClient`，而不是 Go2/B2 的 `VuiClient`：

- G1 发声服务名是 `voice`
- 支持内置 TTS
- 支持音量读取/设置
- 支持 RGB LED 控制
- 支持 16 kHz mono PCM 流式播放

`/Tanyue/voice` 目录只作为音频流参考，不在这里修改。
