# battle/ai_controller.py
import random
from battle.buff import Target, Effect 

class AIController:
    def __init__(self, ch=None, ui=None):
        self.character = ch
        self.ui = ui

    # ★檢查角色是否身上有某個效果（duration > 0 視為仍有效）
    def _has_effect(self, ch, eff) -> bool:
        for b in getattr(ch, "buffs", []):
            if getattr(b, "effect", None) == eff and getattr(b, "duration", 0) != 0:
                return True
        return False

    def choose_skill(self, actor=None):
        ch = actor or self.character
        if not ch:
            return None
        usable = [sk for sk in ch.skills if sk.cdtime == 0]
        return random.choice(usable) if usable else None

    def choose_target(self, buff, team, enemies, actor=None):
        ch = actor or self.character
        if buff.target == Target.SELF:
            return ch

        elif buff.target == Target.TEAM:
            return [a for a in team if not a.is_dead()]

        elif buff.target == Target.ALLY:
            living = [a for a in team if not a.is_dead()]
            return random.choice(living) if living else None

        elif buff.target == Target.ENEMY:
            living = [e for e in enemies if not e.is_dead()]

            taunted = [e for e in living if self._has_effect(e, Effect.TAUNT)]
            if taunted:
                return random.choice(taunted)

            return random.choice(living) if living else None

        elif buff.target == Target.ENEMIES:
            # 全體 AoE 無視嘲諷
            return [e for e in enemies if not e.is_dead()]

        return None
