import json
import os
import copy
from battle.skill import Skill
from battle.buff import Buff, Target, Phase, Effect

class SkillLibrary:
    skills = {}

    @staticmethod
    def init(json_file="battle/skills.json"):
        # 取得當前檔案所在目錄 (battle)
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, json_file)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        SkillLibrary.skills = {}
        for name, info in data.items():
            buffs = [] # <--- Buff 列表
            
            # 1. 先收集所有 Buff
            for b in info["buffs"]:
                buff = Buff(
                    target=Target[b["target"]],
                    phase=Phase[b["phase"]],
                    name=b["name"],
                    desc=b["desc"],
                    duration=b["duration"],
                    effect=Effect[b["effect"]],
                    percent=b["percent"],
                    base=b["base"]
                )
                buff.mark_key = b.get("mark_key")
                buffs.append(buff) # <--- 加入列表
            
            # 2.在 Buff 迴圈結束後，才建立 Skill 物件
            skill = Skill(
                name=name,
                desc=info["desc"],
                cd=info["cd"],
                cost=info["cost"],
                buffs=buffs, # <--- 傳入完整的列表
                # 如果 buffs 為空，保護
                target=buffs[0].target if buffs else Target.ENEMY, 
                growth=info.get("growth", {})
            )

            SkillLibrary.skills[name] = skill

    @staticmethod
    def get(name):
        return copy.deepcopy(SkillLibrary.skills.get(name))
