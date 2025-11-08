# main_menu.py
import tkinter as tk
from tkinter import ttk, messagebox
import os

from save.save_manager import SaveManager
from main_gui import main as start_game
from character.character import Character
from character.jobs_library import JobLibrary
from battle.skill_library import SkillLibrary

# =====================
# 強化角色技能視窗
# =====================
class TrainingUI(tk.Toplevel):
    def __init__(self, parent, chars):
        super().__init__(parent)
        self.title("角色強化")
        self.geometry("420x360")
        self.chars = chars

        ttk.Label(self, text="選擇要強化的角色：", font=("Segoe UI", 12, "bold")).pack(pady=8)

        for ch in self.chars:
            ttk.Button(self, text=f"{ch.name} ({ch.job})",
                       command=lambda c=ch: self.show_char(c)).pack(pady=5, fill="x", padx=40)

        ttk.Button(self, text="返回主選單", command=self.close).pack(pady=12)

    def show_char(self, ch):
        win = tk.Toplevel(self)
        win.title(f"{ch.name} 的技能")
        ttk.Label(win, text=f"{ch.name} — {ch.job}", font=("Segoe UI", 11, "bold")).pack(pady=5)
        for i, sk in enumerate(ch.skills):
            text = f"{i+1}. {sk.name} Lv.{sk.currLevel}（冷卻 {sk.cd} 回合）"
            ttk.Button(win, text=text,
                       command=lambda s=sk: self.upgrade_skill(s, ch)).pack(pady=3, fill="x", padx=30)

    def upgrade_skill(self, skill, ch):
        upgraded = skill.level_up()
        if upgraded:
            SaveManager.save_game(self.chars)  # 即時存檔
            messagebox.showinfo("升級成功", f"{ch.name} 的技能【{skill.name}】升至 Lv.{skill.currLevel}")

    def close(self):
        self.destroy()
        self.master.deiconify()


# =====================
# 主選單
# =====================
class MainMenuUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("冒險者之章 — 主選單")
        self.geometry("400x320")
        self.resizable(False, False)

        ttk.Label(self, text="⚔️ 冒險者之章", font=("Segoe UI", 16, "bold")).pack(pady=25)

        ttk.Button(self, text="▶ 繼續冒險", command=self.continue_game).pack(pady=8, ipadx=10)
        ttk.Button(self, text="🌟 重新開始", command=self.restart_game).pack(pady=8, ipadx=10)
        ttk.Button(self, text="💪 強化角色", command=self.open_training).pack(pady=8, ipadx=10)
        ttk.Button(self, text="❌ 離開遊戲", command=self.destroy).pack(pady=8, ipadx=10)

    # === 功能 ===
    def continue_game(self):
        if not os.path.exists("save/player_data.json"):
            messagebox.showinfo("提示", "目前沒有存檔，請先開始新遊戲。")
            return
        self.destroy()
        start_game()

    def restart_game(self):
        if os.path.exists("save/player_data.json"):
            os.remove("save/player_data.json")
        messagebox.showinfo("新冒險", "舊存檔已刪除，將從序章開始。")
        self.destroy()
        start_game()

    def open_training(self):
        chars, _ = SaveManager.load_game()
        if not chars:
            # 若沒有存檔，就先建立初始角色
            JobLibrary.init("jobs.json")
            SkillLibrary.init("skills.json")
            chars = [
                Character("勇者", "Warrior"),
                Character("補師", "Cleric"),
                Character("弓箭手", "Archer")
            ]
        self.withdraw()
        TrainingUI(self, chars)


if __name__ == "__main__":
    MainMenuUI().mainloop()
    