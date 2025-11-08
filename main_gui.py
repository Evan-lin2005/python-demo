# main_gui.py
from ui.gui import *
from story.story_manager import StoryManager
from story.ui_adapter import StoryUIAdapter
from battle.ai_controller import AIController
from battle.team_factory import TeamFactory
from battle.ui_sync import HealthBarSync
from save.save_manager import SaveManager
from battle.event_manager import event_manager, EventType


def main():
    TeamFactory.init()
    # ===== 1) 載入存檔 =====
    saved_chars, saved_node = SaveManager.load_game()

    # ===== 2) 載入敵方目錄 =====
    TeamFactory.load_enemy_data()  # 會從 story/enemies.json 讀章節/節點 → 敵人清單

    # ===== 3) 建立我方隊伍=====
    allies = saved_chars if saved_chars else TeamFactory.default_allies()


    enemies = []

    # ===== 4) 戰鬥控制器 =====
    player_controller = GUIController()
    enemy_ai = AIController()
    bm = BattleManager(controller=player_controller)

    for ch in allies:
        ch.controller = player_controller
    for ch in enemies:
        ch.controller = enemy_ai

    # ===== 5) UI 與劇情層 =====
    ui = BattleUI(allies, enemies, player_controller)
    ui.adapter = StoryUIAdapter(ui)

    def build_for_node(node, node_id=None):
        teamA, teamB = TeamFactory.build_for_node(node, node_id or "", allies_instances=allies)

        # 綁 控制器
        for e in teamB:
            e.controller = enemy_ai

        #  UI 重建敵方面板
        ui.call_on_ui(ui.set_enemies, teamB)

        #  血條同步器綁定新敵人
        if hasattr(ui, "_hp_sync"):
            ui._hp_sync.characters = teamA + teamB

        return teamA, teamB

    sm = StoryManager(ui, bm, build_for_node)
    sm.enemy_ai = enemy_ai  # ★  AI 實例塞給 SM
    sm.load("story/story.json")

    # ===== 6) 自動更新劇情節點到存檔 =====
    orig_goto = sm.goto
    def goto_with_save(node_id):
        try:
            SaveManager.update_story_node(node_id)
        except Exception:
            pass
        orig_goto(node_id)
    sm.goto = goto_with_save

    # ===== 7) 起始：從存檔節點續玩或從頭開始 =====
    if saved_node:
        print(f"📖 從節點 {saved_node} 繼續劇情")
        sm.goto(saved_node)
    else:
        sm.begin()

    # ===== 8) UI 同步：血條與護盾 =====
    ui._hp_sync = HealthBarSync(ui, allies + enemies)

    # ===== 9) 自動存檔機制=====
    def auto_save(ev, ctx):
        SaveManager.save_game(allies, story_node_id=getattr(sm, "curr", None))
        ui.call_on_ui(ui.append_log, "💾 自動存檔完成")
    event_manager.subscribe(EventType.TURN_END, auto_save, priority=-999, owner="AUTO_SAVE")

    # ===== 10) 啟動 Tk 主迴圈 =====
    ui.mainloop()


if __name__ == "__main__":
    main()

