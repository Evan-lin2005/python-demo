import json, os
from character.character import Character
from battle.skill_library import SkillLibrary
from character.jobs_library import JobLibrary

SAVE_DIR  = "save"
SAVE_FILE = os.path.join(SAVE_DIR, "player_data.json")

class SaveManager:
    @staticmethod
    def save_game(chars, story_node_id=None):
        """存檔角色與劇情進度"""
        os.makedirs(SAVE_DIR, exist_ok=True)

        data = {
            "story_node": story_node_id,
            "characters": []
        }

        for c in chars:
            data["characters"].append({
                "name": c.name,
                "job": c.job,
                # 新增 level / exp 兩個欄位
                "level": int(c.lv),
                "exp":   int(c.exp),
                # 原有屬性照存
                "hp": c.hp, "max_hp": c.max_hp,
                "patk": c.patk, "pdef": c.pdef,
                "matk": c.matk, "mdef": c.mdef,
                "shield": getattr(c, "shield", 0),
                "skills": [
                    {
                        "name": sk.name,
                        "currLevel": sk.currLevel,
                        "cd": sk.cd,
                        "cdtime": getattr(sk, "cdtime", 0)
                    } for sk in getattr(c, "skills", [])
                ]
            })
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 存檔完成 → {SAVE_FILE}")

    @staticmethod
    def load_game():
        """讀取角色與劇情進度"""
        if not os.path.exists(SAVE_FILE):
            print("⚠️ 找不到存檔，建立新資料")
            return None, None

        JobLibrary.init("jobs.json")
        SkillLibrary.init("skills.json")

        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        chars_data = data.get("characters", [])
        story_node = data.get("story_node", None)

        chars = []
        for d in chars_data:
            ch = Character(d["name"], job=d["job"])

            # 正確還原等級與經驗（注意欄位名與型態）
            lv  = int(d.get("level", 1))
            exp = int(d.get("exp",   0))
            ch.set_lv(lv)
            ch.exp = exp

            # 以存檔為準覆寫屬性
            ch.max_hp  = d.get("max_hp", ch.max_hp); ch.hp   = d.get("hp",   ch.max_hp)
            ch.max_patk= d.get("patk",  ch.max_patk); ch.patk= ch.max_patk
            ch.max_pdef= d.get("pdef",  ch.max_pdef); ch.pdef= ch.max_pdef
            ch.max_matk= d.get("matk",  ch.max_matk); ch.matk= ch.max_matk
            ch.max_mdef= d.get("mdef",  ch.max_mdef); ch.mdef= ch.max_mdef
            ch.shield  = d.get("shield", getattr(ch, "shield", 0))

            # 還原技能狀態
            for sk, info in zip(ch.skills, d.get("skills", [])):
                sk.currLevel = int(info.get("currLevel", sk.currLevel))
                sk.cd        = int(info.get("cd",        sk.cd))
                sk.cdtime    = int(info.get("cdtime",    0))
            chars.append(ch)
        print(f"✅ 成功載入存檔，劇情節點：{story_node}")
        return chars, story_node

    @staticmethod
    def update_story_node(node_id):
        """更新劇情節點"""
        if not os.path.exists(SAVE_FILE):
            print("⚠️ 無存檔可更新，忽略")
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["story_node"] = node_id
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"📝 劇情節點更新 → {node_id}")
        except Exception as e:
            print("❌ 更新劇情節點失敗：", e)
