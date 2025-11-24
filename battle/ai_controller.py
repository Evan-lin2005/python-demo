import random
import json, os
from battle.buff import Target, Effect
from enum import Enum, auto

# 定義目標篩選策略的映射
class TargetStrategy:
    @staticmethod
    def low_hp(units, actor):
        # 優先血量百分比最低
        return sorted(units, key=lambda u: u.hp / max(1, u.max_hp))[0]
    
    @staticmethod
    def high_hp(units, actor):
        # 優先血量數值最高
        return sorted(units, key=lambda u: u.hp, reverse=True)[0]
    
    @staticmethod
    def low_def(units, actor):
        # 優先雙防總和最低
        return sorted(units, key=lambda u: u.pdef + u.mdef)[0]
    
    @staticmethod
    def high_atk(units, actor):
        # 優先雙攻總和最高 (威脅最大)
        return sorted(units, key=lambda u: u.patk + u.matk, reverse=True)[0]

    @staticmethod
    def random_target(units, actor):
        return random.choice(units)

    @staticmethod
    def self_target(units, actor):
        return actor

class AIController:
    # 策略對應表：將 JSON 字串映射到函式
    STRATEGIES = {
        "LOW_HP": TargetStrategy.low_hp,
        "HIGH_HP": TargetStrategy.high_hp,
        "WEAKEST_DEF": TargetStrategy.low_def,
        "HIGHEST_ATK": TargetStrategy.high_atk,
        "RANDOM": TargetStrategy.random_target,
        "SELF": TargetStrategy.self_target
    }

    def __init__(self, ch=None, ui=None, feature=None):
        self.character = ch
        self.ui = ui
        self.feature = feature # 保留 Feature Enum 作為備用或標記
        
        # 獲取 Profile 名稱
        profile_name = "Default"
        if hasattr(feature, "name"):
            profile_name = feature.name
        
        self.profile = self.load_profile(profile_name)

    @staticmethod
    def load_profile(name):
        path = os.path.join("battle", "ai_profiles.json")
        if not os.path.exists(path):
            # 預設回傳，防止崩潰
            return {"skill_priority": {}, "target_rule": "RANDOM"}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 取得設定，如果找不到則使用 Default
        return data.get(name, data.get("Default", {}))

    def score_skill(self, skill, actor, allies, enemies):
        total_score = 0
        living_enemies = [e for e in enemies if not e.is_dead()]
        living_allies = [a for a in allies if not a.is_dead()]

        # 1. 基礎權重計算 
        for buff in skill.buffs:
            effect_name = buff.effect.name
            # 從 profile 讀取分數
            score = self.profile.get("skill_priority", {}).get(effect_name, 1)
            
            # 2. 動態情境加分 
            
            # 印記引爆 (Combo)
            if effect_name == "CONSUME_MARK":
                key = getattr(buff, "mark_key", None)
                # 檢查是否有任何敵人身上有這層印記
                if key and any(getattr(e, "_marks", {}).get(key, 0) > 0 for e in living_enemies):
                    score += 40 

            # 治療邏輯 (緊急救援)
            elif effect_name == "ADDHP":
                if living_allies:
                    lowest_hp_ratio = min(a.hp / max(1, a.max_hp) for a in living_allies)
                    if lowest_hp_ratio < 0.3: # 瀕死
                        score += 50
                    elif lowest_hp_ratio < 0.6: # 受傷
                        score += 20
                    else: # 滿血時降低治療意願
                        score -= 10

            # 自身保命 (坦克/脆皮邏輯)
            elif effect_name in ["ADDSHIELD", "INVINCIBLE", "ADDPDEF"]:
                hp_ratio = actor.hp / max(1, actor.max_hp)
                if hp_ratio < 0.4:
                    score += 25

            total_score += score
        
        # 3. 斬殺計算 

        return total_score

    def choose_skill(self, actor=None, allies=None, enemies=None):
        ch = actor or self.character
        if not ch or not allies or not enemies:
            return None
            
        usable = [sk for sk in ch.skills if sk.cdtime == 0]
        if not usable:
            return None

        # 根據計算的分數排序
        sorted_usable = sorted(
            usable, 
            key=lambda sk: self.score_skill(sk, ch, allies, enemies), 
            reverse=True
        )
        
        # 隨機性(取前兩高分的隨機一個，如果只有一個就選那個)
        candidates = sorted_usable[:2] if len(sorted_usable) > 1 else sorted_usable
        return random.choice(candidates)

    def choose_target(self, buff, team, enemies, actor=None):
        ch = actor or self.character
        living_team = [a for a in team if not a.is_dead()]
        living_enemies = [e for e in enemies if not e.is_dead()]

        # 1. 強制性目標 
        if buff.target == Target.SELF:
            return ch
        elif buff.target == Target.TEAM:
            return living_team # 群體技能回傳列表
        elif buff.target == Target.ENEMIES:
            return living_enemies # 群體攻擊回傳列表

        # 2. 選擇性目標 (單體)
        target_group = []
        default_rule = "RANDOM"

        if buff.target == Target.ALLY:
            target_group = living_team
            # 支援型 AI 的目標規則
            rule_key = self.profile.get("target_rule_ally", "LOW_HP") 
        
        elif buff.target == Target.ENEMY:
            target_group = living_enemies
            # 攻擊型 AI 的目標規則
            rule_key = self.profile.get("target_rule_enemy", self.profile.get("target_rule", "RANDOM"))

        if not target_group:
            return None

        # 3. 執行策略
        strategy_func = self.STRATEGIES.get(rule_key, self.STRATEGIES["RANDOM"])
        
        # 嘲諷 (Taunt) 優先處理
        if buff.target == Target.ENEMY:
            taunted_enemies = [e for e in living_enemies if self._has_effect(e, Effect.TAUNT)]
            if taunted_enemies:
                return random.choice(taunted_enemies)

        return strategy_func(target_group, ch)

    def _has_effect(self, ch, eff_enum) -> bool:
        for b in getattr(ch, "buffs", []):
            if getattr(b, "effect", None) == eff_enum and getattr(b, "duration", 0) != 0:
                return True
        return False