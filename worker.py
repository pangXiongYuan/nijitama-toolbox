# -*- coding: utf-8 -*-
"""
worker.py —— 后台刷本线程

两种模式：
  oneclick 一条龙：自己启动浏览器 -> 进游戏 -> 刷本
  attach   普通：连接用户已经打开的游戏窗口（需要 --remote-debugging-port）

完成后：
  after=close  关掉浏览器
  after=keep   保留窗口（可以直接接着玩）

注意：
  - Playwright sync API 必须在本线程创建/使用
  - UI -> 线程：Queue（stop）；线程 -> UI：Qt Signal
  - keep 模式不调用 pw.stop()，并把对象存进全局，防止被回收导致浏览器退出
"""
import queue
import socket
import threading
import time
import traceback

from PySide6.QtCore import QThread, Signal

import _bootstrap  # noqa: F401
from playwright.sync_api import sync_playwright

import farmcore
from gamebot import PROFILE, Game, attach, spawn_chrome, wait_port

_KEEP = []  # 保活容器


def cdp_alive(port=9222) -> bool:
    s = socket.socket()
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


class ListWorker(QThread):
    """
    临时连接游戏，读取关卡列表
      kind="weekday" -> 曜日任務（每天轮换）
      kind="junreki" -> 净化巡历（永久保存）
    """
    sig_done = Signal(list, str)   # cards, error

    def __init__(self, cfg: dict, kind="weekday", parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.kind = kind
        self._logfile = None

    def _log(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            if self._logfile is None:
                import paths
                paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
                self._logfile = open(paths.DATA_DIR / "list_read.log", "a",
                                     encoding="utf-8")
            self._logfile.write(line + "\n")
            self._logfile.flush()
        except Exception:
            pass

    def run(self):
        port = int(self.cfg.get("cdp_port", 9222))
        pw = None
        is_wd = (self.kind == "weekday")
        try:
            self._log("=== 开始读取%s ===" % ("曜日任務" if is_wd else "净化巡历"))
            if not cdp_alive(port):
                self.sig_done.emit([], "没有可连接的游戏窗口。\n"
                                       "请先在【启动游戏】点「启动」并等游戏画面出来。")
                return

            pw = sync_playwright().start()
            browser, ctx, page = attach(pw, port)
            page.set_default_timeout(20000)
            self._log(f"已连接，当前页面: {page.url}")

            g = Game(page, log=self._log)
            ok = g.boot(reuse=True)
            self._log(f"boot={ok} 当前界面={g.screens()}")
            if not ok:
                self.sig_done.emit([], "游戏未就绪（引擎没加载出来）")
                return

            # 逐级导航到关卡选择
            if not g.ui_active("StageSelect"):
                if not g.ui_active("Home"):
                    self._log("不在主页，尝试进入主页…")
                    if not g.to_home():
                        self._log(f"进主页失败，界面={g.screens()}")
                        self.sig_done.emit([], f"停在非主界面：{g.screens()}\n"
                                               "请先在游戏里点进主界面（有出陣按钮那页）")
                        return
                self._log("从主页出发进关卡选择…")
                if not g.to_stage_select():
                    self._log(f"进关卡选择失败，界面={g.screens()}")
                    self.sig_done.emit([], f"进不了关卡选择：{g.screens()}")
                    return

            if is_wd:
                self._log("已在关卡选择，进入曜日任務…")
                if not g.open_weekday():
                    self._log(f"进不了曜日任務列表，界面={g.screens()}")
                    self.sig_done.emit([], "没能进入曜日任務列表。\n"
                                           "请确认游戏里那个曜日任務图标是亮的（已解锁）。")
                    return
                # 前置断言：必须真的在「曜日任務列表」上
                kind = g.screen_kind()
                self._log(f"界面判定: {kind}")
                if kind != "weekday_list":
                    self._log(f"没进入曜日任務列表（判定为 {kind}）")
                    self.sig_done.emit([], f"没进入曜日任務列表（当前是 {kind}），请重试。")
                    return

                def pick():
                    return [{"texts": [c["title"], c["sub"]], "xy": None,
                             "idx": c.get("idx")}
                            for c in g.weekday_cards()]
            else:
                self._log("已在关卡选择，进入净化巡历（戦場列表）…")
                if not g.to_battle_list():
                    self._log(f"进不了戦場列表，界面={g.screens()}")
                    self.sig_done.emit([], "没能进入净化巡历的戦場列表。")
                    return
                kind = g.screen_kind()
                self._log(f"界面判定: {kind}")
                if kind != "battle_list":
                    self._log(f"没进入戦場列表（判定为 {kind}）")
                    self.sig_done.emit([], f"没进入戦場列表（当前是 {kind}），请重试。")
                    return

                def pick():
                    return [{"texts": [c["title"], c["sub"]], "xy": None, "idx": i}
                            for i, c in enumerate(g.collect_all_cards())
                            if "戦場" in c.get("sub", "")]

            cards = []
            for i in range(10):
                raw = pick()
                if raw:
                    cards = raw
                    self._log(f"第 {i+1} 次读取到 {len(raw)} 个关卡（含滚动收集）")
                    break
                page.wait_for_timeout(1000)
            if not cards:
                self._log(f"没读到卡片，界面={g.screens()}")
                try:
                    allcards = g.card_list() or []
                    self._log(f"当前列表卡片 {len(allcards)} 个：")
                    for c in allcards[:10]:
                        self._log(f"   {(c.get('texts') or [])[:2]}")
                except Exception as e:
                    self._log(f"   列表诊断失败: {e}")
                self.sig_done.emit([], f"没读到关卡卡片。当前界面：{g.screens()}")
                return

            self._log("读到的前几关：")
            for c in cards[:6]:
                self._log(f"   {c.get('texts')[:2]}")

            out = []
            for c in cards:
                texts = c.get("texts") or []
                if not texts:
                    continue
                out.append({"title": str(texts[0]),
                            "sub": str(texts[1]) if len(texts) > 1 else "",
                            "idx": c.get("idx", len(out))})
            self._log(f"完成，共 {len(out)} 关")
            self.sig_done.emit(out, "")
        except Exception as e:
            self._log(f"异常: {e}")
            self.sig_done.emit([], f"{e}")
        finally:
            try:
                if pw is not None:
                    pw.stop()
            except Exception:
                pass
            try:
                if self._logfile:
                    self._logfile.close()
            except Exception:
                pass


class HomeWorker(QThread):
    """
    把游戏带回主界面。
    切换模式/副本类型后必须做这一步：如果游戏停在编队、报告书、
    章末界面，直接开始刷本会定位失败。
    """
    sig_done = Signal(bool, str)   # ok, message

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)

    def run(self):
        port = int(self.cfg.get("cdp_port", 9222))
        pw = None
        try:
            if not cdp_alive(port):
                self.sig_done.emit(False, "没有连接的游戏窗口")
                return
            pw = sync_playwright().start()
            browser, ctx, page = attach(pw, port)
            page.set_default_timeout(20000)
            g = Game(page, log=lambda m: None)
            if not g.boot(reuse=True):
                self.sig_done.emit(False, "游戏未就绪")
                return
            ok = g.to_home(timeout=120)
            self.sig_done.emit(ok, "已回到主界面" if ok else f"当前：{g.screens()}")
        except Exception as e:
            self.sig_done.emit(False, str(e))
        finally:
            try:
                if pw is not None:
                    pw.stop()
            except Exception:
                pass


class BotWorker(QThread):
    sig_log = Signal(str)
    sig_status = Signal(str)
    sig_done = Signal(str, int)
    sig_progress = Signal(int, int)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self._cmds = queue.Queue()
        self._stop = False
        self._pause = threading.Event()
        self.g = None

    # ---------- 外部接口 ----------
    def request_stop(self):
        self._stop = True
        self._pause.clear()          # 停止优先，顺手把暂停解除
        try:
            self._cmds.put_nowait("stop")
        except Exception:
            pass

    def request_pause(self):
        """打完当前这一场后停在选关界面，不再开下一轮"""
        self._pause.set()

    def request_resume(self):
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def _stopped(self) -> bool:
        return self._stop

    def _wait_if_paused(self):
        """暂停时挂起：不占 CPU，也不碰游戏"""
        if not self._pause.is_set():
            return
        self.sig_status.emit("已暂停（点「继续」接着刷）")
        self.sig_log.emit(">>> 已暂停，脚本停手；点「继续」接着刷")
        while self._pause.is_set() and not self._stop:
            time.sleep(0.2)
        if not self._stop:
            self.sig_status.emit("继续刷本")
            self.sig_log.emit(">>> 已继续")

    def _sleep_between(self, seconds: float):
        """轮间隔；中途点暂停就挂住，点停止立刻退出"""
        end = time.time() + max(seconds, 0.0)
        while not self._stop and time.time() < end:
            if self._pause.is_set():
                self._wait_if_paused()
                return
            time.sleep(0.1)

    # ---------- 线程体 ----------
    def run(self):
        cfg = self.cfg
        log = self.sig_log.emit
        status = self.sig_status.emit

        done = 0
        fails = 0
        target = int(cfg.get("runs", 5))
        interval = float(cfg.get("interval", 2.0))
        stage_title = cfg.get("stage_title", "")
        keywords = cfg.get("stage_keywords", ["江戸", "火事"])
        stage_type = cfg.get("stage_type", "junreki")
        mode = cfg.get("mode", "oneclick")
        after = cfg.get("after", "keep")

        pw = None
        browser = None
        ctx = None
        keep = False

        try:
            pw = sync_playwright().start()
            port = int(cfg.get("cdp_port", 9222))

            if mode == "attach":
                status("连接已打开的游戏窗口…")
                if not cdp_alive(port):
                    self.sig_done.emit(
                        f"连不上游戏窗口（端口 {port}）。请先点【启动游戏】，"
                        f"等画面出来后点【开始刷本】", 0)
                    return
                browser, ctx, page = attach(pw, port)
                log("已连接到现有游戏窗口")
            else:
                # 一条龙：浏览器由本程序「独立启动」，之后用 CDP 接管。
                # 这样即使关掉工具箱，浏览器也不会跟着被关闭。
                if cdp_alive(port):
                    log("检测到已有游戏窗口，直接连接")
                    browser, ctx, page = attach(pw, port)
                else:
                    status("启动浏览器…")
                    headless = bool(cfg.get("headless", False))
                    # 无头模式强制静音
                    mute = headless or not bool(cfg.get("sound", True))
                    spawn_chrome(profile_dir=PROFILE, port=port,
                                 width=int(cfg.get("width", 1024)),
                                 height=int(cfg.get("height", 600)),
                                 maximized=bool(cfg.get("maximized", False)),
                                 headless=headless, mute=mute,
                                 gpu_mode=str(cfg.get("gpu_mode", "auto")))
                    if not wait_port(port, 45):
                        self.sig_done.emit("浏览器启动超时（调试端口未就绪）", 0)
                        return
                    log("浏览器已启动（独立进程）")
                    browser, ctx, page = attach(pw, port)

            page.set_default_timeout(20000)
            g = Game(page, log=log)
            self.g = g

            # 未登录检测：直接给友好提示，不要干等 2 分钟
            if "/login" in (page.url or "").lower():
                self.sig_done.emit(
                    "还没登录：请点【启动游戏】，在弹出的窗口里输入账号密码登录一次。"
                    "（登录状态会保存在程序目录，以后不用再登）", 0)
                return

            if self._stopped():
                self.sig_done.emit("已停止", 0)
                return

            status("加载游戏…")
            if not g.boot(reuse=(mode == "attach")):
                if "/login" in (page.url or "").lower():
                    self.sig_done.emit(
                        "还没登录：请点【启动游戏】登录一次后再试", 0)
                else:
                    self.sig_done.emit("启动失败：引擎未就绪", 0)
                return
            if self._stopped():
                self.sig_done.emit("已停止", 0)
                return

            # 已经在关卡界面就不用再回主页绕一圈
            if not g.ui_active("StageSelect"):
                status("进入主页…")
                if not g.ui_active("Home"):
                    if not g.to_home():
                        self.sig_done.emit(f"未进入主页：{g.screens()}", 0)
                        return
                status("进入关卡列表…")
                if not g.to_stage_select(stop_check=self._stopped):
                    self.sig_done.emit(f"未进入关卡选择：{g.screens()}", 0)
                    return
            else:
                log("已经在关卡选择界面，直接开始")
            if stage_type == "weekday":
                g.open_weekday(stop_check=self._stopped)
            else:
                if not g.to_battle_list(stop_check=self._stopped):
                    self.sig_done.emit(f"未进入戦場列表：{g.screens()}", 0)
                    return

            status("开始刷本")
            while (target == 0 or done < target) and not self._stopped():
                self._wait_if_paused()
                if self._stopped():
                    break
                self.sig_progress.emit(done, target if target else done + 1)

                if not farmcore.ensure_battle_list(g, log, stage_type,
                                                   stop_check=self._stopped):
                    if self._stopped():
                        break
                    status("重新导航…")
                    if not g.to_stage_select(stop_check=self._stopped):
                        self.sig_done.emit("重新导航失败", done)
                        return
                    if stage_type == "weekday":
                        g.open_weekday(stop_check=self._stopped)
                    elif not g.to_battle_list(stop_check=self._stopped):
                        self.sig_done.emit("重新导航失败", done)
                        return

                status(f"第 {done + 1} 轮" + (f"/{target}" if target else ""))
                st = farmcore.run_once(g, done + 1, stage_title, keywords,
                                       log, stop_check=self._stopped,
                                       stage_type=stage_type,
                                       stage_sub=cfg.get("stage_sub", ""),
                                       stage_idx=cfg.get("stage_idx"),
                                       pause_check=self.is_paused)

                if st == "ok":
                    done += 1
                    fails = 0
                    log(f"  [{done}] ✓ 完成，累计 {done} 轮")
                    self.sig_progress.emit(done, target if target else done)
                elif st == "stopped":
                    break
                elif st == "paused":
                    # 已经停手了：这一场交给游戏自己打完，停在结算界面等恢复
                    self._wait_if_paused()
                    if self._stopped():
                        break
                    self.sig_status.emit("恢复中…")
                    if not g.settle_to_list(stage_type=stage_type,
                                            stop_check=self._stopped):
                        self.sig_done.emit("恢复失败，已停止", done)
                        return
                    continue
                elif st == "shortage":
                    self.sig_done.emit("道具/资源不足，已停止", done)
                    return
                elif st == "retry":
                    continue
                else:
                    fails += 1
                    log(f"  ✗ 失败（连续 {fails} 次）")
                    if fails >= 4:
                        self.sig_done.emit("连续失败过多，已停止", done)
                        return
                    if self._stopped():
                        break
                    if not g.settle_to_list(force_refresh=True, stage_type=stage_type,
                                            stop_check=self._stopped):
                        self.sig_done.emit("恢复失败，已停止", done)
                        return

                self._sleep_between(interval)

            # ---------- 收尾 ----------
            if self._stop:
                # 手动停止：游戏里那场战斗会自己打完，不要在这里干等
                log("已停止。游戏内正在进行的战斗会自己打完，脚本不再操作")
                if after == "close":
                    try:
                        if browser is not None:
                            browser.close()
                    except Exception:
                        pass
                else:
                    keep = True
                self.sig_done.emit("已停止", done)
                return

            # 正常结束：不主动回主页（这一步容易卡住，直接去掉）
            log(f"刷本结束，游戏停在：{g.screens()}")

            if after == "close":
                status("关闭游戏窗口…")
                log("按设置关闭游戏窗口")
                try:
                    if browser is not None:
                        browser.close()
                    elif ctx is not None:
                        ctx.close()
                except Exception as e:
                    log(f"关闭浏览器时出错：{e}")
            else:
                keep = True
                status("已保留游戏窗口")
                log("按设置保留游戏窗口，可以直接接着玩")

            self.sig_done.emit("已停止" if self._stop else f"完成 {done} 轮", done)

        except Exception as e:
            log(f"异常：{e}")
            log(traceback.format_exc(limit=3))
            self.sig_done.emit(f"出错：{e}", done)
        finally:
            if keep:
                _KEEP.append((pw, browser, ctx))
            elif pw is not None:
                try:
                    pw.stop()
                except Exception:
                    pass
