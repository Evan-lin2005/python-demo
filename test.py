# test_job_vs_job.py
import json
from collections import defaultdict
from character.jobs_library import JobLibrary
from character.character import Character
from battle.team_factory import TeamFactory
from battle.battle_manager import BattleManager
from battle.effect_registry import EffectRegistry
from battle.ai_controller import AIController
from battle.event_manager import event_manager, EventType, EventContext

# ============================================================
# 角色貢獻統計
# ============================================================
class Contribution:
    def __init__(self, c: Character):
        self.name = c.name
        self.job = c.job
        self.damage_given = 0
        self.damage_taken = 0
        self.heal_done = 0
        self.buff_count = 0

# ============================================================
# 事件監聽器：收集貢獻資料
# ============================================================
class RecordHooks:
    def __init__(self, contributions: dict):
        self.map = contributions

    def get(self, ch):
        if ch not in self.map:
            self.map[ch] = Contribution(ch)
        return self.map[ch]

    # --- 傷害 ---
    def after_attack(self, ev, ctx: EventContext):
        dmg = max(0, int(ctx.dmg))
        if ctx.actor:
            self.get(ctx.actor).damage_given += dmg
        if ctx.target:
            self.get(ctx.target).damage_taken += dmg

    # --- 補血（ADDHP） ---
    def heal_event(self, ev, ctx: EventContext):
        heal_val = int(ctx.data.get("heal", 0))
        if ctx.actor and heal_val > 0:
            self.get(ctx.actor).heal_done += heal_val

    # --- Buff 次數 ---
    def apply_buff(self, ev, ctx: EventContext):
        if ctx.actor:
            self.get(ctx.actor).buff_count += 1
    def skill_resolve(self, ev, ctx: EventContext):
        buffs = ctx.data.get("buffs", [])
        actor = ctx.actor
        if not actor:
            return

        for buff in buffs:
            if buff.effect.name == "ADDHP":
                # 計算治療量（依技能 JSON 規格）
                heal = actor.max_hp * buff.percent + buff.base
                self.get(actor).heal_done += heal

# ============================================================
# 單場 4v4 對戰
# ============================================================
def fight_4v4(job_a: str, job_b: str, battle_id: int):
    TeamFactory.init()
    EffectRegistry.init()
    JobLibrary.init("jobs.json")

    # 建立 4 名同職業角色
    team_a = [Character(f"{job_a}{i}", job_a) for i in range(4)]
    team_b = [Character(f"{job_b}{i}", job_b) for i in range(4)]

    ai_a = AIController(feature=None)
    ai_b = AIController(feature=None)

    for c in team_a:
        c.controller = ai_a
    for c in team_b:
        c.controller = ai_b

    # 收集貢獻
    contrib_map = {}

    recorder = RecordHooks(contrib_map)
    event_manager.subscribe(EventType.AFTER_ATTACK, recorder.after_attack, owner=battle_id)
    event_manager.subscribe(EventType.APPLY_BUFF, recorder.apply_buff, owner=battle_id)
    event_manager.subscribe(EventType.SKILL_RESOLVE, recorder.skill_resolve, owner=battle_id)


    # 執行戰鬥
    bm = BattleManager(controller=ai_a)
    bm.battle(team_a, team_b)

    # 誰贏？
    a_alive = any(not c.is_dead() for c in team_a)
    b_alive = any(not c.is_dead() for c in team_b)

    event_manager.unsubscribe_owner(battle_id)
    return contrib_map, a_alive, b_alive

# ============================================================
# N 場對戰統計
# ============================================================
def simulate(job_a: str, job_b: str, rounds=30):
    print(f"▶ {job_a} vs {job_b} 測試中... ({rounds} 場)")
    total = defaultdict(lambda: defaultdict(float))
    win_a = 0
    win_b = 0

    for r in range(1, rounds + 1):
        contrib, a_win, b_win = fight_4v4(job_a, job_b, battle_id=r)

        if a_win and not b_win:
            win_a += 1
        elif b_win and not a_win:
            win_b += 1

        # 累積貢獻
        for ch, co in contrib.items():
            total[co.job]["damage_given"] += co.damage_given
            total[co.job]["damage_taken"] += co.damage_taken
            total[co.job]["heal_done"] += co.heal_done
            total[co.job]["buff_count"] += co.buff_count

    # 平均化
    avg = {job: {key: val / rounds for key, val in data.items()} for job, data in total.items()}

    return {
        "jobs": [job_a, job_b],
        "winrate": {
            job_a: win_a / rounds,
            job_b: win_b / rounds,
        },
        "average_contribution": avg
    }

# ============================================================
# 主程式：全部職業對全部職業
# ============================================================
if __name__ == "__main__":
    JobLibrary.init("jobs.json")

    jobs = list(JobLibrary.jobs.keys())
    rounds = 3  # 每組對戰場數，可調高

    all_results = []

    for i in range(len(jobs)):
        for j in range(i + 1, len(jobs)):
            job_a = jobs[i]
            job_b = jobs[j]

            result = simulate(job_a, job_b, rounds=rounds)
            all_results.append(result)

            print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n=== 全職業對戰測試完成 ===")
