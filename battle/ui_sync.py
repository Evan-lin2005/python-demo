# battle/ui_sync.py
from battle.event_manager import event_manager, EventType

class HealthBarSync:
    """
    負責監聽戰鬥事件並更新 UI，
    確保子執行緒發出的事件安全地回到主執行緒執行。
    """
    def __init__(self, ui, characters):
        self.ui = ui
        self.characters = list(characters)
        self._bind()

    def _on_ui(self, fn, *args):
        try:
            self.ui.call_on_ui(fn, *args)
        except Exception:
            try:
                self.ui.after(0, lambda: fn(*args))
            except Exception:
                pass

    def _refresh_for(self, ch):
        if hasattr(self.ui, "update_health_bar"):
            self._on_ui(self.ui.update_health_bar, ch)
        if hasattr(self.ui, "update_shield_bar"):
            self._on_ui(self.ui.update_shield_bar, ch)
        if hasattr(self.ui, "update_status_panel"):
            self._on_ui(self.ui.update_status_panel, ch)

    def _refresh_all(self):
        for ch in self.characters:
            self._refresh_for(ch)

    def _bind(self):
        # 造成/承受傷害 → 更新相關角色
        def on_after_take_damage(ev, ctx):
            tgt = getattr(ctx, "target", None)
            act = getattr(ctx, "actor",  None)
            if tgt: self._refresh_for(tgt)
            if act: self._refresh_for(act)

        # 技能結算（多半會套/消 buff）→ 全體刷新一次
        def on_skill_resolve(ev, ctx):
            self._refresh_all()

        # 套/移除 buff（如護盾）
        def on_buff_change(ev, ctx):
            tgt = getattr(ctx, "target", None) or getattr(ctx, "owner", None)
            if tgt: self._refresh_for(tgt)

        # 回合邊界（持續效果、DOT/護盾衰減等）→ 全體刷新
        def on_turn(ev, ctx):
            self._refresh_all()

        event_manager.subscribe(EventType.AFTER_TAKE_DAMAGE, on_after_take_damage, priority=-1000, owner=self)
        event_manager.subscribe(EventType.SKILL_RESOLVE,     on_skill_resolve,     priority=-1000, owner=self)
        event_manager.subscribe(EventType.APPLY_BUFF,        on_buff_change,       priority=-1000, owner=self)
        event_manager.subscribe(EventType.REMOVE_BUFF,       on_buff_change,       priority=-1000, owner=self)
        event_manager.subscribe(EventType.TURN_START,        on_turn,              priority=-1000, owner=self)
        event_manager.subscribe(EventType.TURN_END,          on_turn,              priority=-1000, owner=self)


    def dispose(self):
        event_manager.unsubscribe_owner(self)
