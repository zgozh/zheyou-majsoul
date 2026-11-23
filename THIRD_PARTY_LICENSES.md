# 许可与对应源码

| 组件 | 许可或来源 |
| --- | --- |
| AkagiMS 1.3.2 和柘栯客户端改动 | Apache-2.0，见 `LICENSE.txt`、`NOTICE` 和 `MODIFICATIONS.md`。上游为 [AkagiMS 1.3.2](https://github.com/shinkuan/AkagiMS/releases/tag/ms-1.3.2)。 |
| Epsilon-Prism 3P u3-v413 权重 | MIT，见 `app/models/epsilon-3p/LICENSE` 和[权重发布页](https://github.com/KoutaChan/Epsilon/releases/tag/epsilon-prism-3p-u3-v413)。 |
| Epsilon 运行时和柘栯适配器 | GPL-3.0。上游[对应源码](https://github.com/KoutaChan/Epsilon/tree/epsilon-prism-3p-u3-v413)，柘栯适配器见 `local_models/EpsilonMjai.java`、`local_models/epsilon_worker.py`。 |
| Mortal-S42.8k 权重 | Apache-2.0，见[模型卡](https://huggingface.co/haor/Mortal-S42)。 |
| Mortal 推理运行时和 HTTP 服务 | AGPL-3.0-or-later。见随包的 Mortal `NOTICE`、`runtime/LICENSE`、[上游构建与模型文件](https://huggingface.co/haor/Mortal-S42/tree/main)、[Mortal 对应源码版本](https://github.com/Equim-chan/Mortal/tree/0cff2b52982be5b1163aa9a62fb01f03ce91e0d2)与 `local_models/server.py`。 |
| Python、PyTorch 和相关包 | 保留各自许可文本。便携运行时目录包含 Python 原版许可证及 Python 包的发行元数据。 |
| Eclipse Temurin、JPype、DJL | 保留随运行时提供的许可与声明。具体二进制版本见 `app/runtime/VERSIONS.json`。 |

公开分发受 GPL 或 AGPL 覆盖的二进制时，须同时向接收者提供对应源码或按适用条款提供取得对应源码的方式，包含构建该版本所需的修改与脚本。
