import threading
import traceback
import tkinter as tk
from tkinter import ttk

from battle.ui_sync import HealthBarSync
from battle.battle_log import BattleLog, set_log_sink
from battle.event_manager import event_manager, EventType
from battle.battle_manager import BattleManager
from battle.effect_registry import EffectRegistry
from battle.skill_library import SkillLibrary
from character.jobs_library import JobLibrary
from character.character import Character
import os
import math


# -----------------------------
#  技能冷卻及敘述
# -----------------------------
# gui.py

import tkinter as tk
from tkinter import ttk

# -------- Tooltip 類 --------
class ToolTip:
    def __init__(self, widget, text: str, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay  # 毫秒
        self.tipwindow = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)

    def _schedule(self, event=None):
        # 延遲顯示 tooltip
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # 移除標題列
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw, text=self.text, justify="left",
            background="#ffffe0", relief="solid", borderwidth=1,
            font=("Segoe UI", 9)
        )
        label.pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

# -----------------------------
# 腳色頭像
# -----------------------------
class AvatarProvider:

    def __init__(self, base_dir="assets/avatars", size=(48, 48), keep_aspect=True):
        self.base_dir = base_dir
        self.size = size            # (w, h)
        self.keep_aspect = keep_aspect
        self._cache = {}            # key: (name, job, size) -> PhotoImage

    def _find_path(self, char):
        name = getattr(char, "name", None)
        job  = getattr(char, "job", None)
        cands = []
        if name: cands.append(f"{name}.png")
        if job:  cands.append(f"{job}.png")
        cands.append("default.png")
        for fn in cands:
            p = os.path.join(self.base_dir, fn)
            if os.path.exists(p):
                return p
        return None

    def load(self, char, tk_root=None):
        key = (getattr(char, "name", None), getattr(char, "job", None), self.size)
        if key in self._cache:
            return self._cache[key]

        path = self._find_path(char)
        if not path:
            return None

        w, h = self.size
        photo = None

        # 1)Pillow
        try:
            from PIL import Image, ImageTk, ImageOps  # type: ignore
            img = Image.open(path).convert("RGBA")
            if self.keep_aspect:
                # thumbnail 會維持比例，把最長邊縮到指定框內
                img.thumbnail((w, h), Image.LANCZOS)
                
            else:
                img = img.resize((w, h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img, master=tk_root)

        except Exception:
            # 2) 沒 Pillow 時，至少用 subsample 強制縮小到不超過 (w, h)
            import tkinter as tk
            raw = tk.PhotoImage(file=path, master=tk_root)
            rw, rh = raw.width(), raw.height()
            # 計算整數縮小倍率（越大縮得越多），確保不超過目標框
            fx = max(1, math.ceil(rw / w)) if w else 1
            fy = max(1, math.ceil(rh / h)) if h else 1
            factor = max(fx, fy)
            photo = raw.subsample(factor, factor)

        self._cache[key] = photo
        return photo
# -----------------------------
# GUI 控制器：給 BattleManager 呼叫
# -----------------------------
class GUIController:
    def __init__(self, ui=None):
        self.ui = ui
        self._lock = threading.Condition()
        self._skill_choice = None
        self._target_choice = None

    def select_skill(self, actor):
        #  UI 自己從 actor.skills 讀
        self.ui.call_on_ui(self.ui.show_skill_choices, actor, self._on_skill_selected)
        with self._lock:
            self._skill_choice = None
            while self._skill_choice is None:
                self._lock.wait(timeout=10)
            return self._skill_choice

    def _on_skill_selected(self, idx: int):
        with self._lock:
            self._skill_choice = idx
            self._lock.notify()

    # BattleManager 呼叫：請玩家從候選目標中選一個（回傳 Character）
    def select_target(self, candidates, prompt="選擇目標"):
        living = [c for c in candidates if not c.is_dead()]
        self.ui.call_on_ui(self.ui.show_target_choices, prompt, living, self._on_target_selected)
        with self._lock:
            self._target_choice = None
            while self._target_choice is None:
                self._lock.wait()
            return self._target_choice
    #呼叫 choose_target；
    def choose_target(self, candidates):
        return self.select_target(candidates)

    def _on_target_selected(self, target):
        with self._lock:
            self._target_choice = target
            self._lock.notify()

    # BattleManager 查隊伍是否還有人活著
    def alive(self, team):
        return any(not c.is_dead() for c in team)

    # 給 BM / 其他模組使用：安全地要求 UI 執行某函式（回到主執行緒）
    def call_on_ui(self, fn, *args, **kwargs):
        if self.ui:
            self.ui.call_on_ui(fn, *args, **kwargs)


# -----------------------------
# 角色面板元件
# -----------------------------

class CharPanel(ttk.Frame):
    def __init__(self, master, char: Character, avatar_provider=None):
        super().__init__(master)
        self.char = char
        self._avatar_provider = avatar_provider
        self._avatar_photo = None
        self.name_var = tk.StringVar()
        self.hp_var = tk.StringVar()

        self.lbl_avatar = tk.Label(self)
        self.lbl_avatar.grid(row=0, column=0, rowspan=3, padx=(0, 8), sticky="n")

        self.lbl_name = ttk.Label(self, textvariable=self.name_var, font=("Segoe UI", 10, "bold"))
        self.lbl_name.grid(row=0, column=1, sticky="w")

        # 畫 HP/盾
        self.bar_w, self.bar_h = 160, 14
        self.hp_canvas = tk.Canvas(self, width=self.bar_w, height=self.bar_h,
                                   highlightthickness=0, bg="#222")
        self.hp_canvas.grid(row=1, column=1, sticky="ew", pady=2)

        # 背景灰條 / 綠色 HP 條
        self._hp_bg = self.hp_canvas.create_rectangle(0, 0, self.bar_w, self.bar_h,
                                                      fill="#444", outline="")
        self._hp_fg = self.hp_canvas.create_rectangle(0, 0, 1, self.bar_h,
                                                      fill="#2ecc71", outline="")
        # 盾白塊集合
        self._shield_blocks = []

        self.lbl_hp = ttk.Label(self, textvariable=self.hp_var)
        self.lbl_hp.grid(row=2, column=1, sticky="w")

        self.columnconfigure(1, weight=1)
        self.refresh()

    def _refresh_avatar(self):
        if not self._avatar_provider:
            return
        tk_root = self.winfo_toplevel()
        photo = self._avatar_provider.load(self.char, tk_root)
        if photo:
            self._avatar_photo = photo
            self.lbl_avatar.configure(image=self._avatar_photo)
        else:
            # 沒圖時清空
            self.lbl_avatar.configure(image="")
            self._avatar_photo = None

    def _draw_hp(self):
        c = self.char
        max_hp = max(1, int(getattr(c, "max_hp", 1)))
        hp = max(0, int(getattr(c, "hp", 0)))
        ratio = max(0.0, min(1.0, hp / max_hp))
        w = int(self.bar_w * ratio)
        self.hp_canvas.coords(self._hp_fg, 0, 0, w, self.bar_h)

    def _draw_shield(self):
        for r in self._shield_blocks:
            self.hp_canvas.delete(r)
        self._shield_blocks.clear()

        max_hp = max(1, int(getattr(self.char, "max_hp", 1)))
        shield = int(getattr(self.char, "shield", 0))
        if shield <= 0:
            return

        hp_ratio = max(0.0, min(1.0, self.char.hp / max_hp))
        start_x  = int(self.bar_w * hp_ratio)
        shield_w = int(self.bar_w * max(0.0, min(1.0, shield / max_hp)))
        end_x    = start_x + shield_w            # ★ 盾終點 = 起點 + 長度

        end_x = min(end_x, self.bar_w)

        y0, y1 = 2, self.bar_h - 2
        block, gap = 6, 1
        x = start_x
        while x + block <= end_x:
            r = self.hp_canvas.create_rectangle(x, y0, x + block, y1,
                                                fill="#ffffff", outline="#ffffff")
            self._shield_blocks.append(r)
            x += block + gap
        if x < end_x:
            r = self.hp_canvas.create_rectangle(x, y0, end_x, y1,
                                                fill="#ffffff", outline="#ffffff")
            self._shield_blocks.append(r)



    def refresh(self):
        c = self.char
        name = getattr(c, "name", "???")
        hp = max(0, int(getattr(c, "hp", 0)))
        max_hp = max(1, int(getattr(c, "max_hp", 1)))
        shield = int(getattr(c, "shield", 0))

        self.name_var.set(name + ("（死亡）" if getattr(c, "is_dead", lambda: False)() else ""))
        self.hp_var.set(f"HP {hp}/{max_hp}  盾 {shield}")

        self._refresh_avatar()
        self._draw_hp()
        self._draw_shield()

    def update_health_from_char(self): self._draw_hp(); self.hp_var.set(f"HP {int(self.char.hp)}/{int(self.char.max_hp)}  盾 {int(getattr(self.char,'shield',0))}")
    def update_shield_from_char(self): self._draw_shield(); self.hp_var.set(f"HP {int(self.char.hp)}/{int(self.char.max_hp)}  盾 {int(getattr(self.char,'shield',0))}")

# -----------------------------
# 主視窗
# -----------------------------
class BattleUI(tk.Tk):
    def __init__(self, allies, enemies, controller: GUIController):
        super().__init__()
        self.title("回合制戰鬥（GUI）")
        self.geometry("820x600")
        self.controller = controller
        self.controller.ui = self
        self.allies = allies
        self.enemies = enemies
        self.avatar_provider = AvatarProvider(base_dir="assets/avatars", size=(48, 48))

        # 上方：友方、敵方面板
        frm_top = ttk.Frame(self)
        frm_top.pack(side="top", fill="x", padx=10, pady=8)

        self.frm_allies = ttk.LabelFrame(frm_top, text="我方")
        self.frm_allies.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.frm_enemies = ttk.LabelFrame(frm_top, text="敵方")
        self.frm_enemies.pack(side="left", expand=True, fill="x")

        # ★ 傳入 avatar_provider
        self.ally_panels = [CharPanel(self.frm_allies, c, self.avatar_provider) for c in self.allies]
        self.enemy_panels = [CharPanel(self.frm_enemies, c, self.avatar_provider) for c in self.enemies]
        for p in self.ally_panels: p.pack(anchor="w", fill="x", padx=8, pady=4)
        for p in self.enemy_panels: p.pack(anchor="w", fill="x", padx=8, pady=4)

        # 🔗 建立角色→面板對應
        self._rebuild_panel_map()

        # 中段：操作區（技能/目標選擇）
        self.frm_ops = ttk.LabelFrame(self, text="行動")
        self.frm_ops.pack(side="top", fill="x", padx=10, pady=8)

        self.lbl_prompt = ttk.Label(self.frm_ops, text="—")
        self.lbl_prompt.grid(row=0, column=0, sticky="w", pady=3)

        self.frm_buttons = ttk.Frame(self.frm_ops)
        self.frm_buttons.grid(row=1, column=0, sticky="w", pady=4)

        # 下方：戰鬥日誌
        frm_log = ttk.LabelFrame(self, text="戰鬥記錄")
        frm_log.pack(side="top", fill="both", expand=True, padx=10, pady=8)

        self.txt_log = tk.Text(frm_log, height=16, wrap="word")
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frm_log, command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log["yscrollcommand"] = sb.set

        # 把 BattleLog 導到 UI
        set_log_sink(lambda msg: self.call_on_ui(self.append_log, msg))
        # 立即刷新一次
        self.refresh_panels()
        # ui/gui.py -> class BattleUI(...):

    def update_health_bar(self, ch):
       
        bar = None
        if hasattr(self, "hp_bars"):
            bar = self.hp_bars.get(ch) or self.hp_bars.get(getattr(ch, "name", None))
        if bar:
            val = 0 if ch.max_hp <= 0 else int(round(ch.hp / ch.max_hp * 100))
            val = max(0, min(100, val))
            try:
                bar["value"] = val
            except Exception:
                # 有些皮膚需要用 .config()
                bar.config(value=val)

        #也一起更新 HP 文字標籤
        if hasattr(self, "hp_labels"):
            lbl = self.hp_labels.get(ch) or self.hp_labels.get(getattr(ch, "name", None))
            if lbl:
                lbl.config(text=f"{int(ch.hp)}/{int(ch.max_hp)}")
    def _rebuild_panel_map(self):
            self._panel_map = {}
            for p in (self.ally_panels + self.enemy_panels):
                self._panel_map[id(p.char)] = p

    def _find_panel_for(self, ch):
        return self._panel_map.get(id(ch))

    def update_health_bar(self, ch):
        panel = self._find_panel_for(ch)
        if panel:
            panel.update_health_from_char()

    def update_shield_bar(self, ch):
        panel = self._find_panel_for(ch)
        if panel:
            panel.update_shield_from_char()

    def update_status_panel(self, ch):

        pass
        
    def call_on_ui(self, fn, *args, **kwargs):
        # 把 UI 操作排回 Tk 主執行緒
        try:
            self.after_idle(lambda: fn(*args, **kwargs))
        except Exception:
            # 不要讓事件炸掉戰鬥執行緒
            import traceback; print("[call_on_ui error]\n", traceback.format_exc())

    def refresh_panels(self):
        for p in self.ally_panels + self.enemy_panels:
            p.refresh()
            
    def set_enemies(self, enemies):
        """替換敵方隊伍並重建右側面板"""
        self.enemies = list(enemies)

        # 1) 把舊的 panel widget 清掉
        for p in getattr(self, "enemy_panels", []):
            try:
                p.destroy()
            except Exception:
                pass

        # 2) 建立新面板
        self.enemy_panels = [CharPanel(self.frm_enemies, c, self.avatar_provider) for c in self.enemies]
        for p in self.enemy_panels:
            p.pack(anchor="w", fill="x", padx=8, pady=4)

        # 3) 立即刷新一次
        self.refresh_panels()


    def append_log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

    def clear_choices(self):
        for w in self.frm_buttons.winfo_children():
            w.destroy()

    def show_skill_choices(self, actor, *rest):
        if not rest:
            raise TypeError("show_skill_choices 需要 on_choice 回呼")

        on_choice = rest[-1]
        skills = getattr(actor, "skills", [])

        self.clear_choices()
        self.lbl_prompt.config(text=f"{actor.name}：選擇技能")

        if not skills:
            ttk.Button(self.frm_buttons, text="（無可用技能）", state=tk.DISABLED)\
                .grid(row=0, column=0, padx=6, pady=4, sticky="w")
            ttk.Button(self.frm_buttons, text="結束回合", command=lambda: on_choice(-1))\
                .grid(row=0, column=1, padx=6, pady=4, sticky="w")
            return

        for i, sk in enumerate(skills):
            btn = ttk.Button(
                self.frm_buttons,
                text=f"{i}. {sk.name}",
                command=lambda idx=i: on_choice(idx)
            )
            btn.grid(row=i // 4, column=i % 4, padx=6, pady=4, sticky="w")

            # 掛 Tooltip：顯示技能描述 + 冷卻狀態
            tip_text = f"{sk.desc}\n冷卻: {sk.cdtime}/{sk.cd}"
            ToolTip(btn, tip_text)


    def show_target_choices(self, prompt: str, candidates, on_choice):
        self.clear_choices()
        self.lbl_prompt.config(text=prompt)
        for i, c in enumerate(candidates):
            desc = f"{c.name} ({int(c.hp)}/{int(c.max_hp)})"
            btn = ttk.Button(self.frm_buttons, text=desc, command=lambda target=c: on_choice(target))
            btn.grid(row=i // 4, column=i % 4, padx=6, pady=4, sticky="w")
            
    def reset_teams(self, allies, enemies):
        # 1) 關掉舊的同步器（避免事件監聽洩漏）
        if hasattr(self, "_hp_sync") and self._hp_sync:
            try: self._hp_sync.dispose()
            except: pass
            self._hp_sync = None

        # 2) 清舊面板、重建新面板
        self.allies = list(allies)
        self.enemies = list(enemies)

        for frame in (getattr(self, "ally_panels", []), getattr(self, "enemy_panels", [])):
            for p in frame:
                try: p.destroy()
                except: pass

        self.ally_panels = [CharPanel(self.frm_allies, c, self.avatar_provider) for c in self.allies]
        for p in self.ally_panels:
            p.pack(anchor="w", fill="x", padx=8, pady=4)

        self.enemy_panels = [CharPanel(self.frm_enemies, c, self.avatar_provider) for c in self.enemies]
        for p in self.enemy_panels:
            p.pack(anchor="w", fill="x", padx=8, pady=4)
        self._rebuild_panel_map()              #重建角色→面板映射
        self._hp_sync = HealthBarSync(self, self.allies + self.enemies)

        # 4) 刷新
        self.refresh_panels()
