---
license: mit
language:
- ja
- en
tags:
- mahjong
- riichi-mahjong
- reinforcement-learning
- self-play
---

# Epsilon-Prism 3P u3-v413

3人打ちのリーチ麻雀（天鳳の三人打ち・東南戦）を打つAIの重みです。このモデルは、人の牌譜を使わず、自己対戦だけで学習しました。

- 作者: KoutaChan
- コード: [KoutaChan/Epsilon](https://github.com/KoutaChan/Epsilon)（GNU GPL v3.0）
- 重み: MIT License（[`LICENSE`](LICENSE)）

> [!WARNING]
> オンライン対局や大会での不正、賭博には使わないでください（[悪用の禁止](#悪用の禁止)）。

このモデルはプレリリースです。問題がありましたら、GitHubのIssuesなどで報告いただけると幸いです。

## 使い方

**Epsilon AI Reviewer（Windows）**: `Epsilon-AI-Reviewer-Setup-win-x64.exe`でインストールします。このモデルと、Epsilon-Prism v760（4人打ち）が既定で入っています。

**jar（Windows x64）**: Java 21を入れ、jarと同じフォルダーに`epsilon-prism-3p-u3-v413.zip`を展開して、次を実行します。

```powershell
java -jar epsilon-prism-3p-1.0-SNAPSHOT-all.jar evaluate --preset smoke --set run.variant=TENHOU_3P --set run.seed=1 --set evaluation.tables.smoke.walls=96 --model epsilon-prism-3p-u3-v413 --table smoke --out eval
```

- Prismを1席、規則の打ち手を2席に置いて96半荘打たせ、着順を出します。
- 結果は最後のログの行と、`eval`フォルダーに書かれます。
- 初回はlibtorch 2.11.0（約239 MB、展開後 約1.5 GB）を自動で取得します。
- 実行したフォルダーに`config`と`logs`ができます。
- GPUでの使い方や、そのほかの設定は[Epsilon-PrismのREADME](https://github.com/KoutaChan/Epsilon/blob/main/epsilon-prism/README.md)を見てください。

## モデル

| 項目 | 内容 |
| --- | --- |
| パラメーター | 4,885,999（約4.89M） |
| 入力 | 打つ席から見える情報だけ |
| 出力 | 候補の手ごとの価値。最も高い手を選ぶ |
| 報酬 | 天鳳の段位戦を元にした順位点（1〜3位: 1・0・−1） |
| 学習 | 白紙から自己対戦 約5,180万半荘 |

学習法はPRISMです。自己対戦で選んだ判断について、候補の手を本当の牌山の写しから局の終わりまで打ち分け、局末の順位の見込みの差をラベルにします。ツモ・槓ドラ・裏ドラの運の揺れは、期待値を変えずに補正して減らします。

## 悪用の禁止

次のことに使わないでください。

- 人と打つオンライン対局（天鳳・雀魂など）や大会で、対局中にAIの判断を見ること、AIに打たせること
- 賭博・詐欺など、法令に反すること
- AIの打牌を人の打牌と偽ること

これはお願いで、MIT Licenseの条件を変えるものではありません。このモデルを使って生じた結果について、作者は責任を負いません。

## English

Epsilon-Prism 3P u3-v413 is a 3-player Riichi Mahjong AI (Tenhou sanma rules, East-South). This is a pre-release.

- **Training**: The policy was trained from scratch by self-play only (about 51.8 million hanchan).
- **License**: The weights are under the MIT License. The code is under the GNU GPL v3.0.
- **Do not misuse it**: Do not use it for real-time assistance or automated play in online games or tournaments that prohibit AI help. Do not use it for gambling or fraud. This request does not change the MIT License terms.
