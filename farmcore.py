# -*- coding: utf-8 -*-
"""
farmcore.py —— 与界面无关的刷本流程（供 GUI 和 CLI 共用）

支持两种副本：
  junreki  净化巡历（固定章节 → 战斗 → 战場卡片）
  weekday  曜日任務（每天轮换，关卡列表运行时读取）
"""
import time


def ensure_battle_list(g, log, entry="junreki", chapter=None, stop_check=None) -> bool:
    """确保处在「关卡列表」上（stop_check 为真时直接放弃）"""
    if stop_check is not None and stop_check():
        return False
    if not g.ui_active("StageSelect"):
        return False

    if entry == "weekday":
        if not g.open_weekday(stop_check=stop_check):
            return False
        return len(g.weekday_cards()) > 0

    title = (chapter or {}).get("title", "")
    sub = (chapter or {}).get("sub", "")
    return g.to_battle_list(entry=entry, chapter_title=title, chapter_sub=sub,
                            stop_check=stop_check)


def run_once(g, idx: int, stage, log, stop_check=None, entry="junreki",
             pause_check=None) -> str:
    """
    跑一次副本。stage = {"title": ..., "sub": ..., "idx": ...}
    返回 'ok' / 'failed' / 'shortage' / 'retry' / 'stopped' / 'paused'
         / 'no_cards'（列表里没有可打的关卡）/ 'click_dead'（有卡片但点了进不去）
         / 'wounded'（出阵条件不满足，多半是有角色负伤）
    """
    stage = stage or {}
    stage_title = str(stage.get("title", ""))
    stage_sub = str(stage.get("sub", ""))
    stage_idx = stage.get("idx")

    def stopped():
        return stop_check is not None and stop_check()

    def paused():
        return pause_check is not None and pause_check()

    # 暂停时不开新的一轮，直接交回上层等恢复
    if paused():
        return "paused"

    # 1) 进入关卡（汉化容忍：标题打分 + 序号兜底）
    ent = g.click_card_smart(stage_title, stage_sub, stage_idx)
    if ent == "wounded":
        log(f"  [{idx}] ✗ 出阵条件不满足（队伍里有角色负伤？）")
        g.shot(f"wounded_enter{idx}")
        return "wounded"
    if ent == "shortage":
        log(f"  [{idx}] ⚠ 道具/资源不足（进关卡阶段）")
        g.shot(f"shortage_enter{idx}")
        return "shortage"
    if not ent:
        short = g.shortage_text()
        if short:
            log(f"  [{idx}] ⚠ 提示：{short}")
            okb = g.find_by_handler("ConfirmOK")
            if okb:
                g.click(okb[0], "关闭提示")
                g.page.wait_for_timeout(1500)
            return "shortage"
        n = g.last_card_count()
        if n == 0:
            log(f"  [{idx}] 列表里没有卡片（这一话可能还没有可打的战场）screens={g.screens()}")
            return "no_cards"
        log(f"  [{idx}] 进关卡失败（列表 {n} 张卡，点了没进编队）screens={g.screens()}")
        g.shot(f"err{idx}_enter")
        return "click_dead"

    log(f"  [{idx}] 已进编队")
    if stopped():
        log(f"  [{idx}] 已停止（在编队界面）")
        return "stopped"
    if paused():
        log(f"  [{idx}] 已暂停（在编队界面，不点出阵）")
        return "paused"

    # 2) 出阵
    sb = g.start_battle()
    if sb == "wounded":
        log(f"  [{idx}] ✗ 出阵条件不满足，无法出阵（多半是有角色负伤）")
        g.shot(f"wounded{idx}")
        return "wounded"
    if sb == "shortage":
        log(f"  [{idx}] ⚠ 道具/资源不足，无法出阵")
        g.shot(f"shortage{idx}")
        return "shortage"
    if not sb:
        g.shot(f"err{idx}_start")
        return "failed"

    log(f"  [{idx}] 等待战斗开始（期间不做任何操作）…")
    t_round = time.time()
    outcome = g.run_battle(
        timeout=1200,
        stop_check=stop_check,
        pause_check=pause_check,
        on_tick=lambda s, b, p: log(f"  [{idx}]   +{s}s 战斗中 {p}"))
    dur = time.time() - t_round
    log(f"  [{idx}] 战斗流程结束: {outcome}（{dur:.0f} 秒）")

    if outcome == "stopped":
        return "stopped"
    if outcome == "paused":
        return "paused"
    if outcome == "stage":
        # 正常一场要 3 分钟左右；太短说明误判（比如界面过渡当成结束）
        if dur < 90:
            log(f"  [{idx}] ⚠ 只用了 {dur:.0f} 秒，判定为误判，重试")
            return "retry"
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
            log(f"  [{idx}] 已恢复")
            return "retry"
        return "failed"
    return "failed"
