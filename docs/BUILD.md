# Windows x64 打包

从 [AkagiMS 1.3.2 官方 Windows x64 ZIP](https://github.com/shinkuan/AkagiMS/releases/tag/ms-1.3.2) 取出 `akagi.exe` 放入 `vendor/`。官方 EXE 的 SHA-256 是 `346e5bb3f15d5da683c43ab1176778764b5fe04cc93c985e1962884a79bd2ee5`。

构建机使用 x64 Python 3.12、JDK 21、Windows .NET Framework 的 `csc.exe`，以及 Python 包 `brotli`、`torch`、`numpy` 和 Torch 运行依赖。运行 `python build_portable.py` 前，按 `THIRD_PARTY_LICENSES.md` 准备模型运行时、`local_models/deps` 中的 JPype、Epsilon DJL CPU 缓存、`vendor/python-embed.zip` 和 `vendor/temurin.zip`。后者对应的 `{release, url, digest}` 写入 `vendor/java-release.json`，其中 `digest` 使用 `sha256:` 前缀。

模型和构建依赖在开发机准备。打包时只复制 `defaults/`，个人配置和牌谱目录由运行时另行生成。用户端入口为 `Zheyou.exe`。

验证使用 `python -m unittest discover -s tests` 和 `python tests/verify_portable.py dist/zheyou-majsoul-windows-x64.zip`。便携验收额外使用 `psutil`、`websocket-client` 和 `websockets`，测试仅使用本地模拟页面和牌桌。上传二进制 Release 前按组件许可附上对应源码。
