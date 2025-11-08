# story/ui_adapter.py
import tkinter as tk
from tkinter import ttk

class StoryUIAdapter:
    def __init__(self, root):
        # root 
        self.root = root
        self._overlay = None

    def _open_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            try:
                self._overlay.destroy()
            except Exception:
                pass

        # 以 place 方式鋪滿整個 root
        self._overlay = tk.Frame(self.root, bg="#0e0e10")
        self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay.lift()           # 疊到最上層
        self._overlay.focus_set()      # 接收鍵盤焦點

        # ：攔截滑鼠事件
        self._overlay.bind("<Button>", lambda e: "break")
        self._overlay.bind("<ButtonRelease>", lambda e: "break")
        self._overlay.bind("<MouseWheel>", lambda e: "break")

        return self._overlay

    # story/ui_adapter.py
    def _close_overlay(self, cb=None, *args):
        #關掉遮罩
        if self._overlay and self._overlay.winfo_exists():
            try:
                self._overlay.destroy()
            except Exception:
                pass
        self._overlay = None
        try:
            self.root.focus_set()
        except Exception:
            pass

        # 回呼
        if cb:
            cb(*args)

    # 關閉
    def close(self):
        self._close_overlay(None)


    def show_dialogue(self, lines, choices=None, on_choice=None, on_done=None):
        ov = self._open_overlay()

        # 置中面板
        panel = ttk.Frame(ov, padding=16)
        panel.place(relx=0.5, rely=0.5, anchor="center")

        # 內容
        text = tk.Text(panel, width=60, height=10, wrap="word", state="normal")
        text.grid(row=0, column=0, sticky="nsew")
        for ln in lines or []:
            text.insert("end", ln + "\n")
        text.config(state="disabled")

        # 滾動條
        scroll = ttk.Scrollbar(panel, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        # 按鈕列
        btnbar = ttk.Frame(panel)
        btnbar.grid(row=1, column=0, columnspan=2, sticky="e", pady=(12, 0))

        # 面板伸縮
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        # 關閉 + callback 包裝
        def close_and(cb=None, *args):
            self._close_overlay(cb, *args)

        if choices:
            # 分支選項：
            for i, label in enumerate(choices):
                ttk.Button(btnbar, text=label,
                           command=lambda idx=i: close_and(on_choice, idx)).pack(side="left", padx=6)
        else:
            # 單一路徑：
            ttk.Button(btnbar, text="繼續",
                       command=lambda: close_and(on_done)).pack(side="right")

