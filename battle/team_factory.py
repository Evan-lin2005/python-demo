# battle/team_factory.py
import json, os
from typing import List, Optional, Dict, Any
from battle.effect_registry import EffectRegistry
from battle.skill_library import SkillLibrary
from character.jobs_library import JobLibrary
from character.character import Character

class TeamFactory:
    _enemy_config: Dict[str, Dict[str, list]] = {}
    _enemy_builders: Dict[str, callable] = {}  

    @staticmethod
    def init():
        EffectRegistry.init()
        SkillLibrary.init("skills.json")
        JobLibrary.init("jobs.json")

    @staticmethod
    def load_enemy_data(path="story/enemies.json"):
        base_dir = os.path.dirname(__file__)
        abs_path = os.path.normpath(os.path.join(base_dir, "..", path))
        if not os.path.exists(abs_path):
            print(f"⚠️ 找不到敵人設定檔：{abs_path}")
            TeamFactory._enemy_config = {}
            return
        with open(abs_path, "r", encoding="utf-8") as f:
            TeamFactory._enemy_config = json.load(f)
        print("✅ 已載入敵人資料")

    # --- 我方預設 ---
    @staticmethod
    def default_allies():
        TeamFactory.init()
        return [
            Character("勇者", job="Warrior"),
            Character("狂戰士", job="Berserker"),
            Character("補師", job="Cleric"),
            Character("弓箭手", job="Archer"),
        ]

    # --- 以 story 節點）決定敵方 ---
    @staticmethod
    def enemies_from_catalog(node: Dict[str, Any], node_id: str) -> List[Character]:
        """
        從 story/enemies.json 依 chapter + node_id 取敵人：
        """
        TeamFactory.init()
        if not TeamFactory._enemy_config:
            TeamFactory.load_enemy_data() 
            
        chapter = None
        try:
            chapter = node.get("chapter")
            if chapter is None:
                raise ValueError("node.chapter is None")
        except Exception as err:
            print("Not successful load Node:", err)
            raise
            
        bucket = TeamFactory._enemy_config.get(chapter, {})
        arr = bucket.get(node_id, [])
        if arr:
            result = []
            for e in arr:
                ch = Character(e["name"], job=e["job"])
                ch.set_lv(e.get("level", 1))  # 若沒給 level 預設 1
                result.append(ch)
            return result
        return []

    # --- build 註冊表 ---
    @staticmethod
    def register(build_id: str, fn):
        TeamFactory._enemy_builders[build_id] = fn

    @staticmethod
    def enemies_by_build(build_id: Optional[str]) -> List[Character]:
        TeamFactory.init()
        fn = TeamFactory._enemy_builders.get(build_id or "_default")
        if fn:
            return fn()
        print(f"⚠️ 未定義 build={build_id}，使用訓練假人")
        return [Character("訓練假人", job="Warrior")]

    # --- 入口：以 story 節點 決定 allies, enemies ---
    @staticmethod
    def build_for_node(node: Dict[str, Any], node_id: str, allies_instances: Optional[List[Character]] = None):
        allies = allies_instances or TeamFactory.default_allies()
        enemies = TeamFactory.enemies_from_catalog(node, node_id)
        if not enemies:
            enemies = TeamFactory.enemies_by_build(node.get("build"))
        return allies, enemies
