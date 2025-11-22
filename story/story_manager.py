# story/story_manager.py
import json, threading, traceback
from battle.event_manager import event_manager, EventType
from battle.battle_log import set_log_sink

class StoryManager:
    def __init__(self, ui, battle_manager, build_teams_fn):
        """
        ui: BattleUI 
        battle_manager: BattleManager
        build_teams_fn: 隊伍建構器
        """
        self.ui = ui
        self.bm = battle_manager
        self.build_teams = build_teams_fn
        self.nodes = {}
        self.curr = None
        self.on_battle_end_next = None
        self._battle_thread = None
        self.teams = []
        # 讓戰鬥與劇情輸出都寫到 UI Log
        set_log_sink(lambda msg: self.ui.call_on_ui(self.ui.append_log, msg))

    def load(self, path="story/story.json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.nodes = data["nodes"]
        self.start_id = data["start"]

    def begin(self):
        self.goto(self.start_id)

    def goto(self, node_id):
        self.curr = node_id
        node = self.nodes.get(node_id)
        if not node: return "Not Find the Node ID"
        t = node.get("type")
        if t == "dialog":
            self._play_dialog(node)
        elif t == "battle":
            self._start_battle_node(node)

    # ===== 節點型別：Dialog =====
    def _play_dialog(self, node):
        lines = node.get("lines", [])
        choices = node.get("choices")
        next_id = node.get("next")

        def on_done():
            if next_id:
                self.goto(next_id)

        if choices:
            # 分支
            self.ui.adapter.show_dialogue(
                lines=lines,
                choices=[c["text"] for c in choices],
                on_choice=lambda idx: self.goto(choices[idx]["goto"])
            )
        else:
            # 台詞
            self.ui.adapter.show_dialogue(lines=lines, on_done=on_done)
            
    def _start_battle_node(self, node):
        self.ui.call_on_ui(getattr(self.ui.adapter, "close", lambda: None))

        on_win  = node.get("on_win")
        on_lose = node.get("on_lose")
        node_id = self.curr

        try:
            allies, enemies = self.build_teams(node, node_id)
        except TypeError:
            allies, enemies = self.build_teams(node, node_id)  # 容錯
        self.teams = allies
        self.on_battle_end_next = (on_win, on_lose)
        self._battle_exiting = False

        # 關掉舊的 HealthBarSync
        if hasattr(self.ui, "_hp_sync") and self.ui._hp_sync:
            try: self.ui._hp_sync.dispose()
            except: pass
            self.ui._hp_sync = None

        # UI 上重建隊伍
        self.ui.call_on_ui(self.ui.reset_teams, allies, enemies)

        # UI 上重建隊伍
        self.ui.call_on_ui(self.ui.reset_teams, allies, enemies)

        # 分配控制器
        for ch in allies:
            ch.controller = getattr(self.ui, "controller", None) or self.bm.controller
            
        # --- ✨ 修改：動態建立 AI 控制器 ---
        
        # 1. 導入 AIController 和 Feature Enum
        # (我們假設 ai_controller.py 在 battle/ 目錄下，且 Feature 在那裡定義)
        try:
            from battle.ai_controller import AIController, Feature
        except ImportError:
            print("❌ 無法導入 AIController 或 Feature！")
            from battle.ai_controller import AIController
            Feature = None # 設置一個預設值

        # 2. 為本場戰鬥建立一個列表，儲存所有 AI 實例，以便稍後清理
        self._current_enemy_controllers = []

        for ch in enemies:
            feature_str = getattr(ch, "ai_feature_str", "DPS").upper()

            feature_enum = None
            if Feature:
                try:
                    feature_enum = Feature[feature_str]
                except KeyError:
                    print(f"⚠️ 未知的 AI Feature '{feature_str}' (來自 {ch.name})，將使用預設 AI。")
                    feature_enum = Feature.DPS # 預設為 DPS
            
            # 5. 建立一個 *新的* AIController 實例並傳入 feature
            ai_instance = AIController(feature=feature_enum)
            ch.controller = ai_instance
            
            # 6. 將此實例儲存起來以便清理
            self._current_enemy_controllers.append(ai_instance)
            
        def _finish(next_id):
            if self._battle_exiting: return
            self._battle_exiting = True
            
            # --- 清理所有 AI 實例的訂閱 ---
            for ai in getattr(self, "_current_enemy_controllers", []):
                event_manager.unsubscribe_owner(ai)
            self._current_enemy_controllers = []
            
            #丟回 UI 執行緒
            if next_id:
                self.ui.call_on_ui(self.goto, next_id)
                
        def run_battle():
            try:
                self.bm.battle(allies, enemies)
            except Exception:
                err = traceback.format_exc()
                self.ui.call_on_ui(self.ui.append_log, "[Battle thread error]\n" + err)
            finally:
                a_alive = any(not c.is_dead() for c in allies)
                e_alive = any(not c.is_dead() for c in enemies)
                win = a_alive and not e_alive                    
                next_id = on_win if win else on_lose

                self.award_after_battle(allies, enemies, node, win)

                _finish(next_id)
                self._battle_thread = None


        # 若舊戰鬥 thread 還在，改用輪詢，
        def _poll_and_start():
            if getattr(self, "_battle_thread", None) and self._battle_thread.is_alive():
                self.ui.call_on_ui(self.ui.append_log, "等待上一場戰鬥釋放資源…")
                self.ui.after(50, _poll_and_start)
            else:
                self._battle_thread = threading.Thread(target=run_battle, daemon=True)
                self._battle_thread.start()

        _poll_and_start()


    def bind_triggers(self):
        def on_after_take_damage(ev, ctx):
            tgt = getattr(ctx, "target", None)
            if not tgt: return
            try:
                ratio = tgt.hp / max(1, tgt.max_hp)
                if ratio <= 0.30 and not getattr(tgt, "_lowhp_cutin", False):
                    tgt._lowhp_cutin = True
            except Exception:
                pass
        event_manager.subscribe(EventType.AFTER_TAKE_DAMAGE, on_after_take_damage, priority=10, owner=self)
    #戰鬥回報
    def _reward_after_battle(self, allies, enemies, node):
        reward_cfg = node.get("reward") or {}
        exp = int(reward_cfg.get("exp", 0))           
        if exp <= 0:
            total_lv = sum(getattr(e, "lv", 1) for e in enemies)
            exp = max(10, total_lv * 50)
        return {"exp": exp}

    
    def award_after_battle(self, allies, enemies, node, win: bool):
        if not win:
            return

        reward = self._reward_after_battle(allies, enemies, node) 
        exp_total = int(reward["exp"])
        exp_each = max(1, exp_total // max(1, len(allies)))         

        for ch in allies:
            before_lv = ch.lv
            ch.obtained_exp(exp_each)
            after_lv = ch.lv
            self.ui.call_on_ui(self.ui.append_log,
                            f"🎉 {ch.name} 獲得 {exp_each} EXP（Lv.{before_lv} → Lv.{after_lv}）")
        from save.save_manager import SaveManager
        SaveManager.save_game(allies, story_node_id=self.curr)
        self.ui.call_on_ui(self.ui.append_log, "💾 獎勵已儲存至存檔")

