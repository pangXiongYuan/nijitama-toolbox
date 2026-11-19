# にじたま 工具箱（nijitama-toolbox）

自动刷《にじたま》（魂これ / tamacolle / 地魂男儿）副本的 Windows 桌面工具。
Python + PySide6 做界面，Playwright 通过 CDP 驱动真实 Chrome 操作游戏。

**核心原则：战斗全程不干预。** 脚本只在「任務報告書」出现后点一次「承認する」，
然后选「続けて任務へ」回到选关，按设定间隔开下一轮。

## English

A Windows desktop tool that automates stage farming in *Nijitama* (魂これ / Tamacolle / 地魂男儿).

It drives your real Chrome over CDP and reads the game's Cocos node tree instead of doing
image recognition — battles run untouched, and the script only clicks 「承認する」 after the
mission report appears.

- Python + PySide6; the UI is currently Chinese only
- 净化巡历 (built-in stages) and 曜日任務 (stages rotated daily)
- Compatible with community Chinese translation userscripts
- Prebuilt `full` package on [Releases](https://github.com/pangXiongYuan/nijitama-toolbox/releases/latest) — no Python required

## 功能

| 模块 | 说明 |
|---|---|
| 净化巡历 | 分话，话和关卡都从游戏里读，读一次存下来 |
| 四方山绘卷 | 同上；游戏里按钮写「あやかし討伐」，进去标题是「四方山绘卷」 |
| 夏日祭典 | 期間限定1 那个入口，历年活动各占一话 |
| 曜日任務 | 每天读一次当天开放的关卡，跨天自动过期 |
| 刷本计划 | 勾多关后成小方块（两列、可滚）：序号/次数/拖动/✕；跑完这一遍就停 |
| 汉化适配 | 列表读的就是游戏里显示的文字（装汉化就是中文），不用自己对 |
| 运行模式 | `attach`（连你自己开的游戏）/ `oneclick`（工具自己启动浏览器） |
| 界面 | 深色卡片风，实时日志，内置帮助 |
| 异常捕获 | 未捕获异常写 `data/error.log` 并弹窗，不会静默失败 |

## 它怎么工作

不做图像识别。通过 `--remote-debugging-port` 连上系统真实的 Chrome，
直接读 Cocos 的 `cc.Node` 树来判断界面状态、计算画布坐标后点击。
比截图识别稳、快，也不占显卡。

关键判定都写在 [PROGRESS.md](PROGRESS.md) 里（包括踩过的坑），改代码前值得先读。

## 环境要求

- Windows 10 / 11
- 系统里装有 Chrome 或 Edge
- Python 3.10+

## 下载

不想自己装 Python 和依赖，去 [Releases](https://github.com/pangXiongYuan/nijitama-toolbox/releases/latest) 下：

**第一次使用请下载带 `full` 的；更新请下载带 `update` 的。**

| 文件名 | 用途 |
|---|---|
| `nijitama-toolbox-v1.6.4-full.zip` | 第一次用。约 86 MB，含运行环境，解压即用 |
| `nijitama-toolbox-v1.6.4-update.zip` | 已经装过旧版。约 3 MB，只有 exe，覆盖旧的就行 |

- 全量包：解压后双击 `nijitama-toolbox.exe`，不用装 Python 和依赖
- 更新包：解压出 `nijitama-toolbox.exe`，覆盖原来那个即可，
  `_internal/`、`profile/`、`data/` 都不用动

运行生成的 `profile/`、`data/`、`steps/` 都在 exe 旁边。

## 快速开始

```powershell
python -m pip install -r requirements.txt
python app.py
```

首次使用：打开游戏 → 在弹出的浏览器里手动登录 → 手动刷一次本让资源加载完 →
之后就能在【刷本】页选关卡开刷。登录态保存在 `profile/`，下次不用再登。

详细说明见 [docs/使用说明.txt](docs/使用说明.txt) 和 [docs/功能说明.md](docs/功能说明.md)。

## 打包

```powershell
python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --name nijitama-toolbox --icon "assets\app.ico" `
  --collect-all playwright --add-data "assets;assets" --add-data "docs;docs" `
  --hidden-import worker --hidden-import farmcore --hidden-import gamebot `
  --hidden-import config --hidden-import paths --hidden-import version `
  --hidden-import docwatch --hidden-import PySide6.QtSvg app.py
```

产物在 `dist/nijitama-toolbox/`。日常更新只需替换 exe。

## 目录结构

| 路径 | 说明 |
|---|---|
| `app.py` | 界面主程序（PySide6） |
| `gamebot.py` | 游戏驱动：CDP + Cocos 节点操作 |
| `worker.py` | 后台线程 |
| `farmcore.py` | 刷本核心流程（与界面解耦） |
| `config.py` / `paths.py` / `version.py` | 配置、路径、版本号 |
| `docwatch.py` | 说明文档变更留档 |
| `profile/` `data/` `steps/` | 运行时生成，已加入 `.gitignore` |

## 已知限制

- 战斗中无法中断，只能等这一场打完
- 同一账号不能双开（bot 和手动浏览器共用 profile）
- 打包版不会自动更新，改了代码要重新打包

## 免责声明

本项目仅供个人学习与技术交流使用。

- 自动化操作可能违反游戏服务条款，**账号风险由使用者自行承担**
- 本项目不提供代练、代肝等任何商业服务，也请勿用于此用途
- 游戏内素材版权归官方所有，本仓库仅在必要范围内作识别用途；权利人要求即移除

## 更新日志

| 版本 | 日期 | 主要变化 |
|---|---|---|
| 1.8.11 | 2026-11-19 | 曜日任務的关卡列表和勾选跨天自动清空（以前会一直留着旧关卡） |
| 1.8.10 | 2026-11-17 | 修「读取失败：name 'gamebot' is not defined」；右键菜单补深色样式 |
| 1.8.9 | 2026-11-17 | 删掉商店版 Python 的启动兜底 `_bootstrap.py`；开发环境换到 Python 3.13 |

更早的版本见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT](LICENSE)
