# 柘栯雀魂辅助

柘栯辅助用于雀魂允许的**人机对打训练和牌局复盘**。它在 Windows 桌面窗口显示本地模型的候选动作与局面解读。三麻默认使用 Epsilon-Prism，四麻默认使用 Mortal-S42，最多显示三项推荐。

## 使用

下载 Windows x64 便携 ZIP，解压完整目录，双击 `Zheyou.exe`。模型和运行依赖随包提供。首次打开后在雀魂界面自行登录，后续启动复用本机的登录状态。Windows 需要 Microsoft Edge WebView2 Runtime。 [GitHub Releases](https://github.com/zgozh/zheyou-majsoul/releases/latest)

`Zheyou.exe` 负责启动本地推理服务和界面。`app/ZheyouClient.exe` 是它自动调用的界面程序。

使用前请确认训练场景允许 AI 辅助。请勿用于真人匹配、段位战、赛事、赌博，或其他禁止 AI 辅助的场景。请遵守所在区服的用户协议、房间规则和适用法律。 [雀魂官方规则入口](https://mahjongsoul.com/)

## 免责声明

- 模型输出供练习参考。候选旁的偏好百分比表示模型对动作的相对评分。模型可能给出欠佳建议，使用者负责自己的操作与账号使用。
- 软件按现状提供。在适用法律允许的范围内，发布者不保证服务、兼容性、可用性或推荐准确性。平台可以按其规则处理违规使用。
- 本项目是独立的第三方工具，与雀魂运营方无隶属或授权关系。雀魂及相关名称、标识归各自权利人所有。
- 许可证、第三方声明和改动记录随包提供，见 `LICENSE.txt`、`NOTICE`、`THIRD_PARTY_LICENSES.md` 和 `MODIFICATIONS.md`。
