# にじたま 工具箱 —— 项目交接文档

> 给「重新开始一个会话的 AI」看。
> 最后更新：2026-11-09，版本 **1.5.0**
> 新会话请先读完这份 + `CHANGELOG.md`，就能直接接手。

---

## 〇、最快接手方式

1. 读本文件 + `CHANGELOG.md`（了解历史）
2. 需要改哪块就看对应文件头部注释（都写了职责）
3. 改完必做三件事：**升版本号** → **写 CHANGELOG** → **同步 docs/ 文档**
4. 不要没被要求就打包、就跑游戏测试

---

## 一、这是什么

自动刷 `https://nijitama.app/`（にじたま / 魂これ）副本的工具。
Python + PySide6 做界面，Playwright 通过 CDP 驱动真实 Chrome 操作游戏。

**核心原则**：战斗全程不干预，只在「任務報告書」出现后点一次「承認する」。

**两个运行模式**：
- `attach`（默认）：用户自己开游戏，工具箱连上去
- `oneclick`：工具箱自己启动浏览器

---

## 二、文件结构

```
nijitama-farm/
├── app.py           界面主程序（约 1700 行，PySide6）
├── gamebot.py       游戏驱动（约 2000 行，Playwright + Cocos JS）
├── worker.py        后台线程：BotWorker / ListWorker / HomeWorker
├── farmcore.py      刷本核心流程（与界面解耦）
├── config.py        配置读写（data/config.json）
├── paths.py         路径定位（区分源码/打包）
├── version.py       版本号唯一来源
├── docwatch.py      说明文档自动留档
├── make_icon.py     从 keyvisual.jpg 生成 app.ico
├── farm.py          CLI 版本（旧，保留但基本不用）
├── _bootstrap.py    让 Python 找到 playwright（Store 版必须，有副作用）
├── CHANGELOG.md     版本历史（每次必更新）
├── PROGRESS.md      本文件
├── README.md        GitHub 首页说明
├── LICENSE          MIT
├── 功能说明.md       功能清单（给用户看，同步到 docs/）
├── assets/          app.ico / app.png / banner.png / keyvisual.jpg / icons/
├── docs/            使用说明.txt（用户自己维护！）/ 功能说明.md
├── data/            config.json、日志、doc_history/、error.log
├── profile/         浏览器登录态（约 200MB，不要删）
└── steps/           出错截图输出目录
```

**打包**：PyInstaller onedir，产物 `dist/nijitama-toolbox/`。
更新时只需替换 exe（约 3.6MB），运行库 `_internal/` 一般不变。

---

## 三、当前功能（v1.5.0）

| 模块 | 说明 |
|---|---|
| 启动游戏 | CDP 9222 驱动系统 Chrome/Edge，窗口小/全屏，声音开关 |
| 刷本 | 净化巡历（内置 7 关）/ 曜日任務（读取当天列表），次数/间隔 |
| 曜日提醒 | **每天弹窗一次**问是否刷新（不再自动静默读取）|
| 汉化适配 | 中日文双语的卡片匹配 + 序号兜底 |
| 设置 | 窗口大小、声音、无头、GPU、清理浏览器缓存 |
| 日志 | 实时日志 + 「错误日志」按钮打开 data/error.log |
| 异常捕获 | 全局 excepthook + threading.excepthook，写 error.log 并弹窗 |
| 帮助 | 内置帮助面板（首次启动弹出，可勾不再提示）|
| 文档留档 | docwatch 每 3 分钟检查内容哈希，变化就存档 |

---

## 四、核心机制（改代码前必读）

### 1. 坐标换算
```
页面坐标 = 画布矩形 + 画布内坐标 × (rect.width / canvas.width)
```
用 `cc.view.getViewportRect()` 得到游戏可视区，**不要用 ScrollView 节点包围盒**。

### 2. 关卡列表是 InfiniteScroller
卡片只有滚到附近才创建。所以：
- 读列表必须 `collect_all_cards()`（边滚边收集）
- 找卡片必须 `click_card_smart()`（打分匹配 + 序号兜底）
- 不许只读容器里现成节点

### 3. 界面判定的坑
- `hasCardSub()` 只认 `activeInHierarchy` 的节点——退回菜单后旧卡片还挂着但都是 inactive
- 顶部菜单那一行是**一个节点带多个 Label**，里面的「曜日任務」会误命中正则
- 所以正则写成 `[月火水木金土日]曜(?!日任務)`

### 4. 滑动必须等惯性停
`swipe_list()` 结束后调 `wait_scroll_idle()`（连续两次偏移不变才算停），
否则算出的坐标是旧的，会点偏（曾经点到「四方山絵巻」横幅）。

### 5. 结算判定
- `Result` 节点在战斗中就有标签，**不能只看有没有标签**
- 正确信号：`Result/FinalResult` 激活 = 報告書出现
- 承認用 `ResultGamen.Approval()`（组件方法，与语言无关）
- 章末：`chapterEnd` 激活 + 点 `chapterEnd/dicision/stage`

### 6. 曜日任務入口
出陣菜单上**没有「曜日任務」按钮文字**，入口是 `topBtns/weekdayBtn`
（显示为「期間限定 金曜密着取材」卡片）。
优先用 `press()` 调 `StageWeekdayBtn@Buttons`，**不要靠坐标点击**。

### 7. 汉化适配
装了汉化脚本后关卡标题/副标题变中文：
- 打分：标题一致 +100，包含 +60；副标题一致 +50；数字一致 +25；类型一致 +20
- ≥120 才点，避免点到同名的素材关
- 不够分 → 按序号定位（序号语言无关）

---

## 五、踩过的坑（别再踩）

| # | 坑 | 修法 |
|---|---|---|
| 1 | 战斗刚开始就点承認 → 卡死 | 看 `FinalResult` 是否激活 |
| 2 | 曜日任務只读到 2 关 | 正则要求「任務」太窄，改成「X曜」 |
| 3 | 剧情关卡被当战斗关 | 副标题 `クリア条件` 或无副标题 → 跳过 |
| 4 | 刷新时在菜单乱点 | 判定里滚动收集会拖屏，被当成点击；改轻量判定 |
| 5 | 点卡片点到横幅 | 等惯性停 + 二次确认坐标 |
| 6 | pythonw 异常静默 | 全局 excepthook + error.log + 弹窗 |
| 7 | 加序号时漏改返回值 | `_current_stage` 要返回 5 元组（含 cidx）|
| 8 | 界面卡顿 | 连接检测放后台线程，只在状态变化时更新样式 |
| 9 | 快捷方式图标空白 | Shell 读不到工作区目录，图标文件放 `%LOCALAPPDATA%` |
| 10 | 任务栏是 Python 图标 | pythonw 进程改不了，只有打包 exe 才行 |
| 11 | Chrome 吃 4GB 磁盘 | 启动参数禁 `OptimizationGuideModelDownloading` |

---

## 六、用户偏好（很重要）

1. **不要没让跑就跑游戏**——测试必须先问
2. **少截图**——一张图 1000-2000 token；能用文字/断言就别看图
3. **改完一次性打包**，不要反复构建
4. 文档由 AI 维护，但他会亲自改措辞去掉「AI 味」——**改之前先存档，尽量只增不删**；
   写文档别用模板腔（"首先/其次/总之"、排比句、过度总结），像人写的
5. 界面深色卡片风（参考 BetterGI）
6. 版本号：修 bug 升第三位、新功能升第二位、大改升第一位
7. 一次会话做很多事后**建议他开新会话**（每轮都要重发历史，越用越贵）；
   轮次 ≥100 时主动提醒（计数见工作区 `AGENTS.md`）
8. **PROGRESS.md / CHANGELOG.md / 功能说明.md 由 AI 维护**，用户不再手改；
   需求由用户提出，改完由 AI 一次性同步三份文档

---

## 七、当前配置（data/config.json）

```json
{
  "stage_type": "weekday",          // junreki / weekday
  "stage_title": "...", "stage_sub": "...",
  "stage_idx": 0,                   // 关卡在列表中的序号（汉化兜底）
  "lang_mode": "auto",              // auto / ja / zh（目前 auto 即可）
  "runs": 5, "interval": 2.0,
  "mode": "attach", "after": "keep",
  "weekday_stages": [...],          // 当天读到的关卡
  "weekday_day": "2026-11-08",      // 缓存属于哪个游戏日
  "weekday_remind_day": "2026-11-09" // 哪天弹过提醒
}
```

游戏日 = `(now + 1h).strftime("%Y-%m-%d")`（23:00 重置）

---

## 八、常用命令

```powershell
cd D:\Documents\deepseek-harness\default-workspace\nijitama-farm

# 语法检查python -m py_compile app.py worker.py farmcore.py gamebot.py config.py paths.py version.py docwatch.py

# 源码运行
python app.py

# 重新打包
python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --name nijitama-toolbox --icon "assets\app.ico" `
  --collect-all playwright --add-data "assets;assets" --add-data "docs;docs" `
  --hidden-import worker --hidden-import farmcore --hidden-import gamebot `
  --hidden-import config --hidden-import paths --hidden-import version `
  --hidden-import docwatch --hidden-import PySide6.QtSvg app.py

# 清掉测试残留的 Chrome
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*nijitama-farm*profile*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

**PowerShell 坑**：命令行里传含日文/引号的 Python 代码很容易被转义搞坏。
要跑多行 Python，**写成临时 .py 文件再执行**，别用 `python -c "..."`。

---

## 九、已知限制

| 限制 | 说明 |
|---|---|
| 战斗中无法中断 | 游戏内战斗只能等打完，脚本只能停止等待 |
| 同账号不能双开 | bot 和手动浏览器共用 profile |
| 打包版不自动更新 | 改代码要重新打包，源码版才实时 |
| 界面滑动观感一般 | 为了定位准确故意放慢，不要轻易改 |

---

## 十、待办（用户还没要，别自作主张做）

- [ ] 战斗失败/撤退检测
- [ ] 多套关卡配置
- [ ] 掉落物品名映射

---

## 十一、GitHub

仓库：https://github.com/pangXiongYuan/nijitama-toolbox （MIT）

**发版流程**：

1. 改 `version.py` → 写 CHANGELOG → 同步 `功能说明.md`
   （根目录和 `docs/` 是两份副本，**都要改**）
2. `git add -A` → `git commit -m "..."` → `git tag -f vX.Y.Z`
3. `git push origin main` → `git push -f origin vX.Y.Z`
4. 建 Release，内容抄 CHANGELOG 对应版本

`profile/`、`data/`、`steps/` 已在 `.gitignore` 里，别解开。
