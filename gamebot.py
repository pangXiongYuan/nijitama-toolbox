# -*- coding: utf-8 -*-
"""
gamebot.py —— にじたま 自动化驱动封装

已验证的流程：
  启动 -> Top -> StartBtn -> (新闻/登录奖励/教程 补齐) -> Home
       -> 出陣 DepartureBtn -> StageSelect
       -> 净化巡历 junrekiBtn
       -> 点章节卡片(はじまりの旅) -> 出现 物語/戦闘
       -> 点戦闘 battleBtn -> 戦場列表
       -> 点目标关卡卡片 -> Team 编队界面
       -> 点 ChapterStartBtn/startBtn 出阵 -> 战斗
"""
import os
import re
import time
from pathlib import Path


import paths

HERE = paths.HERE
PROFILE = paths.PROFILE_DIR
SHOTS = paths.SHOTS_DIR

SWITCH = "https://nijitama.app/switchSession/tamacolle"

# ============ 汉化容忍：关卡卡片匹配 ============
# 装了汉化插件后，关卡标题/副标题会变中文（地魂男児の生活 → 地魂男儿的生活，
# 戦場 其の四 → 战场 其之四）。所以不能直接比字符串，要提取特征再比。
_NUM_MAP = {
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}


def _norm_text(s: str) -> str:
    """去掉空格和虚词，方便中日对照"""
    s = (s or "").replace("\u3000", "").replace(" ", "").replace("　", "")
    for ch in ("の", "之", "・", "－", "-", "the"):
        s = s.replace(ch, "")
    return s.lower()


def _sub_features(sub: str) -> tuple:
    """
    从副标题里抽关键信息：(数字, 类型集合)
    戦場 其の四 → ("4", {"battle"})
    战场 其之四  → ("4", {"battle"})
    高難度戦場 其の一 → ("1", {"battle", "hard"})
    """
    s = _norm_text(sub)
    num = None
    m = re.search(r"([一二三四五六七八九十]|\d+)", s)
    if m:
        num = _NUM_MAP.get(m.group(1), m.group(1))
    kind = set()
    if re.search(r"戦場|战场|戰場", s):
        kind.add("battle")
    if re.search(r"高難度|高难度|高難", s):
        kind.add("hard")
    if re.search(r"素材", s):
        kind.add("material")
    if re.search(r"クリア|通关|通關", s):
        kind.add("story")
    return num, kind


def card_match_score(want_title: str, want_sub: str, texts: list) -> int:
    """
    给「期望的关卡」和「实际卡片文字」打分，越高越像。
    同名关卡（武蔵国 江戸 有素材关和戦場关）靠副标题特征区分。
    """
    title = str(texts[0]) if texts else ""
    sub = str(texts[1]) if len(texts) > 1 else ""
    score = 0

    wt, at = _norm_text(want_title), _norm_text(title)
    if wt and at:
        if wt == at:
            score += 100
        elif wt in at or at in wt:
            score += 60

    if want_sub:
        if sub and _norm_text(sub) == _norm_text(want_sub):
            score += 50
        else:
            n1, k1 = _sub_features(want_sub)
            n2, k2 = _sub_features(sub)
            if n1 and n1 == n2:
                score += 25
            if k1 and k2:
                if k1 == k2:
                    score += 20
                elif k1 & k2:
                    score += 10
    return score


P_START = "scene/Canvas/UI/Top/StartBtn"
P_NEWS = "scene/Canvas/UI/newsParentHome/news/returnBtn"
P_DEPART = "scene/Canvas/UI/Home/DepartureBtn"
P_JUNREKI = "scene/Canvas/UI/StageSelect/topBtns/junrekiBtn"
P_BATTLE_TAB = "scene/Canvas/UI/StageSelect/scrollView/battleBtn"
P_STORY_TAB = "scene/Canvas/UI/StageSelect/scrollView/storyBtn"
P_CONTENT = "scene/Canvas/UI/StageSelect/scrollView/view/content"
P_TEAM_START = "scene/Canvas/UI/Team/ChapterStartBtn/startBtn"

JS_LIB = r"""
window.__gt = {
  root() { return cc.director.getScene(); },
  gm() { return this.root().getChildByName('Managers').getChildByName('GameManager'); },
  bm() { return this.root().getChildByName('Managers').getChildByName('BattleManager'); },
  // 组件可能挂在 GameManager 或 BattleManager 上，两个都找
  comp(n) {
    const g = this.gm();
    if (g) { const c = g.getComponent(n); if (c) return c; }
    const b = this.bm();
    if (b) { const c = b.getComponent(n); if (c) return c; }
    return null;
  },
  byPath(path) {
    const parts = path.split('/').slice(1);
    let n = this.root();
    for (const p of parts) { if (!n) return null; n = n.getChildByName(p); }
    return n;
  },
  pathOf(node) {
    const parts = []; let n = node;
    while (n && n.parent) { parts.unshift(n.name || '?'); n = n.parent; }
    return 'scene/' + parts.join('/');
  },
  screens() {
    const ui = this.root().getChildByName('Canvas').getChildByName('UI');
    const out = [];
    for (const c of ui.children) if (c.activeInHierarchy) out.push(c.name);
    return out;
  },
  uiActive(name) {
    const ui = this.root().getChildByName('Canvas').getChildByName('UI');
    const n = ui.getChildByName(name);
    return !!(n && n.activeInHierarchy);
  },
  isActive(p) { const n = this.byPath(p); return !!(n && n.activeInHierarchy); },
  activeButtons() {
    const out = [];
    const walk = (n) => {
      if (!n) return;
      if (n.getComponent && n.getComponent(cc.Button) && n.activeInHierarchy) out.push(this.pathOf(n));
      if (n.children) for (const c of n.children) walk(c);
    };
    walk(this.root());
    return out;
  },
  xyOfNode(n) {
    // 节点世界坐标 -> 画布像素
    const bb = n.getBoundingBoxToWorld();
    const vs = cc.view.getVisibleSize(), vp = cc.view.getViewportRect();
    const cx = vp.x + (bb.x + bb.width / 2) * cc.view.getScaleX();
    const cy = vp.y + (vs.height - (bb.y + bb.height / 2)) * cc.view.getScaleY();
    // 画布像素 -> 页面坐标（窗口放大/全屏时画布会被 CSS 缩放，必须换算）
    const cv = cc.game && cc.game.canvas;
    if (cv && cv.getBoundingClientRect) {
      const r = cv.getBoundingClientRect();
      const sx = cv.width ? r.width / cv.width : 1;
      const sy = cv.height ? r.height / cv.height : 1;
      return [r.left + cx * sx, r.top + cy * sy];
    }
    return [cx, cy];
  },
  // 页面可视尺寸（用于判断坐标是否在屏幕内）
  pageSize() { return [window.innerWidth, window.innerHeight]; },
  clickXY(path) { const n = this.byPath(path); return n ? this.xyOfNode(n) : null; },
  call(comp, method, args) {
    const c = this.comp(comp);
    if (!c) return { ok: false, why: 'no comp ' + comp };
    if (typeof c[method] !== 'function') return { ok: false, why: 'no method ' + method };
    try { const r = c[method].apply(c, args || []); return { ok: true, ret: (r && typeof r === 'object' ? '<obj>' : String(r)) }; }
    catch (e) { return { ok: false, why: 'throw: ' + e.message }; }
  },
  // 调用按钮的所有 handler（含 emit click）
  press(path) {
    const n = this.byPath(path);
    if (!n) return { ok: false, why: 'no node' };
    const btn = n.getComponent(cc.Button);
    const called = [];
    if (btn) {
      for (const ev of (btn.clickEvents || [])) {
        const tgt = ev.target || n;
        for (const c of (tgt.getComponents ? tgt.getComponents(cc.Component) : [])) {
          if (typeof c[ev.handler] === 'function') {
            let cn = '?'; try { cn = cc.js.getClassName(c); } catch (e) {}
            try { c[ev.handler].call(c, btn, {}); called.push(ev.handler + '@' + cn); }
            catch (e) { called.push('ERR@' + cn); }
          }
        }
      }
    }
    try { n.emit('click', btn); called.push('emit'); } catch (e) {}
    return { ok: true, called };
  },
  cards() {
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return [];
    const out = [];
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const walk = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) walk(x);
      };
      walk(c);
      out.push(texts);
    }
    return out;
  },
  // 按标题精确匹配卡片（忽略空白差异）
  // 按 Label 文字找可点节点（含 Button 或带 Touch handler）
  findByLabel(text) {
    const out = [];
    const walk = (n, d) => {
      if (!n || d > 12) return;
      let lab = '';
      try { const l = n.getComponent(cc.Label); if (l) lab = l.string || ''; } catch (e) {}
      if (lab && lab.indexOf(text) >= 0 && n.activeInHierarchy) {
        let hasBtn = false, handlers = [];
        try {
          const b = n.getComponent(cc.Button);
          if (b) { hasBtn = true; handlers = (b.clickEvents || []).map(e => e.handler); }
        } catch (e) {}
        // 往上找最近的可点祖先
        let target = n;
        let guard = 0;
        while (target && !hasBtn && guard++ < 5) {
          target = target.parent;
          if (target) {
            try {
              const b2 = target.getComponent(cc.Button);
              if (b2) { hasBtn = true; handlers = (b2.clickEvents || []).map(e => e.handler); }
            } catch (e) {}
          }
        }
        if (hasBtn) out.push({ path: this.pathOf(target), label: lab, handlers });
      }
      if (n.children) for (const c of n.children) walk(c, d + 1);
    };
    walk(this.root(), 0);
    return out;
  },
  // 纯文字检测：任意激活 Label 包含该文字即返回 true（不要求按钮）
  hasLabelText(text) {
    let found = false;
    const walk = (n, d) => {
      if (!n || d > 12 || found) return;
      try {
        const l = n.getComponent(cc.Label);
        if (l && l.string && n.activeInHierarchy && l.string.indexOf(text) >= 0) {
          found = true;
          return;
        }
      } catch (e) {}
      if (n.children) for (const c of n.children) walk(c, d + 1);
    };
    walk(this.root(), 0);
    return found;
  },
  // 严格版：祖先按钮必须真的绑定了 clickEvents，避免点到容器上的别的按钮
  findByLabelStrict(text) {
    const out = [];
    const walk = (n, d) => {
      if (!n || d > 12) return;
      let lab = '';
      try { const l = n.getComponent(cc.Label); if (l) lab = l.string || ''; } catch (e) {}
      if (lab && lab.indexOf(text) >= 0 && n.activeInHierarchy) {
        let target = n, guard = 0, handlers = [], ok = false;
        while (target && guard++ < 6) {
          try {
            const b = target.getComponent(cc.Button);
            if (b) {
              handlers = (b.clickEvents || []).map(e => e.handler);
              if (handlers.length > 0) { ok = true; break; }
            }
          } catch (e) {}
          target = target.parent;
        }
        if (ok) out.push({ path: this.pathOf(target), label: lab, handlers });
      }
      if (n.children) for (const c of n.children) walk(c, d + 1);
    };
    walk(this.root(), 0);
    return out;
  },
  // 当前列表里的所有卡片（文字 + 屏幕坐标）
  // 先找标准容器；找不到就扫整个 StageSelect（跳过顶部菜单按钮区）
  cardList() {
    const std = 'scene/Canvas/UI/StageSelect/scrollView/view/content';
    const b = this.byPath(std);
    let cards = this._cardsUnder(b);
    if (cards.length) return cards;
    const ss = this.byPath('scene/Canvas/UI/StageSelect');
    if (!ss) return [];
    let best = [];
    const walk = (n, d, p) => {
      if (!n || d > 7) return;
      const path = p + '/' + (n.name || '?');
      if (path.indexOf('topBtns') >= 0) return;      // 顶部菜单不是关卡
      const cs = this._cardsUnder(n);
      if (cs.length > best.length) best = cs;
      if (n.children) for (const c of n.children) walk(c, d + 1, path);
    };
    walk(ss, 0, 'scene');
    return best;
  },
  // 诊断：列出 StageSelect 里所有“有多个子节点”的容器
  containers() {
    const ss = this.byPath('scene/Canvas/UI/StageSelect');
    if (!ss) return [];
    const out = [];
    const walk = (n, d, p) => {
      if (!n || d > 7) return;
      const path = p + '/' + n.name;
      if (n.children && n.children.length >= 3) {
        let act = 0;
        for (const c of n.children) if (c.activeInHierarchy) act++;
        out.push({ path, total: n.children.length, active: act });
      }
      if (n.children) for (const c of n.children) walk(c, d + 1, path);
    };
    walk(ss, 0, 'scene');
    return out.slice(0, 30);
  },
  _cardsUnder(base) {
    if (!base || !base.children) return [];
    const out = [];
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const walk = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) walk(x);
      };
      walk(c);
      // 关卡卡片至少有两行字（标题 + 条件），单个按钮不算
      if (texts.length >= 2) out.push({ texts, xy: this.xyOfNode(c) });
    }
    return out;
  },
  // 把指定标题的卡片滚到可视区（曜日任務关卡可能超出一屏）
  scrollToCardByTitle(title) {
    const norm = (s) => (s || '').replace(/[\s\u3000]+/g, '');
    const want = norm(title);
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return false;
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const walk = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) walk(x);
      };
      walk(c);
      if (!texts.length || norm(texts[0]) !== want) continue;
      let p = c.parent, sv = null;
      while (p) { try { sv = p.getComponent(cc.ScrollView); } catch (e) {} if (sv) break; p = p.parent; }
      if (sv && sv.scrollToNode) { sv.scrollToNode(c, 0.2); return true; }
      return false;
    }
    return false;
  },
  // 游戏画面在页面里的真实可见矩形（画布，不含黑边）
  viewportRect() {
    const cv = cc.game.canvas, r = cv.getBoundingClientRect();
    const sx = r.width / cv.width, sy = r.height / cv.height;
    const vp = cc.view.getViewportRect();
    return [r.left + vp.x * sx, r.top + vp.y * sy,
            r.left + (vp.x + vp.width) * sx, r.top + (vp.y + vp.height) * sy];
  },
  // 滚动列表所在的可视矩形（页面坐标）
  svRect() {
    return this.viewportRect();
  },
  // 某标题卡片中心的页面坐标（可加副标题进一步区分同名关卡）
  cardXY(title, sub) {
    const norm = (s) => (s || '').replace(/[\s\u3000]+/g, '');
    const want = norm(title);
    const subWant = norm(sub || '');
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return null;
    let fallback = null;
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const w = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) w(x);
      };
      w(c);
      if (!texts.length || norm(texts[0]) !== want) continue;
      const joined = norm(texts.slice(0, 3).join(''));
      if (subWant && joined.indexOf(subWant) >= 0) return this.xyOfNode(c);
      if (!fallback) fallback = this.xyOfNode(c);
    }
    return fallback;
  },
  // 找“关闭类”按钮的坐标（用来关掉挡住界面的弹窗/面板）
  findLabelXY(texts) {
    const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
    const want = Array.isArray(texts) ? texts : [texts];
    let hit = null;
    const walk = (n, d) => {
      if (!n || d > 9 || hit) return;
      if (n.activeInHierarchy) {
        try {
          const l = n.getComponent(cc.Label);
          if (l && l.string && want.indexOf(l.string) >= 0) {
            hit = { text: l.string, xy: this.xyOfNode(n) };
            return;
          }
        } catch (e) {}
      }
      if (n.children) for (const c of n.children) walk(c, d + 1);
    };
    walk(ui, 0);
    return hit;
  },
  // 节点是否激活（按绝对路径）
  pathActive(p) {
    const n = this.byPath(p);
    return n ? !!n.activeInHierarchy : false;
  },
  // 任务报告书是否已经展开（Result/FinalResult 只有报告书出现时才激活）
  reportReady() {
    const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
    const r = ui.getChildByName('Result');
    if (!r || !r.activeInHierarchy) return false;
    const f = r.getChildByName('FinalResult');
    return f ? !!f.activeInHierarchy : false;
  },
  // 章节结束的按钮区（chapterEnd/dicision）
  chapterChoiceReady() {
    return this.pathActive('scene/Canvas/UI/chapterEnd/dicision');
  },
  // 扫描列表里所有「激活」的卡片，看有没有副标题匹配正则（不滚动，便宜）
  hasCardSub(pattern) {
    const re = new RegExp(pattern);
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return false;
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;   // 退回菜单后旧卡片还在，但都是 inactive
      const texts = [];
      const w = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) w(x);
      };
      w(c);
      for (let i = 1; i < Math.min(texts.length, 4); i++) {
        if (re.test(texts[i])) return true;
      }
    }
    return false;
  },
  // 找包含指定文字的标签，返回坐标（用于点菜单里带「曜」的入口卡片）
  findLabelContains(text) {
    const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
    let hit = null;
    const walk = (n, d) => {
      if (!n || d > 10 || hit) return;
      if (n.activeInHierarchy) {
        try {
          const l = n.getComponent(cc.Label);
          if (l && l.string && l.string.indexOf(text) >= 0) {
            hit = { text: l.string, xy: this.xyOfNode(n) };
            return;
          }
        } catch (e) {}
      }
      if (n.children) for (const c of n.children) walk(c, d + 1);
    };
    walk(ui, 0);
    return hit;
  },
  findCardByTitle(title) {
    const norm = (s) => (s || '').replace(/[\s\u3000]+/g, '');
    const want = norm(title);
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return null;
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const walk = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) walk(x);
      };
      walk(c);
      if (texts.length && norm(texts[0]) === want) {
        const btn = (c.children && c.children.length) ? c.children[0] : c;
        return { xy: this.xyOfNode(btn), texts };
      }
    }
    return null;
  },
  findCardXY(keywords) {
    const base = this.byPath('scene/Canvas/UI/StageSelect/scrollView/view/content');
    if (!base) return null;
    for (const c of base.children) {
      if (!c.activeInHierarchy) continue;
      const texts = [];
      const walk = (n) => {
        try { const l = n.getComponent(cc.Label); if (l && l.string) texts.push(l.string); } catch (e) {}
        if (n.children) for (const x of n.children) walk(x);
      };
      walk(c);
      if (keywords.every(k => texts.some(t => t.indexOf(k) >= 0))) {
        const btn = (c.children && c.children.length) ? c.children[0] : c;
        return { xy: this.xyOfNode(btn), texts };
      }
    }
    return null;
  },
  toggles() {
    return {
      story: this.isActive('scene/Canvas/UI/StageSelect/scrollView/storyBtn'),
      battle: this.isActive('scene/Canvas/UI/StageSelect/scrollView/battleBtn'),
    };
  },
  // 加载进度（形如 77.3%）
  progressText() {
    let out = '';
    const ui = this.root().getChildByName('Canvas');
    const walk = (n) => {
      if (!n || out) return;
      try {
        const l = n.getComponent(cc.Label);
        if (l && l.string && n.activeInHierarchy && l.string.indexOf('%') >= 0) out = l.string;
      } catch (e) {}
      if (n.children) for (const c of n.children) walk(c);
    };
    walk(ui);
    return out;
  },
  stageState() {
    const c = this.comp('StageSelectGamen');
    if (!c) return null;
    return { type: c.selectChapterType, battleChapter: c.battleChapter,
             syutsujin: c.syutsujin, isDetail: c.isDetail, group: c.selectedChapterGroupID };
  },
  // 按 handler 名找当前激活的按钮
  findByHandler(handler) {
    const out = [];
    const walk = (n) => {
      if (!n) return;
      const b = n.getComponent ? n.getComponent(cc.Button) : null;
      if (b && n.activeInHierarchy) {
        const hs = (b.clickEvents || []).map(e => e.handler);
        if (hs.indexOf(handler) >= 0) out.push(this.pathOf(n));
      }
      if (n.children) for (const c of n.children) walk(c);
    };
    walk(this.root());
    return out;
  },
  // 列出当前所有激活按钮及其 handler
  buttonHandlers() {
    const out = [];
    const walk = (n) => {
      if (!n) return;
      const b = n.getComponent ? n.getComponent(cc.Button) : null;
      if (b && n.activeInHierarchy) {
        out.push({ path: this.pathOf(n),
                   handlers: (b.clickEvents || []).map(e => e.handler) });
      }
      if (n.children) for (const c of n.children) walk(c);
    };
    walk(this.root());
    return out;
  },
};
"""


class Game:
    def __init__(self, page, log=print):
        self.page = page
        self.log = log

    # ---------- 基础 ----------
    def js(self, expr, arg=None):
        if arg is None:
            return self.page.evaluate(expr)
        return self.page.evaluate(expr, arg)

    def screens(self):
        try:
            return self.js("__gt.screens()")
        except Exception:
            return []

    def ui_active(self, name):
        try:
            return self.js("(n)=>__gt.uiActive(n)", name)
        except Exception:
            return False

    def buttons(self):
        try:
            return self.js("__gt.activeButtons()")
        except Exception:
            return []

    def is_active(self, path):
        try:
            return self.js("(p)=>__gt.isActive(p)", path)
        except Exception:
            return False

    def call(self, comp, method, args=None):
        try:
            return self.js("([c,m,a])=>__gt.call(c,m,a)", [comp, method, args or []])
        except Exception as e:
            return {"ok": False, "why": str(e)}

    def shot(self, tag):
        try:
            SHOTS.mkdir(exist_ok=True)
            self.page.screenshot(path=str(SHOTS / f"{tag}.png"))
        except Exception:
            pass

    def click(self, path, label=""):
        try:
            pos = self.js("(p)=>__gt.clickXY(p)", path)
        except Exception:
            pos = None
        if not pos:
            self.log(f"      !! 无坐标 {path}")
            return False
        self.page.mouse.click(pos[0], pos[1])
        return True

    def press(self, path):
        try:
            return self.js("(p)=>__gt.press(p)", path)
        except Exception as e:
            return {"ok": False, "why": str(e)}



    # ---------- 启动 ----------
    def tap_center(self, bias=0.62):
        """点游戏画面中心偏下的位置（用于穿 TOUCH 启动页）"""
        try:
            r = self.js("()=>__gt.viewportRect()")
            if r:
                x = (r[0] + r[2]) / 2
                y = r[1] + (r[3] - r[1]) * bias
                self.page.mouse.click(x, y)
                return
        except Exception:
            pass
        self.page.mouse.click(505, 560)

    def boot(self, timeout=240, reuse=False):
        """
        等引擎 + 穿门到 Top。
        reuse=True 时，如果当前页面已经在游戏里就不重新导航（普通模式用，
        避免把用户已经打开的页面刷掉）。
        """
        if not (reuse and "tamacolle" in (self.page.url or "")):
            self.page.goto(SWITCH, wait_until="domcontentloaded", timeout=90000)
        for _ in range(120):
            try:
                if self.js("!!(window.cc && cc.director && cc.director.getScene())"):
                    break
            except Exception:
                pass
            self.page.wait_for_timeout(1000)
        self.js(JS_LIB)

        # 普通模式/读取关卡时，可能已经停在主界面或关卡列表，
        # 这时不该再等「标题画面」。
        # 注意：只看“有没有任意 UI 层”是不够的（新闻层常驻），
        # 必须确认真的是游戏里的某个界面；否则重载页面自救。
        if reuse:
            known = ("Top", "Home", "StageSelect", "Team", "Battle",
                     "Result", "ResultGamen", "Garden", "Syouen")
            try:
                sc = self.screens() or []
                if any(k in sc for k in known):
                    self.log(f"    已在游戏内({sc})，跳过标题等待")
                    return True
                self.log(f"    当前没有可用界面{sc}，重新加载游戏")
                self.page.goto(SWITCH, wait_until="domcontentloaded", timeout=90000)
                for _ in range(120):
                    try:
                        if self.js("!!(window.cc && cc.director && cc.director.getScene())"):
                            break
                    except Exception:
                        pass
                    self.page.wait_for_timeout(1000)
                self.js(JS_LIB)
            except Exception as e:
                self.log(f"    复用检查失败: {e}")

        # 周期性点击穿门，直到 Top 激活
        t0 = time.time()
        last = 0
        while time.time() - t0 < timeout:
            if self.ui_active("Top"):
                self.log(f"    Top 就绪 ({time.time()-t0:.0f}s)")
                return True
            if time.time() - last > 6:
                # 先试着关掉挡路的面板（编成/通知/确认框）
                closed = False
                try:
                    hit = self.js("(t)=>__gt.findLabelXY(t)",
                                  ["閉じる", "とじる", "OK", "確認", "キャンセル", "×"])
                    if hit and hit.get("xy"):
                        self.log(f"    关闭遮挡面板「{hit.get('text')}」")
                        self.page.mouse.click(hit["xy"][0], hit["xy"][1])
                        self.page.wait_for_timeout(1500)
                        closed = True
                except Exception:
                    pass
                if not closed:
                    self.tap_center()
                last = time.time()
            self.page.wait_for_timeout(1000)
        self.log(f"    boot 超时，当前界面={self.screens()}")
        return False

    def to_home(self, timeout=90):
        """
        Top -> Home。
        开场链（新闻/登录奖励/教程）用「边催边查」的方式推进，
        不做固定长睡眠，比原来的固定 20 秒等待快很多。
        """
        if self.ui_active("Home"):
            return True

        # 停在任务报告书 / 章末界面时，先处理掉再回主页
        try:
            # 如果战斗还在进行，只能等它打完（脚本无法中断游戏内战斗）
            if self.ui_active("Battle") and not self.js("()=>__gt.reportReady()"):
                self.log("    战斗进行中，等它结束…")
                t0w = time.time()
                while time.time() - t0w < 300:
                    if self.js("()=>__gt.reportReady()") or self.ui_active("chapterEnd"):
                        break
                    self.page.wait_for_timeout(5000)

            if self.js("()=>__gt.reportReady()"):
                self.log("    停在任务报告书，先点承認")
                self.press_approval()
                self.page.wait_for_timeout(3000)
            if self.ui_active("chapterEnd"):
                self.log("    停在章末界面，选择继续")
                self.choose_stay()
                self.page.wait_for_timeout(2000)
        except Exception:
            pass
        if self.ui_active("Home"):
            return True
        if self.ui_active("StageSelect"):
            self.log("    当前在关卡界面，先返回主页面")
            # 从「戦場列表」回主页要连按多次（列表→章节→选关→主页）
            for attempt in range(1, 4):
                if self.ui_active("Home"):
                    return True
                if not self.ui_active("StageSelect"):
                    break
                r = self.press("scene/Canvas/UI/StageSelect/backBtn")
                self.log(f"    返回键#{attempt} -> {r}")
                for _ in range(8):
                    self.page.wait_for_timeout(1000)
                    if self.ui_active("Home"):
                        return True
            if self.ui_active("Home"):
                return True

        CHAIN = ("NewsEnd", "LoginBonusEnd", "TutorialEnd",
                 "GameStartHomeAfter", "GameStartHomeEnd")

        for round_no in range(1, 5):
            if self.ui_active("Home"):
                return True

            # 关键：等「開始」按钮真的可点再点，否则第一次点击完全无效（会白等 30 秒）
            ready = False
            for _ in range(40):
                if self.ui_active("Home"):
                    return True
                if self.is_active(P_START):
                    ready = True
                    break
                self.page.wait_for_timeout(500)
            if not ready:
                self.log(f"    開始按钮一直不可点，screens={self.screens()}")
                continue

            self.click(P_START, f"StartBtn#{round_no}")
            self.page.wait_for_timeout(600)

            deadline = time.time() + 6
            i = 0
            while time.time() < deadline:
                if self.ui_active("Home"):
                    self.log(f"    Home ✓（第 {round_no} 轮，{i * 0.6:.0f}s）")
                    return True
                # 有公告先关
                if self.is_active(P_NEWS):
                    self.click(P_NEWS, "关公告")
                    self.page.wait_for_timeout(600)
                    continue
                # 轮流催开场链
                meth = CHAIN[i % len(CHAIN)]
                self.call("HomeGamen", meth)
                i += 1
                self.page.wait_for_timeout(600)

            self.log(f"    第 {round_no} 轮未进 Home，screens={self.screens()}")

        return self.ui_active("Home")

    def reload_and_home(self):
        """页面卡死时：重载 -> 等引擎 -> 回主页"""
        self.log("      重载页面…")
        try:
            self.page.goto(SWITCH, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            self.log(f"      重载失败: {e}")
            return False
        if not self.boot():
            self.log("      重载后引擎未就绪")
            return False
        return self.to_home()

    def to_stage_select(self, tries=4, allow_reload=True):
        """
        Home -> StageSelect。
        注意：只触发一次，然后耐心等 10 秒。
        以前一次迭代里 click+press 点两下，第一次已经进去了、第二下又退出来，
        会来回震荡导致一直进不去。
        全部失败时怀疑页面卡死，自动重载一次再试。
        """
        for i in range(1, tries + 1):
            if self.ui_active("StageSelect"):
                return True
            if not self.is_active(P_DEPART):
                self.page.wait_for_timeout(1000)
                continue
            r = self.press(P_DEPART)
            self.log(f"      出陣#{i} press={r.get('called')}")
            for _ in range(10):
                self.page.wait_for_timeout(1000)
                if self.ui_active("StageSelect"):
                    return True
        if self.ui_active("StageSelect"):
            return True
        if allow_reload:
            self.log("      出陣一直无响应（疑似游戏卡死），自动重载恢复")
            if self.reload_and_home():
                return self.to_stage_select(tries=2, allow_reload=False)
        return False

    # ---------- 副本列表 ----------
    def _wait_card(self, keywords, timeout=25):
        """等某张卡片出现"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            card = self.js("(k)=>__gt.findCardXY(k)", list(keywords))
            if card:
                return card
            self.page.wait_for_timeout(1000)
        return None

    def to_battle_list(self, chapter_keyword="はじまりの旅"):
        """StageSelect -> 净化巡历 -> 章节 -> 戦闘 -> 戦場列表（带轮询与重试）"""
        # 已经在戦場列表就直接用，不要重新导航一遍
        try:
            st = self.js("__gt.stageState()") or {}
            if st.get("type") == 2 and (self.js("__gt.cards()") or []):
                return True
        except Exception:
            pass

        for attempt in range(1, 4):
            if self.ui_active("StageSelect"):
                self.press(P_JUNREKI)
                self.page.wait_for_timeout(2000)

            card = self._wait_card([chapter_keyword], 25)
            if not card:
                self.log(f"      第{attempt}次：未找到章节卡片，screens={self.screens()}")
                continue

            # 章节卡片也可能在列表下方，先滚进来再点
            try:
                xy = self.scroll_card_into_view(chapter_keyword)
            except Exception:
                xy = None
            if xy:
                card = {"xy": xy}
            self.page.mouse.click(card["xy"][0], card["xy"][1])
            self.page.wait_for_timeout(2500)

            tg = self.js("__gt.toggles()") or {}
            if tg.get("battle"):
                self.click(P_BATTLE_TAB, "戦闘")
                self.page.wait_for_timeout(2500)
            else:
                r = self.call("Buttons", "ChapterBattleBtn")
                self.log(f"      戦闘切换未出现，调用 ChapterBattleBtn {r}")
                self.page.wait_for_timeout(2000)

            # 等戦場列表出现
            t0 = time.time()
            while time.time() - t0 < 25:
                st = self.js("__gt.stageState()") or {}
                cards = self.js("__gt.cards()") or []
                if st.get("type") == 2 and len(cards) > 0:
                    self.log(f"      stageState={st} 卡片={len(cards)}")
                    return True
                self.page.wait_for_timeout(1000)

            self.log(f"      第{attempt}次：未进入戦場列表，screens={self.screens()}")

        return False

    # ---------- 曜日任務 ----------
    # 曜日任務关卡的副标题固定是「木曜任務　初級」「木曜出張任務　初級」这种
    # 曜日任務的副标题每天不一样：木曜任務 / 金曜出張任務 / 金曜密着取材 …
    # 只要求「星期+曜」，但必须排除顶部菜单按钮「曜日任務」本身
    WEEKDAY_RE = re.compile(r"[月火水木金土日]曜(?!日任務)")

    def sv_rect(self):
        """关卡列表的可视矩形（页面坐标）[x1, y1, x2, y2]"""
        try:
            return self.js("()=>__gt.svRect()")
        except Exception:
            return None

    def list_offset(self):
        """当前列表的滚动位置（内容 y 坐标）"""
        try:
            return self.js("""() => {
              const n = __gt.byPath('scene/Canvas/UI/StageSelect/scrollView');
              if (!n) return null;
              const sv = n.getComponent(cc.ScrollView);
              return (sv && sv.content) ? sv.content.y : null;
            }""")
        except Exception:
            return None

    def wait_scroll_idle(self, timeout=2.5):
        """
        等列表停止滚动。
        滑动有惯性，原地不动才算停；否则点的坐标是旧的，会点偏。
        """
        t0 = time.time()
        last = self.list_offset()
        self.page.wait_for_timeout(120)
        while time.time() - t0 < timeout:
            cur = self.list_offset()
            if cur is None:
                return
            if last is not None and abs(cur - last) < 0.5:
                return
            last = cur
            self.page.wait_for_timeout(120)

    def swipe_list(self, dy: int, rect=None):
        """
        在关卡列表里滑动（dy<0 向上滑看下面的内容，dy>0 向下滑）。
        用真实鼠标拖拽模拟，和用户手指滑动效果一致。
        滑完必须等惯性停下，否则后续点击会点偏（曾点到上方的宣传横幅）。
        """
        rect = rect or self.sv_rect()
        if not rect:
            return False
        x1, y1, x2, y2 = rect
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        # 起点不要贴边，避免被工具栏/黑边吃掉
        start_y = cy + (60 if dy < 0 else -60)
        steps = 10
        self.page.mouse.move(cx, start_y)
        self.page.wait_for_timeout(60)
        self.page.mouse.down()
        for i in range(1, steps + 1):
            self.page.mouse.move(cx, start_y + dy * i / steps)
            self.page.wait_for_timeout(30)
        self.page.mouse.up()
        self.page.wait_for_timeout(250)
        self.wait_scroll_idle()
        return True

    def card_xy(self, title, sub=""):
        try:
            return self.js("(a)=>__gt.cardXY(a[0], a[1])", [title, sub or ""])
        except Exception:
            return None

    def locate_card_by_scroll(self, title, sub="", max_steps=12):
        """
        在 InfiniteScroller 列表里找卡片：
        当前没实例化就一边滚一边找，滚到底还没找到就回到顶部再往下找。
        """
        xy = self.card_xy(title, sub)
        if xy:
            return xy

        rect = self.sv_rect()
        self.scroll_list_top()
        self.page.wait_for_timeout(600)

        for _ in range(max_steps):
            xy = self.card_xy(title, sub)
            if xy:
                return xy
            if self.is_list_at_bottom():
                break
            self.swipe_list(-220, rect)
            self.page.wait_for_timeout(400)

        # 到底了还没有：说明在更上面，回顶再扫一遍
        self.scroll_list_top()
        self.page.wait_for_timeout(600)
        for _ in range(max_steps):
            xy = self.card_xy(title, sub)
            if xy:
                return xy
            if self.is_list_at_bottom():
                break
            self.swipe_list(-220, rect)
            self.page.wait_for_timeout(400)
        return None

    def scroll_card_into_view(self, title, sub="", top_margin=95, bottom_margin=110):
        """
        把目标卡片滑到游戏画面内（避开顶部横幅和底部工具栏），返回可点坐标。
        判断依据是游戏视口矩形，不是 ScrollView 的包围盒。
        """
        # 卡片可能还没被实例化（无限滚动列表），先滚动找一遍
        if self.card_xy(title, sub) is None:
            found = self.locate_card_by_scroll(title, sub)
            if not found:
                self.log(f"      滚动全列表也没找到「{title}」")
                return None
            self.page.wait_for_timeout(300)

        for i in range(8):
            self.wait_scroll_idle()          # 惯性没停就别算坐标
            rect = self.sv_rect()
            xy = self.card_xy(title, sub)
            if not rect or not xy:
                self.page.wait_for_timeout(400)
                continue
            x1, y1, x2, y2 = rect
            y_lo, y_hi = y1 + top_margin, y2 - bottom_margin
            x, y = xy
            # 贴边容忍：卡片中心只差几十像素、或列表已经到底滑不动时，
            # 只要卡片还在视口里就把点击点钳进可用区（差 1px 不该算失败）
            click_y = max(y_lo, min(y, y_hi))
            near_edge = abs(y - click_y) <= 40 and y1 + 10 <= y <= y2 - 10
            inside = (x1 + 30 <= x <= x2 - 30 and
                      (y_lo <= y <= y_hi or near_edge))
            if inside:
                # 点之前再确认一次没在滚（双保险）
                self.wait_scroll_idle()
                xy2 = self.card_xy(title, sub)
                if xy2 and abs(xy2[0] - x) < 6 and abs(xy2[1] - y) < 6:
                    if click_y != y:
                        self.log(f"      卡片 y={y:.0f} 贴边，改点 y={click_y:.0f}")
                    return [x, click_y]
                continue
            self.log(f"      卡片 y={y:.0f} 不在可用区({y_lo:.0f}~{y_hi:.0f})，滑动")
            mid = (y_lo + y_hi) / 2
            # 卡片偏下 -> 上滑（负位移）；偏上 -> 下滑
            self.swipe_list(-150 if y > mid else 150, rect)
        return None

    def scroll_list_top(self):
        """把关卡列表滚回顶部"""
        try:
            return bool(self.js("""() => {
              const n = __gt.byPath('scene/Canvas/UI/StageSelect/scrollView');
              if (!n) return false;
              const sv = n.getComponent(cc.ScrollView);
              if (sv && sv.scrollToTop) { sv.scrollToTop(0.05); return true; }
              return false;
            }"""))
        except Exception:
            return False

    def is_list_at_bottom(self):
        """判断列表是否已经滑到底"""
        try:
            return bool(self.js("""() => {
              const n = __gt.byPath('scene/Canvas/UI/StageSelect/scrollView');
              if (!n) return true;
              const sv = n.getComponent(cc.ScrollView);
              if (!sv || !sv.content) return true;
              const max = sv.getMaxScrollOffset ? sv.getMaxScrollOffset() : null;
              if (!max) return true;
              return Math.abs(sv.content.y - max.y) < 4;
            }"""))
        except Exception:
            return True

    def collect_all_cards(self, max_steps=12, require_sub=True):
        """
        边滚边收集列表里的全部卡片。
        场景用的是 InfiniteScroller：只有滚动到哪，卡片才会被创建，
        所以不能只读当前容器里的节点（否则会漏掉没滚动到的关卡）。

        require_sub=True 时跳过「只有一个标题」的卡片
        —— 那是剧情关，没有战斗，不能当关卡刷。
        """
        # 没有任何卡片节点时直接返回：在菜单页拖屏会被游戏当成点击
        if not self.card_list():
            self.log("      当前没有卡片节点，跳过滚动")
            return []

        seen = {}
        skipped = 0
        rect0 = self.sv_rect()

        def harvest():
            nonlocal skipped
            for c in self.card_list():
                texts = [str(t) for t in (c.get("texts") or [])]
                if not texts:
                    continue
                if require_sub and len(texts) < 2:
                    skipped += 1
                    continue
                key = texts[0] + "|" + (texts[1] if len(texts) > 1 else "")
                if key not in seen:
                    seen[key] = {"title": texts[0],
                                 "sub": texts[1] if len(texts) > 1 else ""}

        # 先回到顶部，再一路往下滚
        self.scroll_list_top()
        self.page.wait_for_timeout(600)
        harvest()

        for step in range(max_steps):
            if self.is_list_at_bottom():
                self.log(f"      列表已到底（滚动 {step} 次）")
                break
            before = len(seen)
            self.swipe_list(-220, rect0)
            self.page.wait_for_timeout(500)
            harvest()
            if len(seen) == before and self.is_list_at_bottom():
                break

        self.scroll_list_top()
        self.page.wait_for_timeout(500)
        if skipped:
            self.log(f"      跳过 {skipped} 张剧情卡（没有副标题，无战斗）")
        return list(seen.values())

    def weekday_cards(self):
        """
        只挑出真正的曜日任務关卡（滚动收集全部）。

        命名每天不一样：「木曜任務」「金曜出張任務」「金曜密着取材」都有，
        所以只要求副标题含「X曜」即可；剧情关的副标题是「クリア条件」，排除。
        """
        out = []
        try:
            # 序号按「全列表位置」记，和 click_card_smart 里的 cands 下标同一套，
            # 否则两边一个过滤剧情关、一个不过滤，序号会错位
            for i, c in enumerate(self.collect_all_cards()):
                title = str(c.get("title", ""))
                sub = str(c.get("sub", ""))
                if "クリア条件" in sub:
                    continue
                if self.WEEKDAY_RE.search(sub):
                    out.append({"title": title, "sub": sub,
                                "texts": [title, sub], "xy": None, "idx": i})
        except Exception:
            pass
        return out

    def screen_kind(self):
        """
        判断当前在哪个界面，用于每步前置断言，避免"以为进了"。
        返回 home / chapter_list / weekday_list / battle_list / team / other
        """
        try:
            if self.ui_active("Home"):
                return "home"
            if self.ui_active("Team"):
                return "team"
            sc = self.screens() or []
            if "StageSelect" not in sc:
                return "other"
            st = self.js("__gt.stageState()") or {}
            if st.get("type") == 2:
                return "battle_list"
            # 用全部已实例化卡片判断（不只看可见的几张）
            if self.js("(p)=>__gt.hasCardSub(p)", self.WEEKDAY_RE.pattern):
                return "weekday_list"
            return "chapter_list"
        except Exception:
            return "other"

    def weekday_ready(self):
        """
        是否已经在曜日任務列表。
        注意：这里必须用「不滚动」的轻量判断。
        以前用 weekday_cards()（内部会滚动收集），在菜单页上拖屏会被游戏
        当成点击，点开旁边的「四方山絵巻」，而且白等 20 秒。
        """
        try:
            return bool(self.js("(p)=>__gt.hasCardSub(p)", self.WEEKDAY_RE.pattern))
        except Exception:
            return False

    def open_weekday(self):
        """
        进入曜日任務关卡列表。
        注意：顶部菜单里也有个「曜日任務」按钮，它的文字会误判成关卡，
        所以判定必须用副标题的「X曜任務」格式。
        """
        if not self.ui_active("StageSelect"):
            return False
        self.page.wait_for_timeout(1500)

        if self.weekday_ready():
            return True

        top = "scene/Canvas/UI/StageSelect/topBtns/weekdayBtn"

        # 1) 先直接调按钮处理函数（不依赖坐标，最稳）
        r = self.press(top)
        self.log(f"      点曜日任務（press）: {r}")
        for _ in range(8):
            self.page.wait_for_timeout(1000)
            if self.weekday_ready():
                self.log("      已进入曜日任務列表（press）")
                return True

        # 2) 再试坐标点击
        self.log("      press 无效，改用坐标点击")
        self.click(top, "曜日任務")
        for _ in range(8):
            self.page.wait_for_timeout(1000)
            if self.weekday_ready():
                self.log("      已进入曜日任務列表（点击）")
                return True

        # 3) 找「期間限定 X曜…」这种入口卡片
        #    出陣菜单上的曜日任務不是按钮，而是一张卡片
        #    （例如「期間限定 / 金曜密着取材」），所以要按「X曜」找。
        entry = None
        for c in self.card_list():
            texts = [str(t) for t in (c.get("texts") or [])]
            if any(self.WEEKDAY_RE.search(t) for t in texts):
                entry = c
                break
        if entry is None:
            # 菜单卡片可能在列表里没实例化，扫一遍
            for c in self.collect_all_cards():
                if self.WEEKDAY_RE.search(c.get("sub", "")) or self.WEEKDAY_RE.search(c.get("title", "")):
                    entry = c
                    break

        if entry is not None:
            texts = [str(t) for t in (entry.get("texts") or
                                      [entry.get("title", ""), entry.get("sub", "")])]
            self.log(f"      点曜日任務入口卡片: {texts[:2]}")
            xy = entry.get("xy")
            if not xy and texts:
                xy = self.scroll_card_into_view(texts[0], texts[1] if len(texts) > 1 else "")
            if xy:
                self.page.mouse.click(xy[0], xy[1])
                for _ in range(10):
                    self.page.wait_for_timeout(1000)
                    if self.weekday_ready():
                        self.log("      已进入曜日任務列表（入口卡片）")
                        return True

        # 4) 最后的兜底：直接找界面上带「曜」字的标签点它
        try:
            hit = self.js("(t)=>__gt.findLabelContains(t)", "曜")
            if hit and hit.get("xy"):
                self.log(f"      按文字兜底点击: 「{hit.get('text')}」")
                self.page.mouse.click(hit["xy"][0], hit["xy"][1])
                for _ in range(10):
                    self.page.wait_for_timeout(1000)
                    if self.weekday_ready():
                        self.log("      已进入曜日任務列表（文字兜底）")
                        return True
        except Exception:
            pass

        self.log(f"      !! 进不了曜日任務列表，界面={self.screens()}")
        try:
            self.log("      当前菜单卡片：")
            for c in self.card_list()[:8]:
                self.log(f"        {(c.get('texts') or [])[:3]}")
        except Exception:
            pass
        return False

    def card_list(self):
        """当前列表里的关卡卡片：[{texts, xy}]"""
        try:
            return self.js("__gt.cardList()") or []
        except Exception:
            return []

    def click_card_smart(self, title, sub="", idx=None):
        """
        汉化容忍的关卡点击：
          1) 收集列表全部卡片（含滚动）
          2) 用「标题 + 副标题特征」打分，取最高分（≥120 才认）
          3) 分数不够就用序号兜底（序号与语言无关）
        返回 True 表示已进入编队界面。
        """
        cands = []
        try:
            cands = self.collect_all_cards()
        except Exception as e:
            self.log(f"      收集列表失败: {e}")

        best = None
        best_score = -1
        for c in cands:
            s = card_match_score(title, sub, [c.get("title", ""), c.get("sub", "")])
            if s > best_score:
                best_score, best = s, c

        if best and best_score >= 120:
            self.log(f"      匹配关卡: {best['title']} | {best['sub']}（{best_score} 分）")
            if self.enter_card_by_title(best["title"], best["sub"]):
                return True
            self.log("      按匹配结果点击失败，尝试序号兜底")

        if idx is not None and 0 <= idx < len(cands):
            c = cands[idx]
            if "クリア条件" in (c.get("sub") or ""):
                # 剧情关没有战斗，点进去只会播剧情；宁可失败也不要乱进
                self.log(f"      序号 #{idx} 是剧情关（{c['title']} | {c['sub']}），不点")
            else:
                self.log(f"      按序号 #{idx} 定位: {c['title']} | {c['sub']}")
                if self.enter_card_by_title(c["title"], c["sub"]):
                    return True

        if cands:
            self.log(f"      没匹配上（最高 {best_score} 分），当前列表：")
            for i, c in enumerate(cands[:10]):
                self.log(f"        #{i} {c['title']} | {c['sub']}")
        return False

    def enter_card_by_title(self, title, sub=""):
        """
        点标题匹配的卡片 -> 编队界面。
        先把卡片滚进可视区再点；点歪了（比如点到宣传横幅）会自动退回选关界面。
        """
        want = (title or "").replace("\u3000", "").replace(" ", "")

        for attempt in range(1, 3):
            xy = self.scroll_card_into_view(title, sub)
            if xy:
                self.log(f"      点击目标: {title} @({xy[0]:.0f},{xy[1]:.0f})")
                self.page.mouse.click(xy[0], xy[1])
                self.page.wait_for_timeout(4000)
                if self.ui_active("Team"):
                    return True
                # 没进编队，而且已经离开了选关界面 → 点到别的东西了
                sc = self.screens() or []
                if "StageSelect" not in sc:
                    self.log(f"      点歪了（当前界面 {sc}），退回选关")
                    self.page.mouse.click(
                        (self.sv_rect() or [0, 0, 1024, 600])[0] + 40, 300)
                    self.page.wait_for_timeout(800)
                    r = self.press("scene/Canvas/UI/StageSelect/backBtn")
                    self.page.wait_for_timeout(2000)
                    if "StageSelect" not in (self.screens() or []):
                        if not self.to_stage_select(tries=2):
                            self.log(f"      退回失败，界面 {self.screens()}")
                            return False
                self.log(f"      第 {attempt} 次点击没进编队，重试")
            else:
                cards = self.card_list()
                self.log(f"      滑不到「{title}」，当前 {len(cards)} 张卡片：")
                for c in cards[:10]:
                    t = (c.get("texts") or [""])[0]
                    self.log(f"        「{t}」@({c['xy'][0]:.0f},{c['xy'][1]:.0f})")
                self.page.wait_for_timeout(800)

        self.log(f"      列表里没找到或点不中「{title}」")
        return False

    def enter_stage(self, keywords=("江戸", "火事"), exact_title="武蔵国　江戸　火事",
                    sub=""):
        """
        点目标关卡卡片 -> Team 界面。
        和曜日任務一样：先把卡片滑到可视区再点；同名关卡用副标题区分。
        """
        title = exact_title
        xy = None
        if title:
            xy = self.scroll_card_into_view(title, sub)

        # 精确标题点不到时，按关键词在列表里找
        if not xy and keywords:
            for c in self.card_list():
                texts = [str(t) for t in (c.get("texts") or [])]
                head = texts[:2]
                if any(all(k in t for k in keywords) for t in head):
                    self.log(f"      按关键词命中: {head}")
                    xy = self.scroll_card_into_view(texts[0] if texts else title)
                    if xy:
                        title = texts[0]
                    break

        if not xy:
            self.log(f"      未找到关卡 {exact_title or keywords}")
            cards = self.card_list()
            self.log(f"      当前 {len(cards)} 张卡片：")
            for c in cards[:10]:
                self.log(f"        {(c.get('texts') or [''])[0]}")
            return False

        self.log(f"      选中关卡: {title} @({xy[0]:.0f},{xy[1]:.0f})")
        self.page.mouse.click(xy[0], xy[1])

        for _ in range(10):
            if self.ui_active("Team"):
                return True
            self.page.wait_for_timeout(1000)

        # 没进编队：可能是资源不足弹窗
        short = self.shortage_text()
        if short:
            self.log(f"      ⚠ 进关卡时资源不足: {short}")
            okb = self.find_by_handler("ConfirmOK")
            if okb:
                self.click(okb[0], "关闭提示")
                self.page.wait_for_timeout(1500)
            return "shortage"

        self.log(f"      未进编队，当前按钮: {[b['handlers'] for b in self.button_handlers()][:8]}")
        return False

    def battle_started(self):
        """判断战斗是否真的开始了"""
        bs = self.battle_state() or {}
        if bs.get("Battle") or bs.get("Result") or bs.get("chapterEnd"):
            return True
        if bs.get("Team") is False:
            return True
        if self.progress():
            return True
        return False

    def shortage_text(self):
        """检测是否有「不足」类提示（道具/资源不够导致无法出阵）"""
        try:
            return self.js(r"""() => {
              const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
              const hits = [];
              const walk = (n, d) => {
                if (!n || d > 10) return;
                try {
                  const l = n.getComponent(cc.Label);
                  if (l && l.string && n.activeInHierarchy) {
                    const s = l.string;
                    if (s.indexOf('足り') >= 0 || s.indexOf('不足') >= 0 ||
                        s.indexOf('ありません') >= 0) hits.push(s);
                  }
                } catch (e) {}
                if (n.children) for (const c of n.children) walk(c, d + 1);
              };
              walk(ui, 0);
              return hits.slice(0, 5).join(' / ');
            }""")
        except Exception:
            return ""

    def start_battle(self):
        """Team 界面点出阵（handler+真实点击双保险，并校验是否开打）"""
        # 注意：不做任何「强制跳转」类清理！战斗/结算进行中绝不能干预。
        if not self.ui_active("Team"):
            self.log(f"      当前不在编队界面，screens={self.screens()}")
            return False

        for attempt in range(1, 4):
            if not self.is_active(P_TEAM_START):
                self.log(f"      出阵按钮不可点（attempt {attempt}）")
                self.page.wait_for_timeout(2000)
                continue

            # handler + 真实点击
            self.press(P_TEAM_START)
            self.click(P_TEAM_START, f"出阵#{attempt}")
            self.page.wait_for_timeout(2500)

            if self.ui_active("ConfirmGamen") or self.find_by_handler("ConfirmOK"):
                self.log("      确认弹窗 -> OK")
                self.call("Buttons", "ConfirmOK")
                self.page.wait_for_timeout(2500)

            for _ in range(6):
                if self.battle_started():
                    return True
                self.page.wait_for_timeout(2000)

            # 检查是不是资源不足
            short = self.shortage_text()
            if short:
                self.log(f"      ⚠ 疑似资源不足: {short}")
                # 关掉提示框
                okb = self.find_by_handler("ConfirmOK")
                if okb:
                    self.click(okb[0], "关闭提示")
                    self.page.wait_for_timeout(1500)
                return "shortage"

            self.log(f"      第 {attempt} 次出阵后战斗未开始，screens={self.screens()}")

        return False

    def progress(self):
        try:
            return self.js("__gt.progressText()")
        except Exception:
            return ""

    def battle_state(self):
        try:
            return self.js("""() => {
              const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
              const out = {};
              for (const n of ['Battle','Result','chapterEnd','ConfirmGamen','Team','StageSelect']) {
                const c = ui.getChildByName(n);
                out[n] = c ? !!c.activeInHierarchy : null;
              }
              return out;
            }""")
        except Exception:
            return {}

    def press_approval(self):
        """
        点「任務報告書」的「承認する」。

        优先调用 ResultGamen.Approval()（按钮本身调的函数，最准），
        避免按文字向上找祖先时点到容器上的其它按钮、反而把别的界面调出来。
        按文字找仅作兜底。
        """
        r = self.call("ResultGamen", "Approval")
        if r.get("ok"):
            return True

        # 兜底 1：按坐标点报告纸右下的「承認する」
        try:
            vr = self.js("()=>__gt.viewportRect()")
            if vr:
                self.page.mouse.click(vr[0] + (vr[2] - vr[0]) * 0.86,
                                      vr[1] + (vr[3] - vr[1]) * 0.855)
                return True
        except Exception:
            pass

        # 兜底 2：按文字找，但要求该祖先按钮确实绑定了 clickEvents
        for label in ("承認", "確認"):
            try:
                hits = self.js("(t)=>__gt.findByLabelStrict(t)", label)
            except Exception:
                hits = []
            if hits:
                self.click(hits[0]["path"], f"{label}する")
                return True
        return False

    def wait_battle_start(self, timeout=180, stop_check=None):
        """等战斗真正开始（战斗界面 / 加载进度 / 报告 任一出现）"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if stop_check is not None and stop_check():
                return "stopped"
            bs = self.battle_state() or {}
            if bs.get("Battle") or bs.get("Result") or bs.get("chapterEnd"):
                return True
            if self.progress():
                return True
            self.page.wait_for_timeout(1000)
        return False

    def run_battle(self, timeout=1500, on_tick=None, stop_check=None):
        """
        完整跑一场（可能含多段连续战斗）。

        严格规则：
          - 战斗过程中：不做任何操作（不点屏幕、不点進軍、不跳结算）
          - 只有「任務報告書」渲染完成后，点一次「承認する」
          - 点完不做别的，等界面自己出现「荘園に帰還 / 続けて任務へ」
          - 收到 stop_check 为真时立即中断，返回 'stopped'

        返回 'chapterend' / 'stage' / 'no_start' / 'timeout' / 'hang' / 'stopped'
        """
        # 1) 先确认战斗真的开始了
        started = self.wait_battle_start(180, stop_check=stop_check)
        if started == "stopped":
            return "stopped"
        if not started:
            self.log("      战斗未开始（可能会话/资源问题）")
            return "no_start"

        t0 = time.time()
        last_log = -99
        approvals = 0
        last_click = 0.0
        last_sig = None
        last_change = time.time()
        seen_result_false = False   # 本轮是否见过 Result 消失（用于排除残留）
        last_diag = 0.0             # 诊断日志上次打印时间（绝对时间戳）
        seen_battle = False         # 是否真的看到过战斗进行中
        seen_stage = 0              # 连续看到 StageSelect 的次数

        while time.time() - t0 < timeout:
            # 用户点了「停止」：立刻中断，不再等战斗
            if stop_check is not None and stop_check():
                self.log("      收到停止请求，中断战斗等待")
                return "stopped"

            bs = self.battle_state() or {}
            if bs.get("chapterEnd"):
                # 刚开打就出现 chapterEnd 一定是残留，忽略
                if approvals > 0 or (time.time() - t0) > 30:
                    return "chapterend"

            # 战斗真的在跑（有战斗层或进度）才算“见过战斗”
            if bs.get("Battle") or self.progress():
                seen_battle = True
                seen_stage = 0

            if self.ui_active("StageSelect"):
                # 关键：进战斗的瞬间 StageSelect 层还没销毁，
                # 必须「见过战斗」或已经过了 25 秒，才认定真的回到了选关界面。
                if seen_battle or (time.time() - t0) > 25:
                    seen_stage += 1
                    if seen_stage >= 2:
                        self.log("      已回到选关界面，本轮结束")
                        return "stage"
                else:
                    self.log("      检测到 StageSelect 层（可能还在过渡），继续等待")
                self.page.wait_for_timeout(1500)
                continue

            # 任务结束界面已出现（纯文字判断）-> 绝不再点確認/承認
            try:
                if (approvals > 0 or (time.time() - t0) > 30) and \
                   (self.js("(t)=>__gt.hasLabelText(t)", "任務を終え") or
                        self.js("(t)=>__gt.hasLabelText(t)", "続けて任務")):
                    return "chapterend"
            except Exception:
                pass

            sig = (bs.get("Battle"), bs.get("Result"), self.progress())
            if sig != last_sig:
                last_sig = sig
                last_change = time.time()

            # 关键：必须见过「Result 消失」才认为后面的 Result 是本轮的真实结算，
            # 否则会被上一轮残留的 Result 骗到，在战斗刚开始就点承認。
            if not bs.get("Result"):
                seen_result_false = True

            # 结算是否真的可操作：看 Result/decision 按钮区是否激活。
            # Result 节点在战斗过程中也可能挂着标签（地图进度等），只看标签会误判。
            try:
                report_shown = bool(self.js("()=>__gt.reportReady()"))
            except Exception:
                report_shown = False

            approve_ok = report_shown and (approvals > 0 or (time.time() - t0) > 30)

            if bs.get("Result") and approve_ok and self.result_ready(5):
                now = time.time()
                if now - last_click > 6:
                    if self.press_approval():
                        approvals += 1
                        last_click = now
                        self.log(f"      承認 #{approvals}（战斗第 {int(now - t0)} 秒）")
                        self.page.wait_for_timeout(3000)
                        last_change = time.time()
                        continue

            # 加载/界面长时间毫无变化 -> 判定卡死，交给上层重启
            if time.time() - last_change > 150:
                self.log(f"      界面 {int(time.time()-last_change)}s 无变化，判定卡死")
                self.shot("hang")
                return "hang"

            # 诊断：Result 残留期间定期记录现场（间隔 60 秒，便于事后分析）
            if bs.get("Result") and not approve_ok:
                now_diag = time.time()
                if now_diag - last_diag >= 60:
                    last_diag = now_diag
                    try:
                        ready = self.result_ready(1)
                        self.log(f"      [诊断] Result残留 标签={ready} "
                                 f"Battle={bs.get('Battle')} prog={self.progress()!r} "
                                 f"耗时={int(now_diag - t0)}s")
                        self.shot("diag_result")
                    except Exception:
                        pass

            elapsed = int(time.time() - t0)
            if on_tick and elapsed - last_log >= 25:
                on_tick(elapsed, bs, self.progress())
                last_log = elapsed
            self.page.wait_for_timeout(2000)
        return "timeout"

    def restart_from_home(self):
        """卡死恢复：不关浏览器，重新加载并回到主页，再走到戦場列表"""
        self.log("      卡死恢复：重新加载 -> 主页 -> 戦場列表")
        try:
            if not self.boot():
                self.log("      重新加载后引擎未就绪")
                return False
            if not self.to_home():
                self.log("      重新加载后未进 Home")
                return False
            if not self.to_stage_select():
                self.log("      重新加载后未进 StageSelect")
                return False
            return self.to_battle_list()
        except Exception as e:
            self.log(f"      恢复异常: {e}")
            return False

    def result_ready(self, timeout=45):
        """等结算界面文字渲染出来（刚出现时是空的）"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                n = self.js("""() => {
                  const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
                  const r = ui.getChildByName('Result');
                  if (!r) return 0;
                  let c = 0;
                  const walk = (x) => {
                    try { const l = x.getComponent(cc.Label); if (l && l.string && x.activeInHierarchy) c++; } catch (e) {}
                    if (x.children) for (const y of x.children) walk(y);
                  };
                  walk(r);
                  return c;
                }""")
            except Exception:
                n = 0
            if n and int(n) > 0:
                return True
            self.page.wait_for_timeout(1000)
        return False

    # ---------- 结算 ----------
    def find_by_handler(self, handler):
        try:
            return self.js("(h)=>__gt.findByHandler(h)", handler)
        except Exception:
            return []

    def button_handlers(self):
        try:
            return self.js("__gt.buttonHandlers()")
        except Exception:
            return []


    def chapterend_buttons(self):
        """列出 chapterEnd 对话框里当前可点的按钮"""
        try:
            return self.js(r"""() => {
              const ui = cc.director.getScene().getChildByName('Canvas').getChildByName('UI');
              const base = ui.getChildByName('chapterEnd');
              if (!base) return [];
              const pathOf = (node) => {
                const parts = []; let n = node;
                while (n && n.parent) { parts.unshift(n.name || '?'); n = n.parent; }
                return 'scene/' + parts.join('/');
              };
              const out = [];
              const walk = (n, d) => {
                if (!n || d > 6) return;
                const b = n.getComponent ? n.getComponent(cc.Button) : null;
                if (b && n.activeInHierarchy) {
                  out.push({ path: pathOf(n),
                             handlers: (b.clickEvents || []).map(e => e.handler) });
                }
                if (n.children) for (const c of n.children) walk(c, d + 1);
              };
              walk(base, 0);
              return out;
            }""")
        except Exception:
            return []

    def choose_stay(self):
        """
        任务结束界面的选择：
          左「荘園に帰還」= 回主界面（有倒计时，会强制返回）
          右「続けて任務へ」= 留在选关  ← 我们要点这个
        优先按文字找，再退回 handler。
        """
        for attempt in range(1, 7):
            if self.ui_active("StageSelect"):
                return True

            # 0) 先关掉「チャプター進行」这类挡路弹窗
            #    （它的关闭按钮是图片，只能按坐标点：画面正中偏下）
            try:
                if self.js("(p)=>__gt.pathActive(p)", "scene/Canvas/UI/chapterEnd/dicision"):
                    pass
                else:
                    r = self.js("()=>__gt.viewportRect()")
                    if r:
                        self.page.mouse.click((r[0] + r[2]) / 2,
                                              r[1] + (r[3] - r[1]) * 0.71)
                        self.page.wait_for_timeout(1200)
            except Exception:
                pass

            # 1) 「続けて任務へ」= chapterEnd/dicision/stage，直接点节点的屏幕坐标
            try:
                xy = self.js("()=>__gt.clickXY('scene/Canvas/UI/chapterEnd/dicision/stage')")
                if xy:
                    self.log(f"      点「続けて任務へ」@({xy[0]:.0f},{xy[1]:.0f})")
                    self.page.mouse.click(xy[0], xy[1])
                    self.page.wait_for_timeout(3500)
                    if self.ui_active("StageSelect"):
                        return True
                    continue
            except Exception:
                pass

            # 2) 退回按文字找
            for label in ("続けて任務", "続けて", "任務へ"):
                hits = []
                try:
                    hits = self.js("(t)=>__gt.findByLabelStrict(t)", label)
                except Exception:
                    hits = []
                if hits:
                    self.click(hits[0]["path"], f"続けて任務へ(#{attempt})")
                    self.page.wait_for_timeout(3500)
                    if self.ui_active("StageSelect"):
                        return True
                    break

            if self.ui_active("StageSelect"):
                return True

            # 2) 退回 handler 方式 —— 只用鼠标点击，不调用该界面的组件函数
            paths = self.find_by_handler("ChapterEndStageBtn")
            if paths:
                self.click(paths[0], f"ChapterEndStageBtn(#{attempt})")
                self.page.wait_for_timeout(3000)
                continue

            # 3) 兜底：点对话框里任意按钮
            btns = self.chapterend_buttons()
            if btns:
                self.log(f"      按文字没找到，点对话框按钮: {[b['handlers'] for b in btns]}")
                self.click(btns[0]["path"], "chapterEnd任意")
                self.page.wait_for_timeout(3000)
                continue

            self.page.wait_for_timeout(1500)

        return self.ui_active("StageSelect")

    def settle_to_list(self, max_tries=5, force_refresh=False):
        """
        把游戏拉回「StageSelect 戦場列表」。
        force_refresh=True 时，即使已在 StageSelect 也重走一遍净化巡历，
        把滚动列表重建到顶部（应对滚动位置错乱导致点不中卡片）。
        """
        for i in range(max_tries):
            if self.ui_active("StageSelect"):
                if force_refresh:
                    self.log(f"      settle{i}: 强制刷新列表")
                    if self.to_battle_list():
                        return True
                    force_refresh = False
                    continue
                st = self.js("__gt.stageState()") or {}
                cards = self.js("__gt.cards()") or []
                if st.get("type") == 2 and len(cards) > 0:
                    return True
                if self.to_battle_list():
                    return True
                continue

            bs = self.battle_state()
            if bs.get("chapterEnd"):
                self.log(f"      settle{i}: 处理 chapterEnd")
                if self.choose_stay():
                    return True
                continue
            if bs.get("Result") or bs.get("Battle") or self.progress():
                # 战斗/结算没走完 -> 交给 run_battle 正常跑完，绝不乱点
                self.log(f"      settle{i}: 战斗流程未结束，交给 run_battle")
                out = self.run_battle(timeout=1200)
                if out == "chapterend":
                    if self.choose_stay():
                        return True
                elif out == "stage":
                    return True
                elif out == "hang":
                    if not self.restart_from_home():
                        return False
                continue
            if bs.get("Home"):
                self.log(f"      settle{i}: 从 Home 出发")
                self.to_stage_select()
                continue

            # 其它情况：尝试回 Home 再出发
            self.log(f"      settle{i}: screens={self.screens()} 尝试回 Home")
            self.to_home()
            self.to_stage_select()
        return False



def find_chrome():
    """找系统里的 Chrome；没有就用 Edge（Windows 自带，同样支持 CDP）"""
    cands = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def spawn_chrome(profile_dir=None, port=9222, width=1024, height=600,
                 maximized=False, headless=False, mute=False):
    """
    独立启动一个 Chrome（脱离当前进程树），并开启调试端口。
    返回 Popen 对象 —— 注意：之后用 attach() 通过 CDP 接管，
    这样即使本程序退出，浏览器也不会被关闭。
    """
    import subprocess

    exe = find_chrome()
    if not exe:
        raise RuntimeError("找不到系统 Chrome，请确认已安装")

    profile_dir = str(profile_dir or PROFILE)
    args = [
        exe,
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        # 关掉端侧 AI 模型下载和组件更新，避免 profile 膨胀到几个 GB
        "--disable-features=OptimizationGuideModelDownloading,OptimizationHints",
        "--disable-component-update",
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={port}",
        "--ignore-gpu-blocklist",
        "--enable-gpu",
        "--use-angle=d3d11",
        "--disable-blink-features=AutomationControlled",
    ]
    if headless:
        args.append("--headless=new")
    elif maximized:
        args.append("--start-maximized")
    else:
        # 加 92px 是浏览器自身标题栏/地址栏的高度，保证内容区是 16:9
        args += [f"--window-size={width},{height + 92}", "--window-position=120,40"]
    if mute:
        args.append("--mute-audio")
    args.append(SWITCH)

    # DETACHED_PROCESS(0x8) | CREATE_NEW_PROCESS_GROUP(0x200)
    return subprocess.Popen(args, creationflags=0x00000008 | 0x00000200,
                            close_fds=True)


def wait_port(port=9222, timeout=40) -> bool:
    """等调试端口就绪"""
    import socket as _s
    t0 = time.time()
    while time.time() - t0 < timeout:
        sk = _s.socket()
        sk.settimeout(0.5)
        try:
            if sk.connect_ex(("127.0.0.1", port)) == 0:
                return True
        finally:
            sk.close()
        time.sleep(0.5)
    return False


def attach(playwright, port=9222):
    """
    连接到一个「已经打开」的 Chrome（普通模式用）。
    要求该 Chrome 启动时带了 --remote-debugging-port=<port>。
    返回 (browser, context, page)
    """
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = None
    for p_ in ctx.pages:
        u = (p_.url or "").lower()
        if "nijitama" in u or "tamacolle" in u:
            page = p_
            break
    if page is None:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return browser, ctx, page


def launch(playwright, headless_new=True, gpu=True, retries=4, wait=6,
           width=960, height=600, maximized=False):
    """
    启动浏览器。
      gpu=True      -> 硬件渲染（省 CPU，推荐）
      gpu=False     -> SwiftShader 软件渲染（兼容性最好，但很吃 CPU）
      maximized=True-> 全屏（窗口最大化，跟随真实窗口尺寸）
    杀掉旧进程后 profile 可能短暂被占用，带重试。
    """
    args = [
        "--no-sandbox", "--mute-audio",
        "--disable-blink-features=AutomationControlled",
    ]
    if gpu:
        args += [
            "--ignore-gpu-blocklist",
            "--enable-gpu",
            "--use-angle=d3d11",
            "--disable-gpu-sandbox",
        ]
    else:
        args += [
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
            "--disable-gpu-sandbox",
        ]
    if headless_new:
        args.insert(0, "--headless=new")
    elif maximized:
        args.append("--start-maximized")
    else:
        # 小窗口：固定尺寸并放到左上角，避免被任务栏遮挡
        args += [f"--window-size={width},{height + 110}",
                 "--window-position=0,0"]

    last = None
    for i in range(1, retries + 1):
        try:
            kwargs = dict(headless=False, args=args)
            if headless_new or not maximized:
                kwargs["viewport"] = {"width": width, "height": height}
            else:
                kwargs["no_viewport"] = True     # 全屏时跟随真实窗口
            return playwright.chromium.launch_persistent_context(
                str(PROFILE), **kwargs)
        except Exception as e:
            last = e
            print(f"[launch] 第 {i} 次启动失败：{str(e)[:120]}，{wait}s 后重试", flush=True)
            time.sleep(wait)
    raise last
