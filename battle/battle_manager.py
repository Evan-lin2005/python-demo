from battle.event_manager import event_manager, EventType
from battle.buff import Target, Phase
from battle.ai_controller import AIController
from battle.battle_log import BattleLog
import copy

class CLIController:
    def select_skill(self, actor):
        while True:
            actor.show_skills()
            try:
                idx = int(input("選擇技能編號: "))
                if 0 <= idx < len(actor.skills):
                    return idx
            except:
                pass

    def select_target(self, candidates, prompt="選擇目標"):
        living = [c for c in candidates if not c.is_dead()]
        while True:
            for i, c in enumerate(living):
                print(f"{i}. {c.name} HP={c.hp} SH={c.shield}")
            try:
                idx = int(input(prompt + ": "))
                if 0 <= idx < len(living):
                    return living[idx]
            except:
                pass

class BattleManager:
    def __init__(self, controller=None):
        self.controller = controller or CLIController()

    def battle(self, team_a, team_b):
        round_num = 1
        while self.alive(team_a) and self.alive(team_b):
            print(f"\n===== 第 {round_num} 回合 =====")

            # A隊行動
            for member in team_a:
                if not member.is_dead():
                    self.turn(member, team_a, team_b)
                    if not self.alive(team_b): break

            # B隊行動
            for member in team_b:
                if not member.is_dead():
                    self.turn(member, team_b, team_a)
                    if not self.alive(team_a): break

            round_num += 1

        # 判斷勝負
        if not self.alive(team_a) and not self.alive(team_b):
            print("⚔️ 雙方同歸於盡！")
        elif not self.alive(team_a):
            print("☠️ A隊全滅，B隊勝利！")
        else:
            print("☠️ B隊全滅，A隊勝利！")

    def turn(self, src, allies, enemies):
        print(f"\n--- {src.name} 的回合 ---")
        event_manager.emit(EventType.TURN_START, actor=src)
        src.trigger_phase(Phase.START)
        
        controller = getattr(src, "controller", self.controller)

        #接收 ctx，判斷是否被 cancel
        ctx = event_manager.emit(EventType.BEFORE_ACTION, actor=src)
        if getattr(ctx, "canceled", False):
            BattleLog.output_buff(src.name, "被控制狀態，無法行動", 0)
            # 回合結束
            event_manager.emit(EventType.TURN_END, actor=src)
            src.trigger_phase(Phase.END)
            src.buff_end_round()
            src.reduce_cd()
            return
            
        # === 1) 選技能 ===
        if isinstance(controller, AIController):
            skill = controller.choose_skill(actor=src)        # ★ 把 src 傳進去
            if not skill:
                print(f"{src.name} 沒有技能可用，跳過回合。")
                # 結束回合
                event_manager.emit(EventType.TURN_END, actor=src)
                src.trigger_phase(Phase.END)
                src.buff_end_round()
                src.reduce_cd()
                return
            skill_buffs = skill.be_used()
            print(f"{src.name} 使用技能【{skill.name}】")
        else:
            idx = controller.select_skill(src)
            skill_buffs = src.choose_skill(idx)

            # 若技能冷卻中，提示並重新選擇
            while skill_buffs == []:
                # GUI 模式：顯示提示訊息
                if hasattr(controller, "ui") and controller.ui:
                    controller.ui.call_on_ui(controller.ui.append_log, f"⚠️ {src.name} 的技能正在冷卻中，請重新選擇！")
                else:
                    print(f"⚠️ {src.name} 的技能正在冷卻中，請重新選擇！")

                idx = controller.select_skill(src)
                skill_buffs = src.choose_skill(idx)

            # 成功選定技能才繼續


        # === 2) 套用 Buff / 選目標 ===
        event_manager.emit(EventType.SKILL_CAST, actor=src, data={"buffs": skill_buffs})

        for buff in skill_buffs:
            # 取得目標
            if isinstance(controller, AIController):
                tgt = controller.choose_target(buff, allies, enemies, actor=src)  # ★ 把 src 傳進去
            else:
                if buff.target == Target.SELF:
                    tgt = src
                elif buff.target == Target.ALLY:
                    tgt = controller.select_target(allies, "選擇我方單位")
                elif buff.target == Target.ENEMY:
                    tgt = controller.select_target(enemies, "選擇敵人")
                elif buff.target == Target.TEAM:
                    tgt = allies
                elif buff.target == Target.ENEMIES:
                    tgt = enemies
                else:
                    tgt = None

            # 發動（支援單體 / 多體）
            if isinstance(tgt, list):
                for t in tgt:
                    if t and not t.is_dead():
                        t.receive_buff(src, copy.deepcopy(buff))
            elif tgt:
                if not getattr(tgt, "is_dead", lambda: False)():
                    tgt.receive_buff(src, copy.deepcopy(buff))

        event_manager.emit(EventType.SKILL_RESOLVE, actor=src, data={"buffs": skill_buffs})
        event_manager.emit(EventType.TURN_END, actor=src)

        # === 3) 回合收尾 ===
        src.trigger_phase(Phase.END)
        src.buff_end_round()
        src.reduce_cd()

    def choose_target(self, candidates):
        living = [c for c in candidates if not c.is_dead()]
        while True:
            for i, c in enumerate(living):
                print(f"{i}. {c.name} HP={c.hp}")
            idx = int(input("選擇目標: "))
            if idx < len(living) and idx >= 0 :
                return living[idx]

    def alive(self, team):
        return any(not c.is_dead() for c in team)



