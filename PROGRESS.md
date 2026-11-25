# にじたま 工具箱 —— 项目交接文档

> 给「重新开始一个会话的 AI」看。
> 最后更新：2026-11-21，版本 **1.8.14**
> 新会话请先读完这份 + `CHANGELOG.md`，就能直接接手。

---

## 〇、最快接手方式

1. 读本文件 + `CHANGELOG.md`（了解历史）
2. 需要改哪块就看对应文件头部注释（都写了职责）
3. 改完必做四件事：**升版本号** → **写 CHANGELOG** → **同步 `功能说明.md`（根目录 + docs/ 两份）** → **README 更新日志表换一行**
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
├── sessionlog.py    滚动会话日志（写 data/session.log，512KB 裁一次）
├── make_icon.py     从 keyvisual.jpg 生成 app.ico
├── farm.py          CLI 版本（旧，保留但基本不用）
├── CHANGELOG.md     版本历史（每次必更新）
├── PROGRESS.md      本文件
├── README.md        GitHub 首页说明
├── LICENSE          MIT
├── 功能说明.md       功能清单（给用户看，同步到 docs/）
├── assets/          app.ico / app.png / banner.png / keyvisual.jpg / icons/
├── docs/            使用说明.txt + 功能说明.md（打包时带上）
├── data/            config.json、日志、doc_history/、error.log
├── profile/         浏览器登录态（约 3.7 GB，不要删，也不许提交）
└── steps/           出错截图输出目录
```

**打包**：PyInstaller onedir，产物 `dist/nijitama-toolbox/`。
更新时只需替换 exe（约 3.6MB），运行库 `_internal/` 一般不变。

---

## 三、当前功能（v1.8.14）

| 模块 | 说明 |
|---|---|
| 启动游戏 | CDP 9222 驱动系统 Chrome/Edge，窗口小/全屏，声音开关 |
| 刷本 | 四个入口（净化巡历/四方山绘卷/夏日祭典/曜日任務），话和关卡从游戏里读 |
| 刷本计划 | 勾多关后成一行小方块（序号/次数/拖动/✕ 取消）；场次=计划总次数，跑一遍就停 |
| 暂停 | 立刻停手，本场由游戏自己打完停在结算界面；点「继续」先结算再接着刷 |
| 点不动自愈 | 关卡点了进不去 → 重建列表 → 重载自救（每场一次）；窗口冻结/没战场直接提示 |
| 曜日提醒 | **每天弹窗一次**问是否刷新（不再自动静默读取）；**跨天自动清空**旧列表和勾选 |
| 汉化适配 | 中日文双语的卡片匹配 + 序号兜底 |
| 设置 | 窗口大小、声音、无头、GPU、清理浏览器缓存 |
| 日志 | 实时日志 + 「错误日志」/「会话日志」按钮，分别打开 error.log 和 session.log |
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
- **序号必须按「全列表位置」记**：读取时若先过滤了剧情关再编号，点击时又用未过滤的列表，就会错位点到剧情关

### 8. 点击安全区与贴边
`scroll_card_into_view()` 里可用区是 `y1+95 ~ y2-110`（避开顶部横幅和底部工具栏）。
卡片只差几十像素时**不要判失败**——列表滚到底就再也动不了，会空转 8 次。
现在 `|y - 钳位后的y| <= 40` 就把点击点钳进可用区，照样点在卡片上。

### 9. 暂停 / 停止的语义（v1.6.1 起）
- **停止**：`_stop` 置位，所有导航函数、战斗循环都接 `stop_check`，1 秒内退出；游戏里那场照常打完
- **暂停**：`_pause`（`threading.Event`）置位 → `run_battle` 立刻返回 `paused`，**不再点承認**，
  这一场由游戏自己打完停在报告书；worker 挂起等恢复，恢复时先 `settle_to_list()` 把这场收尾
- 停止优先级高于暂停：`request_stop()` 会顺手清掉 `_pause`
- 新加任何长循环（导航、等待）都要带上 `stop_check` / `pause_check`，否则又会出现「按了没反应」

### 10. 窗口被遮挡会冻结游戏
Chrome 在 Windows 上会检测窗口是否被完全遮挡，被挡住就当成 hidden：rAF 停止、定时器降频，
Cocos 的逻辑全挂在 rAF 上，于是一起冻住。
启动参数已加：`--disable-backgrounding-occluded-windows`、`--disable-renderer-backgrounding`、
`--disable-background-timer-throttling`，并在 `--disable-features` 里加了
`CalculateNativeWinOcclusion,IntensiveWakeUpThrottling`。
**最小化仍然会停**，那是真 hidden，参数救不回来。

### 11. 输入卡死：鼠标只按下没松开，之后点什么都没反应Cocos 的点击靠「按下 → 抬起」配对。一次拖拽如果只发出按下、抬起丢失了
（脚本被强杀、Playwright 连接断开、`mouse.down()` 后抛异常都可能），
游戏内部会一直认为有一根手指还按着，之后所有点击都被当成那次拖拽的延续被吞掉。

表现很有欺骗性：画面照常在动（rAF 一秒 160 多帧）、按钮看着正常、
`pointerdown / mousedown / mouseup / click` 事件全都正常到达 canvas，但界面毫无反应。
关掉 `fade`、`mekakushiUD/L/R` 这些遮罩也没用——不是遮罩挡的。
**`press()`（直接调按钮 handler）不受影响**，所以脚本还能导航，
失效的只是所有靠鼠标坐标的点击：卡片、返回、出陣。

唯一可靠的恢复办法是重载页面（`reload_and_home()`），把游戏的输入状态整个重置。
2026-11-16 实测：卡住后无论 `mouse.up()`、关遮罩还是换新连接点，都不恢复；
`page.reload()` 之后点 MENU 立刻正常。

**1.6.5 起的处理**（改代码时别把这几条弄丢）：
- `Game.release_mouse()`：连接游戏后、以及 worker 的 `finally` 里各补一次 `mouse.up()`，
  正常退出路径不会再留下「按下」；被 SIGKILL 强杀时 finally 不执行，这一档挡不住
- 关卡点了进不去（`farmcore.run_once` 返回 `click_dead`）时：
  第 1 次 → `settle_to_list(force_refresh=True)` 重建列表；
  第 2 次 → `reload_and_home()` 重载自救，整场刷本只重载一次（`BotWorker._reloaded`）
- 重载前先用 `Game.frame_alive()` 读 `cc.director.getTotalFrames()` 有没有在涨：
  不涨说明是窗口最小化/被完全遮挡，直接提示停手，不白重载
- 列表 0 张卡（`no_cards`）先重建一次确认，还是空就直接说「这一话没有可打的战场」

### 12. 副本入口 → 话 → 关卡（1.7.0 起的结构）

选关界面是三层，判定只看 `stageState().type`：

| 层 | 判定 | 内容 |
|---|---|---|
| 入口菜单 | `type == 0` 且没卡片 | 顶部一排入口按钮（`topBtns/*`）|
| 章节列表 | `type == 0` 且有卡片 | 每话一张卡（`texts[0]` 话名、`texts[1]` 副标题）|
| 战场列表 | `type == 2` | 每关一张卡（`texts[0]` 关卡名、`texts[1]` 战场名）|

入口表在 `gamebot.ENTRIES`（显示名 / 内部键 / 节点名），加新入口只要加一行：

```python
("净化巡历", "junreki", "junrekiBtn"),       # 浄化巡歴
("四方山绘卷", "ayakashi", "ayakashiBtn"),   # あやかし討伐，进去标题才是「四方山绘卷」
("夏日祭典", "summer", "specialBtn1"),       # 期間限定1
("曜日任務", "weekday", "weekdayBtn"),       # 没有「话」这一层
```

流程：`open_entry()` 退到入口菜单 → 点入口 → 等章节列表 →
`enter_chapter()` 点话卡 → 切戦闘 → 等 `type == 2`。

- `read_chapters()` / `read_stages()` 是读取入口，都走同一套导航 + `collect_all_cards()` 滚动收集
- 卡片文字第 4 个字段（时间/地名/倒计时）是节点复用的残留，**不能当数据**，只认前两个
- 收集结果里会混进「戻る」返回按钮节点，`_clean_cards()` 会剔掉
- `_chapter_list_of` / `_battle_list_of` 记着「现在停在哪」，命中就不重复导航；
  `boot()` 和重载后要清零
- 关卡序号 `idx` 是**当前话战场列表里的位置**，跟读到的列表一起存，不再跨话通用

### 13. 刷本计划（1.8.0 起）

- 界面：lst_stages（CheckList：点整行切勾选，不选中所以不滚动）+ 计划区 PlanChip 两列网格
  （序号 / 关卡名 / 次数 / ✕），**竖向滚动，一屏两行半**（高度 90）
- 拖动时**边缘自动滚**：`_auto_timer`（30 ms）在指针进入视口上下 18 px 时按距离滚 2~14 px，
  滚完重算高亮。只靠 mousemove 事件驱动是不够的——指针停着不动就滚不起来
- 存法：`entries[entry].selected[章节键] = [{title, sub, times}, ...]`，**数组顺序就是刷本顺序**
- 顺序模式：`stage_order` = `picked`（默认，按勾选先后，**拖动**调）/ `list`（按关卡列表顺序，拖动禁用）
- 拖动：`PlanChip` 自己看按下/移动/抬起，松手把全局坐标交给 `_chip_moved` 算落在哪个方块上；
  **两个方块直接对调**（`sel[src], sel[tgt] = sel[tgt], sel[src]`），不是把后面整串挪一格；
  **不要**用 Qt 的拖放框架（InternalMove 会在拖完再删一次源行，第 1.8.2 版就栽在这上面）
- 勾选逻辑：勾上追加到末尾，取消摘掉，已有 `times` 保留
- 摊平在 `worker.py`：`plan = [关卡 × times …]`，然后 `plan[done % len(plan)]`；
  `runs` 由计划自动求和（1.8.1 起没有手填的刷本次数），跑完一遍就停
- `CheckList.mousePressEvent` 故意不调父类，一次解决三件事：不触发「选中」→ 不自动滚动、
  不用瞄准小方框、也不会出现「Qt 勾一次 + 自己勾一次」的二次切换
- 次数框是 `ChipSpinBox`（1.8.8 起）：`focusInEvent` 里 `QTimer.singleShot(0, selectAll)`
  （直接 selectAll 会被随后的光标定位覆盖），`mousePressEvent` 只在点中 lineEdit 区域时全选
  （点上下箭头不该全选）；`Qt.NoContextMenu` 要同时设在 QSpinBox 和它的 `lineEdit()` 上，
  只设外层右键还有菜单

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
| 12 | 序号兜底点到剧情关 | 读取时过滤剧情关再编号、点击时不过滤，整体错一位；改成按全列表位置记 + 剧情关不点 |
| 13 | 最后一关永远点不进去 | 卡片 426 超出可用区上限 425（差 1px），列表到底滑不动；贴边 40px 内钳进可用区 |
| 14 | 按了停止还在导航 | 导航函数不查停止标志，一次 `to_battle_list` 要 75 秒；现在全接 `stop_check` |
| 15 | 窗口被挡住游戏就不动 | Chrome 遮罩检测→判 hidden→rAF 停；启动参数禁 occlusion 与 timer 节流（最小化仍会停） |
| 16 | 游戏画面偶发冻住 | 独显直连 + `--use-angle=d3d11` 下驱动重置（`nvlddmkm` Id 153）；显卡模式改三档，默认 auto 不加 GPU 参数 |
| 17 | 改了参数一边生效一边没有 | 启动参数曾在 `spawn_chrome()` 和【启动游戏】各拼一份，1.6.2 只改了一边。现在统一走 `gamebot.chrome_args()` |
| 18 | 脚本被强杀后游戏点什么都没反应，人手点也没用 | 拖拽只发了按下、抬起丢了，Cocos 一直等那次触摸结束。重载页面才能恢复（见第四节第 11 条） |
| 19 | 退层时按 `chapterBase/firstMenuBtn`，游戏直接回主页 | 那个按钮（`ChapterBackParentBtn`）是「回主菜单」，不是回上一层。只用 `backBtn` 一层层退，且等界面真的变了再按下一层 |
| 20 | 写死的关卡标题装了汉化就对不上 | 原来是日文原文 + 序号兜底在跑。1.7.0 起列表从游戏里读，读到的就是显示文字，语言无关 |
| 21 | 点靠下的关卡，列表自己往上滚 | QListWidget 选中某项时会把它滚到完整可见。自己处理 mousePressEvent、不走选中，顺带做到「点整行就勾」（CheckList）|
| 22 | 一点「读取」就 `name 'gamebot' is not defined` | `worker.py` 只写了 `from gamebot import PROFILE, Game, ...`，却在日志里用 `gamebot.ENTRY_NAME`。1.7.0 加了那两行文案，1.8.10 才补上 `import gamebot`。**改了 import 要顺手搜一遍模块名用法** |
| 23 | 日志框右键菜单是白底 | QMenu 是独立弹窗，样式表里没写规则就是系统默认色；而且它的 parent 可能是空的，只挂窗口样式管不到。要给 `QMenu` 写规则 + `QApplication.setStyleSheet(QSS)` |
| 24 | 曜日任務的列表和勾选跨天不清 | `_maybe_remind_weekday` 只弹窗、从没清过；`weekday.day` 写进去没人比对。曜日按天轮换，旧关卡点不到 → 一直撞「点不动」。跨天时清 `stages`/`selected`、`day` 置空 |
| 25 | 勾第 2 关后计划区只显示左边一半 | `QScrollArea` 不因内部重建重算 `sizeHint`，宽度停在 228；`widgetResizable` 把两块压成 105。`_fill_plan` 里按第一排方块自己算宽度设 `setMinimumWidth`（**不能读 `chip_lay.sizeHint()`，addWidget 后还没重算**） |
| 26 | 角色负伤时反复重载游戏 | 弹窗「出陣の条件が整っていません / 安房(負傷中)」不匹配 `shortage_text()` 的词表（`整っていません` 是「いません」）；`start_battle` 干等 6 次 → 判卡死 → 重载。1.8.13 加 `blocked_text()` 认这句话，返回 `"wounded"` 让上层停手 |

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
9. 装软件默认放 **E 盘**（`E:\Apps\`），别占 C 盘；Squirrel 类安装包不认自定义路径时，
   先装默认位置再用 `mklink /J` 做目录联接

---

## 七、当前配置（data/config.json，config_version = 2）

```json
{
  "config_version": 2,
  "entry": "junreki",               // junreki / ayakashi / summer / weekday
  "entries": {
    "junreki": {
      "chapters": [ {...} ],        // 读到的话，新的在前
      "chapter": {"title": "...", "sub": "第一话"},
      "stage_lists": {"<标题\0副标题>": [ {"title","sub","idx"} ]},
      "selected":    {"<标题\0副标题>": [ {"title","sub"} ]}   // 勾了要刷的，按勾选顺序
    },
    "ayakashi": { ... }, "summer": { ... },
    "weekday": {"stages": [...], "selected": [...], "day": "2026-11-16"}
  },
  "chapter": {"title": "...", "sub": "第一话"},   // 运行中要刷的那一话
  "stages": [ {"title","sub","idx"} ],            // 运行中要轮刷的关卡（按顺序）
  "lang_mode": "auto", "runs": 5, "interval": 2.0,
  "mode": "attach", "after": "keep",
  "weekday_remind_day": "2026-11-09"
}
```

读写的入口：`config.get_entry / entry_stages / entry_selected / set_entry_selected`，
别直接动 `entries` 里的键。

游戏日 = `(now + 1h).strftime("%Y-%m-%d")`（23:00 重置）

---

## 八、常用命令

```powershell
cd D:\Documents\deepseek-harness\default-workspace\nijitama-farm

# 语法检查
python -m py_compile app.py worker.py farmcore.py gamebot.py config.py paths.py version.py docwatch.py

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

# git（本机没装独立 git，用 GitHub Desktop 自带那份）
& "$env:DSH_HOME\git.ps1" status --short
& "$env:DSH_HOME\git.ps1" add -A
& "$env:DSH_HOME\git.ps1" commit -m "fix: ..."
& "$env:DSH_HOME\git.ps1" push origin main
```

**PowerShell 坑**：命令行里传含日文/引号的 Python 代码很容易被转义搞坏。
要跑多行 Python，**写成临时 .py 文件再执行**，别用 `python -c "..."`。

---

## 九、已知限制

| 限制 | 说明 |
|---|---|
| 战斗中无法中断 | 暂停只是脚本停手，游戏里那场要等它打完 |
| 角色负伤不能出阵 | 游戏会弹「出陣の条件が整っていません」；1.8.13 起脚本认这句并停手提示（1.8.14 又加固了一轮），但不会自己去治疗，得手动治 |
| 窗口最小化会停 | 被判成真 hidden，启动参数救不回来；挂着刷时别最小化，露一条边也行 |
| 同账号不能双开 | bot 和手动浏览器共用 profile |
| 打包版不自动更新 | 改代码要重新打包，源码版才实时 |
| 界面滑动观感一般 | 为了定位准确故意放慢，不要轻易改 |
| 脚本被强杀后可能点不动 | 触摸卡在「按下」状态，人手点也没用；重载页面恢复（见第四节第 11 条）|

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
   （根目录和 `docs/` 是两份副本，**都要改**）→ README 的「更新日志」表加一行
   （只留最近三版，最老的一行删掉）
2. `git add -A` → `git commit -m "..."` → `git tag -f vX.Y.Z`
3. `git push origin main` → `git push -f origin vX.Y.Z`
4. 建 Release：**说明里只放下载信息，不要抄更新日志**（用户明确要求），
   更新记录看 README 的「更新日志」表和 CHANGELOG
5. 打包 → 两个 zip 传到 Release，**文件名带版本号**：
   - `nijitama-toolbox-vX.Y.Z-full.zip`：整个 `dist/nijitama-toolbox/`（约 86 MB，含运行环境）
   - `nijitama-toolbox-vX.Y.Z-update.zip`：只放 exe（约 3 MB，覆盖旧 exe 即更新）
   - 下载页提示写「第一次用下带 full 的，更新下带 update 的」，提示本身不带版本号，
     这样每次发版只换文件、不用改文案

`profile/`、`data/`、`steps/` 已在 `.gitignore` 里，别解开。

---

## 十二、交接状态（2026-11-17）

**当前**：版本 **1.8.14**（源码已改，**未打包、未提交**；线上最新 Release 是 v1.8.11）。
`dist/nijitama-toolbox/` 是 1.8.11 在 3.13 下打的包，**没有 1.8.12/1.8.13 的修复**，别拿它试。

**这轮改了什么（1.6.5 → 1.8.14）**

- 1.6.5：输入卡死自救（`release_mouse` / `frame_alive` / 点不动就重载一次）
- 1.7.0：副本改成「入口 → 话 → 关卡」三层，**关卡列表改为从游戏里读**，配置迁到 v2
- 1.7.1~1.7.3：UI 修补（深色列表、字号 +2、勾选框蓝底白勾、列表宽度 420、按钮不截字）
- 1.8.0~1.8.8：刷本计划（每关次数、拖动对调、chip 两列网格、拖动高亮）
- 1.8.9：删掉 `_bootstrap.py`（商店版 Python 的兜底，环境换到 3.13 后已经空跑）
- 1.8.10：`worker.py` 漏了 `import gamebot`，一点「读取」就 `name 'gamebot' is not defined`；
  QMenu 补深色样式并把 QSS 挂到 `QApplication`
- 1.8.11：曜日任務的列表和勾选跨天自动清空（`_maybe_remind_weekday` 里补的，
  放在「是否正在刷本」判断之后，清完照旧弹提醒）
- 1.8.12：计划区宽度跟着方块数长开（`_fill_plan` 里按第一排方块算最小宽度，
  读 `chip_lay.sizeHint()` 会拿到旧值，得自己算）
- 1.8.13：认出「出陣の条件が整っていません / 負傷中」，负伤时停手提示
  （`gamebot.blocked_text()` + 新状态 `"wounded"`，farmcore 透传、worker 停手）
- 1.8.14：1.8.13 真机没生效（三次出阵全空、没有「拦下」日志）→ 点完出阵改成
  每 400ms 查一次连查 3.2 秒（弹窗可能一闪而过）、扫描范围从 `Canvas/UI` 放到整个场景、
  Label + RichText 都读、词表加「受傷/受伤/整いません/出阵条件不足」；
  三次都没开打时额外打印 `visible_texts()`（界面所有文字），方便下次直接对结构
- 顺手修掉的坑：#18 输入卡死、#19 `firstMenuBtn` 是回主菜单、#20 汉化后硬编码标题对不上、
  #21 列表选中会自动滚动、#22 worker 里漏 import、#23 QMenu 白底、#24 曜日跨天不清、
  #25 计划区宽度不跟着长、#26 负伤弹窗被当成卡死；
  `boot(reuse=True)` 不再把商店/澡堂当成「不在游戏里」而重载页面

**怎么快速看效果**：桌面快捷方式「にじたま 工具箱」（`D:\Deskstop\`）跑的是**源码**
（`pythonw app.py`），改完保存、关掉再双击就是新的，标题栏显示版本号。项目根还有个同作用的
`启动源码版（免打包）.lnk`。两个指向的 `pythonw.exe` 在 2026-11-17 换成了
`E:\Apps\Python313\pythonw.exe`（原来指商店版，卸掉后点不开）。**不要**用 `dist/` 里的 exe 试新界面。

**下一轮接着做**：等他拿 1.8.14 再试一次负伤场景。如果日志出现「⚠ 出阵被拦下」就说明对了；
如果还是三次全空，末尾那行 `!! 出阵一直没开打，界面文字：…` 就是弹窗的真实文案与节点名，
照着它改 `blocked_text()` 的词表或解析方式。
1.8.11 那条跨天清空得等真的过了 23:00 才看得到，想现在验就把
`data/config.json` 里 `entries.weekday.day` 改成昨天的日期再重启。

**最近几版做了什么**

| 版本 | 内容 |
|---|---|
| 1.5.1 | 修最后一关卡点不进去（贴边 1px）、修序号错位点到剧情关 |
| 1.5.2 | 停止时立刻中断导航；恢复流程按副本类型分流 |
| 1.6.0 | 新增暂停/继续 |
| 1.6.1 | 暂停改成「立刻停手，本场自己打完」 |
| 1.6.2 | 关掉 Chrome 遮挡检测与定时器节流，窗口被挡住不再冻结 |
| 1.6.3 | 会话日志 `data/session.log`（512KB 自动裁剪）+【日志】页「会话日志」按钮 |
| 1.6.4 | 启动参数统一走 `gamebot.chrome_args()`；显卡渲染改三档（自动/独显/软件）|
| 1.6.5 | 补 `release_mouse()` + 点不动时重载自救；`frame_alive()` 分清冻结与输入卡死 |
| 1.7.0 | 入口/话/关卡三层，列表改为读取，配置 v2，可勾多关轮刷 |
| 1.7.1 | 关卡列表补深色样式（原来白底浅灰字）+ 最小高度 |
| 1.7.2 | 字号整体 +2；任务设置靠左；读取按钮自适应宽度不再截字 |
| 1.7.3 | 勾选框改蓝底白勾；关卡列表宽度 420，右边按钮不动 |
| 1.8.0 | 刷本计划表（每关次数/顺序）；CheckList 点整行勾选、不再自动滚动 |
| 1.8.1 | 次数改成数字框；计划表与列表左对齐、表高按实际行算；删旧刷本次数、间隔挪进运行模式 |
| 1.8.2 | 已选关卡改成拖动排序（PlanTable 自己处理 dropEvent），删掉 ▲▼ 按钮 |
| 1.8.3 | 拖动改用 DragDrop+Copy（不然 Qt 会二次删行）；boot 不再把商店等界面误判成「不在游戏里」而重载 |
| 1.8.4 | 计划区从表格换成 chip（PlanChip，自己处理拖动），省一整张表 |
| 1.8.5 | chip 改两列网格、竖向滚动；横向滚动条关掉（会压字）|
| 1.8.6 | 拖动时高亮目标 chip（ChipDrop 样式）；数字框 46x20、方块高 28 |
| 1.8.7 | 拖动改成两关直接对调（swap），不再是插到别处顺移；拖动只高亮那一个目标 |
| 1.8.8 | 计划区高度 70→90（露半行）；拖到边缘自动滚（QTimer 30ms）；次数框点一下全选、去右键菜单 |
| 1.8.9 | 删掉 `_bootstrap.py`（商店版 Python 的兜底）；开发环境换到 Python 3.13 并重打验证 |
| 1.8.10 | 修 `worker.py` 漏 `import gamebot` 导致「读取话列表」报 NameError；QMenu 补深色样式并挂到 QApplication |
| 1.8.11 | 曜日任務列表和勾选跨天自动清空（`_maybe_remind_weekday` 里补的）|
| 1.8.12 | 计划区宽度跟着方块数长开（勾第 2 关不再被压成半块）|
| 1.8.13 | 认出「出陣の条件が整っていません / 負傷中」→ 停手提示，不再误判卡死重载 |
| 1.8.14 | 负伤提示再修：扫整场景 + Label/RichText + 连查 3.2 秒；出阵失败打印界面文字 |

**环境**：CPython **3.13.17**（`E:\Apps\Python313\python.exe`）、PySide6 6.12.0、
playwright 1.64.1、PyInstaller 6.22.3。原商店版 Python 3.11.9 已于 2026-11-17 卸载，
`py -3.11` 报「No suitable Python runtime found」是正常的；`E:\dafeiyu\uv\` 下那个
3.12.16 是大肥鱼项目的，别动。pip 源是清华镜像，缓存放 `E:\Apps\Python313\pip-cache`。
git 走 `~/.dsh/git.ps1`（GitHub Desktop 自带 2.56）；发布用 `~/.dsh/ghtoken.ps1`
读 Windows 凭据管理器里的 token。

**下次接着做**：等用户提需求。待办列表在第十节，别自作主张开工。
