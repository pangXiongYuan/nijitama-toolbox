# -*- coding: utf-8 -*-
"""
farm.py —— 自动重复刷「武蔵国 江戸 火事」

每轮流程：
    StageSelect(戦場列表) -> 点「武蔵国 江戸 火事」-> Team 编队
    -> 出阵 -> 战斗 -> Result -> Approval -> chapterEnd
    -> 点「留选关」-> 回到 StageSelect -> 下一轮

用法：
    python farm.py                  # 刷 20 轮
    python farm.py --runs 100       # 刷 100 轮
    python farm.py --runs 0         # 无限（Ctrl+C 停）
    python farm.py --interval 3     # 每轮间隔 3 秒

注意：同一账号不能同时登录，运行前请先关掉你自己浏览器里的游戏页面。
"""
import argparse
import sys
import time

import _bootstrap  # noqa: F401

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

from gamebot import Game, launch

STAGE_KEYWORDS = ["江戸", "火事"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_battle_list(g: Game) -> bool:
    """确保处在 StageSelect 的戦場列表上"""
    if g.ui_active("StageSelect"):
        st = g.js("__gt.stageState()") or {}
        cards = g.js("__gt.cards()") or []
        if st.get("type") == 2 and len(cards) > 0:
            return True
        return g.to_battle_list()
    return False


def run_once(g: Game, idx: int) -> str:
    """跑一次副本，返回 ok / failed"""
    ent = g.enter_stage(STAGE_KEYWORDS)
    if ent == "shortage":
        log(f"  [{idx}] ⚠ 道具/资源不足（进关卡阶段）")
        g.shot(f"shortage_enter{idx}")
        return "shortage"
    if not ent:
        log(f"  [{idx}] 进关卡失败 screens={g.screens()}")
        g.shot(f"err{idx}_enter")
        return "failed"
    log(f"  [{idx}] 已进编队")

    sb = g.start_battle()
    if sb == "shortage":
        log(f"  [{idx}] ⚠ 道具/资源不足，无法出阵")
        g.shot(f"shortage{idx}")
        return "shortage"
    if not sb:
        g.shot(f"err{idx}_start")
        return "failed"

    for _ in range(3):
        ok_btn = g.find_by_handler("ConfirmOK")
        if ok_btn:
            log(f"  [{idx}] 确认弹窗 -> OK")
            g.click(ok_btn[0], "ConfirmOK")
            g.page.wait_for_timeout(2000)
        else:
            break

    log(f"  [{idx}] 等待战斗开始（期间不做任何操作）…")
    outcome = g.run_battle(timeout=1200,
                           on_tick=lambda s, b, p: log(f"  [{idx}]   +{s}s 战斗中 {p}"))
    log(f"  [{idx}] 战斗流程结束: {outcome}")

    if outcome == "stage":
        return "ok"
    if outcome == "chapterend":
        if g.choose_stay():
            return "ok"
        log(f"  [{idx}] 留选关失败 screens={g.screens()}")
        g.shot(f"err{idx}_notstage")
        return "failed"
    if outcome == "no_start":
        log(f"  [{idx}] 战斗没能开始 screens={g.screens()}")
        g.shot(f"err{idx}_nostart")
        return "failed"
    if outcome == "hang":
        log(f"  [{idx}] 界面卡死，尝试从主页重新开始")
        if g.restart_from_home():
            log(f"  [{idx}] 已恢复，重新排队")
            return "retry"
        return "failed"

    log(f"  [{idx}] 战斗超时 screens={g.screens()}")
    g.shot(f"err{idx}_battle_timeout")
    return "failed"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20, help="刷多少轮，0=无限")
    ap.add_argument("--interval", type=float, default=3.0, help="轮间隔秒")
    ap.add_argument("--show", action="store_true", help="显示浏览器窗口（可观看）")
    args = ap.parse_args()

    with sync_playwright() as p:
        ctx = launch(p, headless_new=not args.show, gpu=True,
                     width=1024, height=600)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20000)
        g = Game(page, log=log)

        log("启动游戏…")
        if not g.boot():
            log("启动失败")
            ctx.close()
            return
        if not g.to_home():
            log(f"未进入 Home screens={g.screens()}")
            ctx.close()
            return
        log("Home ✓")
        if not g.to_stage_select():
            log(f"未进入 StageSelect screens={g.screens()}")
            ctx.close()
            return
        log("StageSelect ✓")
        if not g.to_battle_list():
            log(f"未进入戦場列表 screens={g.screens()}")
            ctx.close()
            return
        log("戦場列表 ✓ 开始循环")

        done = 0
        fails = 0
        target = args.runs if args.runs > 0 else float("inf")

        try:
            while done < target:
                # 战斗/结算进行中：先把它跑完，绝不重新导航
                bs = g.battle_state() or {}
                if bs.get("Battle") or bs.get("Result") or bs.get("chapterEnd"):
                    log("检测到仍有战斗流程未结束，先处理完")
                    outcome = g.run_battle(
                        timeout=1200,
                        on_tick=lambda s, b, p: log(f"  +{s}s 收尾中 {p}"))
                    if outcome == "chapterend":
                        g.choose_stay()
                    continue

                if not ensure_battle_list(g):
                    log("不在戦場列表，尝试重新导航")
                    if not g.to_stage_select() or not g.to_battle_list():
                        log("重新导航失败，停止")
                        break

                status = run_once(g, done + 1)
                if status == "ok":
                    done += 1
                    fails = 0
                    log(f"  [{done}] ✓ 完成，累计 {done} 轮")
                elif status == "shortage":
                    log("道具/资源不足，停止刷本")
                    break
                elif status == "retry":
                    # 卡死已自动恢复，不计入失败，继续下一轮
                    log("  已恢复，继续")
                    continue
                else:
                    fails += 1
                    log(f"  ✗ 失败（连续 {fails} 次）")
                    if fails >= 4:
                        log("连续失败过多，停止")
                        break
                    if not g.settle_to_list(force_refresh=True):
                        log("恢复失败，停止")
                        break
                    log("已恢复到戦場列表（已强制刷新）")

                time.sleep(args.interval)
        except KeyboardInterrupt:
            log("手动中断")

        log(f"结束：完成 {done} 轮")
        g.shot("zz_farm_end")
        ctx.close()


if __name__ == "__main__":
    main()
