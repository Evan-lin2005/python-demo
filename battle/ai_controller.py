# battle/ai_controller.py
import random
from battle.buff import Target, Effect, Buff
import json, os
from enum import Enum, auto
from character.character import Character

class Feature(Enum):
    TANK = auto()
    DPS = auto()
    SUPPORT = auto()
    
# 預設分數，當 profile.json 中沒有定義時使用
DEFAULT_PRIORITY = {
    "PHYSICDAMAGE": 10,
    "MAGICDAMAGE": 10,
    "ADDHP": 15,
    "ADDSHIELD": 10,
    "ADDPATK": 8,
    "ADDMATK": 8,
    "ADDPDEF": 5,
    "ADDMDEF": 5,
    "STUN": 20,
    "INVINCIBLE": 30,
    "CONSUME_MARK": 25,
    "TAUNT": 15,
}

class AIController:
    def __init__(self, ch=None, ui=None, feature=None):
        self.character = ch
        self.ui = ui
        self.feature = feature
        
        profile_name = "Default"
        if self.feature:
            try:
                profile_name = self.feature.name  
            except Exception:
                pass
        self.profile = self.load_profile(profile_name)

    def _has_effect(self, ch, eff) -> bool:
        
        for b in getattr(ch, "buffs", []):
            if getattr(b, "effect", None) == eff and getattr(b, "duration", 0) != 0:
                return True
        return False
    
    @staticmethod
    def load_profile(name):
        path = os.path.join("battle", "ai_profiles.json")
        if not os.path.exists(path):
            return {"skill_priority": DEFAULT_PRIORITY, "target_rule": "LOWEST_HP"}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profile = data.get(name, data.get("Default", {}))
        if "skill_priority" not in profile:
            profile["skill_priority"] = DEFAULT_PRIORITY
        return profile
    
    def score_skill(self, skill, actor, allies, enemies):
        total_score = 0
        living_enemies = [e for e in enemies if not e.is_dead()]
        living_allies = [a for a in allies if not a.is_dead()]

        # 強化 1：遍歷所有 buff 效果並加總分數
        for buff in skill.buffs:
            effect_name = buff.effect.name
            score = self.profile["skill_priority"].get(effect_name, 1) # 讀取基礎分

            # 額外策略：根據戰場情況動態加分
            if effect_name == "CONSUME_MARK":
                # 強化 2：檢查特定的 mark_key
                key = getattr(buff, "mark_key", None)
                if key and any(getattr(e, "_marks", {}).get(key, 0) > 0 for e in living_enemies):
                    score += 50  # 大幅加分

            elif effect_name == "ADDHP":
                if not living_allies: continue
                low_hp_ratio = min(a.hp / max(1, a.max_hp) for a in living_allies)
                score += int((1 - low_hp_ratio) * 30) # 隊友血越少，分數越高
            
            elif effect_name == "STUN" or effect_name == "INVINCIBLE":
                score += 10 # 戰術技能額外加分

            total_score += score

        return total_score
    
    def choose_skill(self, actor=None, allies=None, enemies=None):
        ch = actor or self.character
        if not ch or not allies or not enemies:
            return None
            
        usable = [sk for sk in ch.skills if sk.cdtime == 0]
        if not usable:
            return None

        sorted_usable = sorted(
            usable, 
            key=lambda sk: self.score_skill(sk, ch, allies, enemies), 
            reverse=True
        )
        
        return sorted_usable[0] # 返回分數最高者

    def choose_target(self, buff, team, enemies, actor=None):
        ch = actor or self.character
        living_team = [a for a in team if not a.is_dead()]
        living_enemies = [e for e in enemies if not e.is_dead()]

        if buff.target == Target.SELF:
            return ch

        elif buff.target == Target.TEAM:
            return living_team

        elif buff.target == Target.ALLY:
            if not living_team: return None
            return self.choose_teammate(buff, living_team, ch)
            
        elif buff.target == Target.ENEMY:
            if not living_enemies: return None
            return self.choose_enemies(buff, living_enemies, ch)

        elif buff.target == Target.ENEMIES:
            return living_enemies

        return None

    def choose_teammate(self, buff: Buff, team: list[Character], actor):
        
        if buff.effect == Effect.ADDHP or buff.effect == Effect.INVINCIBLE or buff.effect == Effect.ADDSHIELD:
            # 根據血量百分比排序，優先套用血量最低者
            sorted_team = sorted(team, key=lambda character: character.hp / max(1, character.max_hp))
            return sorted_team[0]
            
        elif buff.effect == Effect.ADDPATK or buff.effect == Effect.ADDMATK:
            if self.feature == Feature.DPS: # 本身是傷害型
                return actor
            # 優先攻擊力 (物攻+魔攻)
            sorted_team = sorted(team, key=lambda character: character.patk + character.matk)
            return sorted_team[-1] # 返回最高者
            
        elif buff.effect == Effect.ADDCRI or buff.effect == Effect.ADDCRIDMG:
            sorted_team = sorted(team, key=lambda character: character.cri)
            return sorted_team[-1]
            
        elif buff.effect == Effect.ADDPDEF or buff.effect == Effect.ADDMDEF:
            if self.feature == Feature.TANK: # 本身是坦克
                return actor
            sorted_team = sorted(team, key=lambda ch: ch.pdef + ch.mdef) #防禦力最弱
            return sorted_team[0]
            
        else: 
            return random.choice(team)

    def choose_enemies(self, buff: Buff, enemies: list[Character], actor):
        taunted = [e for e in enemies if self._has_effect(e, Effect.TAUNT)]
        if taunted:
            return random.choice(taunted)

        if buff.effect == Effect.CONSUME_MARK:
            key = getattr(buff, "mark_key", None)
            if key:
                consumed = [e for e in enemies if getattr(e, "_marks", {}).get(key, 0) > 0]
                if consumed:
                    sorted_consumed = sorted(consumed, key=lambda ch: ch.hp)
                    return sorted_consumed[0] 

        if buff.effect == Effect.PHYSICDAMAGE or buff.effect == Effect.MAGICDAMAGE or buff.effect == Effect.STUN:
            
            sorted_enemies = sorted(enemies, key=lambda ch: ch.hp)
            return sorted_enemies[0]
            
        elif buff.effect == Effect.ADDPATK or buff.effect == Effect.ADDMATK: 
            sorted_enemies = sorted(enemies, key=lambda ch: ch.patk + ch.matk)
            return sorted_enemies[-1] 
        elif buff.effect == Effect.ADDPDEF or buff.effect == Effect.ADDMDEF: 
            sorted_enemies = sorted(enemies, key=lambda ch: ch.pdef + ch.mdef)
            return sorted_enemies[0]  
        else:
            return random.choice(enemies)