# ============================================
# test.py — 多職業自動對戰（輸出過程 + 個人統計）
# 不依賴 BattleManager.use_skill()，直接走現有角色/效果機制
# ============================================
import os
import copy
from collections import defaultdict

from battle.battle_log import BattleLog, set_log_sink
from battle.effect_registry import EffectRegistry
from battle.skill_library import SkillLibrary
from character.jobs_library import JobLibrary
from character.character import Character
from battle.ai_controller import AIController
from battle.event_manager import event_manager, EventType, EventContext
from battle.buff import Phase, Target

# -----------------------------
# 檔案輸出設定
# -----------------------------
LOG_DIR = "logs"
PROCESS_LOG = os.path.join(LOG_DIR, "battle_process.txt")  # 戰鬥過程
STATS_LOG = os.path.join(LOG_DIR, "battle_stats.txt")      # 個人統計（輸出/承傷/回血）


def init_all():
    os.makedirs(LOG_DIR, exist_ok=True)
    open(PROCESS_LOG, "w", encoding="utf-8").close()
    open(STATS_LOG, "w", encoding="utf-8").close()

    SkillLibrary.init("skills.json")
    JobLibrary.init("jobs.json")
    EffectRegistry.init()

    # 將 BattleLog 的輸出導向「過程檔」
    def write_line(msg: str):
        with open(PROCESS_LOG, "a", encoding="utf-8") as f:
            f.write((msg or "").rstrip("\n") + "\n")

    set_log_sink(write_line)
    print(f"[Log] 戰鬥過程輸出：{PROCESS_LOG}")
    print(f"[Log] 個人統計輸出：{STATS_LOG}")
    return write_line


# -----------------------------
# 外部判斷（不修改核心）
# -----------------------------
def team_dead(team):
    return all(ch.is_dead() for ch in team)

def battle_over(teamA, teamB):
    return team_dead(teamA) or team_dead(teamB)

def winner_label(teamA, teamB):
    if team_dead(teamA) and team_dead(teamB):
        return "平手"
    if team_dead(teamB):
        return "隊伍A"
    if team_dead(teamA):
        return "隊伍B"
    return "未結束"


# -----------------------------
# 組隊（多職業）
# -----------------------------
def build_teams():
    teamA = [
        Character("勇者", job="Warrior"),
        Character("狂戰士", job="Berserker"),
        Character("補師", job="Cleric"),
        Character("刺客", job="Assassin"),
    ]
    teamB = [
        Character("邪惡黑法師", job="Elementalist"),
        Character("聖騎士", job="Paladin"),
        Character("血魔祭司", job="BloodMage"),
        Character("吟遊詩人", job="Bard"),
    ]
    return teamA, teamB


# -----------------------------
# 小工具：施放技能（不依賴 BattleManager.use_skill）
# -----------------------------
def cast_skill(actor, allies, enemies, ai, write_line):
    """用現有 AI 選技/選目標，利用 Character.receive_buff 套用技能"""
    # 選技能
    skill = ai.choose_skill(actor)
    if not skill:
        return False

    # 事件：準備施放（可讓其他系統監聽）
    event_manager.emit(EventType.BEFORE_ACTION, actor=actor, data={"skill": skill})

    # 對每個 Buff 依目標型態選目標並套用
    for buff in skill.be_used():  # 設置冷卻並取得 buff 列表
        # 交給 AI 選目標（你的 AI 會依 buff.target 判斷 SELF/ALLY/ENEMY/ENEMIES/TEAM）
        target = ai.choose_target(buff, allies, enemies, actor)

        def _apply_to(target_char, the_buff):
            # 深拷貝 Buff，避免共用實例污染
            b = copy.deepcopy(the_buff)
            write_line(f"[行動] {actor.name} 使用 {skill.name} → {target_char.name}（{b.name}）")
            target_char.receive_buff(actor, b)

        if target is None:
            continue
        if isinstance(target, list):
            for t in target:
                _apply_to(t, buff)
        else:
            _apply_to(target, buff)

    # 事件：施放完成
    event_manager.emit(EventType.SKILL_CAST, actor=actor, data={"skill": skill})
    return True


# -----------------------------
# 對戰主流程 + 個人統計
# -----------------------------
def run_battle(write_line):
    teamA, teamB = build_teams()

    # 個人統計：輸出(造成傷害)/承傷(受到傷害)/回血(實際加回)
    stats = defaultdict(lambda: {"dealt": 0, "taken": 0, "healed": 0})

    # 監聽最終傷害（含無敵/護盾後的實傷）
    def on_after_take_damage(ev, ctx: EventContext):
        dmg = int(round(float(getattr(ctx, "dmg", 0) or 0)))
        if dmg <= 0:
            return
        attacker = getattr(ctx, "actor", None)
        target = getattr(ctx, "target", None)
        if attacker is not None:
            stats[attacker.name]["dealt"] += dmg
        if target is not None:
            stats[target.name]["taken"] += dmg

    event_manager.subscribe(EventType.AFTER_TAKE_DAMAGE, on_after_take_damage,
                            priority=200, owner="TEST_STATS_DAMAGE")

    # 包裝 add_hp 以計算「實際回血」
    def instrument_heal(char):
        orig = char.add_hp
        def wrapped(delta):
            before = char.hp
            ret = orig(delta)
            gain = int(round(char.hp - before))
            if gain > 0:
                stats[char.name]["healed"] += gain
            return ret
        char.add_hp = wrapped
    for ch in teamA + teamB:
        instrument_heal(ch)

    # 掛上 AI
    ai = AIController()
    for ch in teamA + teamB:
        ch.controller = ai

    # 回合制主循環
    round_count = 0
    MAX_ROUND = 100
    while not battle_over(teamA, teamB) and round_count < MAX_ROUND:
        round_count += 1
        write_line(f"\n===== 第 {round_count} 回合 =====")
        # 簡單行動序：依建立順序輪流（存活者才行動）
        turn_order = [c for c in (teamA + teamB) if not c.is_dead()]

        for actor in turn_order:
            if actor.is_dead() or battle_over(teamA, teamB):
                continue

            allies = teamA if actor in teamA else teamB
            enemies = teamB if actor in teamA else teamA

            # 回合開始
            event_manager.emit(EventType.TURN_START, actor=actor)
            actor.trigger_phase(Phase.START)

            # 施放技能
            acted = cast_skill(actor, allies, enemies, ai, write_line)

            # 回合結束（角色自己的 END 階段）
            actor.trigger_phase(Phase.END)
            event_manager.emit(EventType.TURN_END, actor=actor)

            # 技能冷卻 -1
            actor.reduce_cd()

        # 回合末：全體處理「APPLY 長效類」的倒數（避免在 START 重複套用）
        for ch in teamA + teamB:
            if not ch.is_dead():
                # Character.buff_end_round 內會只做倒數與過期移除（不重複套用）
                if hasattr(ch, "buff_end_round"):
                    ch.buff_end_round()

    # 結束
    result = winner_label(teamA, teamB)
    write_line(f"\n===== 戰鬥結束！勝利方：{result} =====\n")

    # 解除事件監聽
    event_manager.unsubscribe_owner("TEST_STATS_DAMAGE")

    # 輸出統計檔
    with open(STATS_LOG, "a", encoding="utf-8") as f:
        f.write("=== 個人統計（總輸出 / 承傷 / 回血）===\n")
        def dump_team(title, team):
            f.write(f"\n[{title}]\n")
            team_total = {"dealt": 0, "taken": 0, "healed": 0}
            for ch in team:
                s = stats[ch.name]
                team_total["dealt"]  += s["dealt"]
                team_total["taken"]  += s["taken"]
                team_total["healed"] += s["healed"]
                f.write(f"{ch.name: <10}  輸出: {s['dealt']:>6}   承傷: {s['taken']:>6}   回血: {s['healed']:>6}\n")
            f.write(f"—— 小計 ——  輸出: {team_total['dealt']:>6}   承傷: {team_total['taken']:>6}   回血: {team_total['healed']:>6}\n")
        dump_team("隊伍A", teamA)
        dump_team("隊伍B", teamB)

    return result


def main():
    write_line = init_all()
    res = run_battle(write_line)
    print(f"[Result] 戰鬥結束！勝利方：{res}")
    print(f"[Log] 戰鬥過程：{PROCESS_LOG}")
    print(f"[Log] 個人統計：{STATS_LOG}")


if __name__ == "__main__":
    main()
