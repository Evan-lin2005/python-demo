from battle.buff import Effect
from battle.battle_log import BattleLog,_out
from battle.event_manager import event_manager, EventType, EventContext

# =========================
# effect_registry.py (final)
# - 修正魔/物傷屬性計算
# - 統一傷害管線：命中 → BEFORE_ATTACK(加乘) → take_damage()
# - 無敵於 BEFORE_TAKE_DAMAGE，priority=1000
# - DOT 走完整事件管線（支援無敵/護盾）
# - 標記機制（MARK / CONSUME_MARK / PREP_WINDOW）
# - AFTER_TAKE_DAMAGE 順序：THORNS(100) → COUNTER(200) → LIFESTEAL(300)
# =========================

import random

# --- 暴擊判定（chance: 0~1） ---
def cri(chance: float) -> bool:
    chance = max(0.0, min(1.0, float(chance)))
    return random.random() < chance

# --- 命中/閃避 ---
def _roll_hit(src, tgt):
    ctx = event_manager.emit(
        EventType.BEFORE_ATTACK,
        actor=src,
        target=tgt,
        hit=getattr(src, "hit", 0.0),
        miss=getattr(tgt, "miss", 0.0),
    )
    hit_val  = max(0.0, min(1.0, float(getattr(ctx, "hit", 0.0))))
    miss_val = max(0.0, min(1.0, float(getattr(ctx, "miss", 0.0))))
    evade_chance = max(0.0, min(0.95, miss_val - hit_val))
    evaded = random.random() < evade_chance
    return (not evaded), 1.0 - evade_chance  # (命中?, 命中率)

# --- 輕量標記桶 ---
def _mark_bucket(obj):
    if not hasattr(obj, "_marks"):
        obj._marks = {}
    return obj._marks


class EffectRegistry:
    apply = {}
    remove = {}

    @staticmethod
    def init():
        # =============== 主動傷害（物理/魔法） ===============
        def _apply_damage_core(src, tgt, buff, atk_attr: str, def_attr: str):
            ok, _ = _roll_hit(src, tgt)
            if not ok:
                BattleLog.output_miss(src.name, tgt.name)
                event_manager.emit(EventType.AFTER_ATTACK, actor=src, target=tgt, dmg=0.0, miss=True)
                return

            # 1) 基礎傷（屬性正確）
            atk = max(0.0, float(getattr(src, atk_attr, 0.0)))
            deff = max(0.0, float(getattr(tgt, def_attr, 0.0)))
            base = max(0.0, atk * float(buff.percent) + float(buff.base) - deff)

            # 2) BEFORE_ATTACK：允許外部效果調整乘數/加成
            ctx = event_manager.emit(
                EventType.BEFORE_ATTACK,
                actor=src,
                target=tgt,
                data={"dmg_mult": 1.0, "dmg_add": 0.0, "tag": getattr(buff, "name", None)}
            )

            mult = float(getattr(ctx, "data", {}).get("dmg_mult", 1.0))
            add  = float(getattr(ctx, "data", {}).get("dmg_add", 0.0))
            dmg = max(0.0, base * mult + add)

            # 3) 暴擊（若有）
            if cri(getattr(src, "cri", 0.0)):
                dmg *= max(1.0, float(getattr(src, "cridmg", 1.5)))

            # 4) 走正式傷害管線（支援無敵/護盾/反擊）
            before = tgt.hp
            tgt.take_damage(dmg, attacker=src)
            delta = before - tgt.hp

            BattleLog.output_damage(src.name, tgt.name, delta)
            event_manager.emit(EventType.AFTER_ATTACK, actor=src, target=tgt, dmg=float(delta))

        # 物理傷害（patk vs pdef）
        def apply_physic(src, tgt, buff):
            _apply_damage_core(src, tgt, buff, atk_attr="patk", def_attr="pdef")

        EffectRegistry.apply[Effect.PHYSICDAMAGE]  = apply_physic
        EffectRegistry.remove[Effect.PHYSICDAMAGE] = lambda s, t, b: None

        # 魔法傷害（matk vs mdef）
        def apply_magic(src, tgt, buff):
            _apply_damage_core(src, tgt, buff, atk_attr="matk", def_attr="mdef")

        EffectRegistry.apply[Effect.MAGICDAMAGE]  = apply_magic
        EffectRegistry.remove[Effect.MAGICDAMAGE] = lambda s, t, b: None

        # =============== 直接生命加減（百分比或固定） ===============

        def apply_hp(src, tgt, buff):
            delta = float(tgt.max_hp) * float(buff.percent) + float(buff.base)
            before = tgt.hp
            tgt.add_hp(delta)
            BattleLog.output_buff(tgt.name, "血量", tgt.hp - before)

        EffectRegistry.apply[Effect.ADDHP]  = apply_hp
        EffectRegistry.remove[Effect.ADDHP] = lambda s, t, b: None

        # =============== 屬性增減（有移除時回復） ===============

        def _apply_stat(delta_fn_name, max_attr_name, label):
            def _apply(src, tgt, buff):
                add = float(getattr(tgt, max_attr_name)) * float(buff.percent) + float(buff.base)
                before = float(getattr(tgt, label[0]))
                getattr(tgt, delta_fn_name)(add)
                after = float(getattr(tgt, label[0]))
                d = after - before
                buff.applied.append(d)
                BattleLog.output_buff(tgt.name, label[1], d)
            def _remove(src, tgt, buff):
                for applied in buff.applied:
                    getattr(tgt, delta_fn_name)(-applied)
                buff.applied.clear()
            return _apply, _remove

        EffectRegistry.apply[Effect.ADDPATK], EffectRegistry.remove[Effect.ADDPATK] = _apply_stat("add_patk", "max_patk", ("patk", "物理攻擊力"))
        EffectRegistry.apply[Effect.ADDPDEF], EffectRegistry.remove[Effect.ADDPDEF] = _apply_stat("add_pdef", "max_pdef", ("pdef", "物理防禦力"))
        EffectRegistry.apply[Effect.ADDMATK], EffectRegistry.remove[Effect.ADDMATK] = _apply_stat("add_matk", "max_matk", ("matk", "魔法攻擊力"))
        EffectRegistry.apply[Effect.ADDMDEF], EffectRegistry.remove[Effect.ADDMDEF] = _apply_stat("add_mdef", "max_mdef", ("mdef", "魔法防禦力"))
        EffectRegistry.apply[Effect.ADDCRI],  EffectRegistry.remove[Effect.ADDCRI]  = _apply_stat("add_cri",  "max_cri",  ("cri",  "爆擊率"))
        EffectRegistry.apply[Effect.ADDCRIDMG], EffectRegistry.remove[Effect.ADDCRIDMG] = _apply_stat("add_cridmg", "max_cridmg", ("cridmg", "爆擊傷害"))
        EffectRegistry.apply[Effect.ADDHIT],  EffectRegistry.remove[Effect.ADDHIT]  = _apply_stat("add_hit",  "max_hit",  ("hit",  "命中率"))
        EffectRegistry.apply[Effect.ADDMISS], EffectRegistry.remove[Effect.ADDMISS] = _apply_stat("add_miss", "max_miss", ("miss", "閃避率"))

        # =============== 護盾（可疊加，移除時回退） ===============

        def apply_shield(src, tgt, buff):
            add = float(tgt.max_hp) * float(buff.percent) + float(buff.base)
            before = float(getattr(tgt, "shield", 0.0))
            tgt.add_shield(add)
            after = float(getattr(tgt, "shield", 0.0))
            d = after - before
            buff.applied.append(d)
            BattleLog.output_buff(tgt.name, "護盾", d)

        def remove_shield(src, tgt, buff):
            for applied in buff.applied:
                tgt.add_shield(-applied)
            buff.applied.clear()

        EffectRegistry.apply[Effect.ADDSHIELD]  = apply_shield
        EffectRegistry.remove[Effect.ADDSHIELD] = remove_shield

        # =============== DOT：走完整事件管線（支援無敵/護盾） ===============

        def apply_dot(src, tgt, buff):
            base = max(0.0, float(tgt.max_hp) * float(buff.percent) + float(buff.base))
            ctx = event_manager.emit(EventType.BEFORE_TAKE_DAMAGE, target=tgt, actor=src, dmg=base)
            dmg = max(0.0, float(getattr(ctx, "dmg", base)))
            if dmg <= 0.0:
                BattleLog.output_buff(tgt.name, f"{buff.name} 被免疫", 0)
                return
            before = tgt.hp
            tgt.take_damage(dmg, attacker=src)
            actual = before - tgt.hp
            BattleLog.output_dot(tgt.name, buff.name if getattr(buff, "name", "") else "持續傷害", actual)

        EffectRegistry.apply[Effect.DOT]  = apply_dot
        EffectRegistry.remove[Effect.DOT] = lambda s, t, b: None

        # =============== 無敵（最高優先，攔截實際傷害） ===============
        # battle/effect_registry.py 內（沿用現有 INVINCIBLE，加入「去重保護」）
        def apply_invincible(src, tgt, buff):
            # 若目標已經有相同 buff 物件，就不要重複掛（避免重複訂閱）
            for bb in getattr(tgt, "buffs", []):
                if bb is buff:   # 關鍵：用身分比較，不用 id
                    return
            def on_before_take_damage(ev, ctx, _t=tgt):
                if ctx.target is _t:
                    ctx.dmg = 0.0
                    BattleLog.output_buff(_t.name, "無敵", 0)
            event_manager.subscribe(EventType.BEFORE_TAKE_DAMAGE, on_before_take_damage,
                                    priority=1000, owner=buff)

        def remove_invincible(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.INVINCIBLE]  = apply_invincible
        EffectRegistry.remove[Effect.INVINCIBLE] = remove_invincible

        # =============== 反傷（在無敵之後、反擊之前） ===============

        def apply_thorns(src, tgt, buff):
            ratio = float(buff.percent)
            def on_after_take_damage(ev, ctx: EventContext, _t=tgt, _r=ratio):
                if ctx.target is _t and ctx.actor is not None and ctx.dmg > 0:
                    reflect = int(round(ctx.dmg * _r))
                    ctx.actor.take_damage(reflect, attacker=_t)
                    BattleLog.output_damage(_t.name, ctx.actor.name, reflect)
            event_manager.subscribe(
                EventType.AFTER_TAKE_DAMAGE, on_after_take_damage,
                priority=100, owner=buff
            )
        def remove_thorns(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.THORNS]  = apply_thorns
        EffectRegistry.remove[Effect.THORNS] = remove_thorns

        # =============== 反擊（固定在反傷之後） ===============

        def apply_counter(src, tgt, buff):
            ratio, base = float(buff.percent), float(buff.base)
            def on_after_take_damage(ev, ctx: EventContext, _t=tgt, _r=ratio, _base=base):
                if ctx.target is _t and ctx.dmg > 0 and ctx.actor is not None:
                    counter_dmg = max(0, int(round(ctx.dmg * _r + _base)))
                    before = ctx.actor.hp
                    ctx.actor.take_damage(counter_dmg, attacker=_t)
                    BattleLog.output_damage(_t.name, ctx.actor.name, before - ctx.actor.hp)
            event_manager.subscribe(
                EventType.AFTER_TAKE_DAMAGE, on_after_take_damage,
                priority=200, owner=buff
            )
        def remove_counter(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.COUNTER]  = apply_counter
        EffectRegistry.remove[Effect.COUNTER] = remove_counter

        # =============== 吸血（最後結算） ===============

        def apply_lifesteal(src, tgt, buff):
            ratio, base = float(buff.percent), float(buff.base)
            def on_after_take_damage(ev, ctx: EventContext, _s=src, _r=ratio, _base=base):
                if ctx.actor is _s and ctx.dmg > 0:
                    heal = max(0, int(round(ctx.dmg * _r + _base)))
                    before = _s.hp
                    _s.add_hp(heal)
                    BattleLog.output_buff(_s.name, "吸血回復", _s.hp - before)
            event_manager.subscribe(
                EventType.AFTER_TAKE_DAMAGE, on_after_take_damage,
                priority=300, owner=buff
            )
        def remove_lifesteal(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.LIFESTEAL]  = apply_lifesteal
        EffectRegistry.remove[Effect.LIFESTEAL] = remove_lifesteal

        # =============== 標記系統（MARK / CONSUME_MARK / PREP_WINDOW） ===============

        # MARK：在目標身上記層數
        def apply_mark(src, tgt, buff):
            marks = _mark_bucket(tgt)
            key = buff.name  #  對齊CONSUME_MARK 
            marks[key] = marks.get(key, 0) + 1

        EffectRegistry.apply[Effect.MARK]  = apply_mark
        EffectRegistry.remove[Effect.MARK] = lambda s, t, b: None

        # CONSUME_MARK：於 BEFORE_ATTACK 消耗印記，依 buff.percent / buff.base 作為每層增傷
        def apply_consume_mark(src, tgt, buff):
            def on_before_attack(ev, ctx: EventContext, _t=tgt, _b=buff):
                if ctx.target is not _t:
                    return

                # 只在真正的傷害前那次 BEFORE_ATTACK 才生效：
                data = getattr(ctx, "data", None)
                if not isinstance(data, dict) or ("dmg_mult" not in data and "dmg_add" not in data):
                    return

                marks = _mark_bucket(_t)
                key = getattr(_b, "mark_key", None) or getattr(_b, "desc", None) or _b.name
                stacks = int(marks.get(key, 0))
                if stacks <= 0:
                    return

                per_stack_mult = float(getattr(_b, "percent", 0.0))
                per_stack_add  = float(getattr(_b, "base", 0.0))

                data["dmg_mult"] = float(data.get("dmg_mult", 1.0)) * (1.0 + per_stack_mult * stacks)
                data["dmg_add"]  = float(data.get("dmg_add",  0.0)) + (per_stack_add * stacks)
                ctx.data = data

                marks[key] = 0  # 消耗所有層
                event_manager.unsubscribe_owner(_b)  # 僅影響這一擊
            event_manager.subscribe(EventType.BEFORE_ATTACK, on_before_attack, owner=buff, priority=250)

        def remove_consume_mark(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.CONSUME_MARK]  = apply_consume_mark
        EffectRegistry.remove[Effect.CONSUME_MARK] = remove_consume_mark

        # PREP_WINDOW：於 BEFORE_ATTACK 加乘（例如下一擊 +X%）
        def apply_prep_window(src, tgt, buff):
            def on_before_attack(ev, ctx: EventContext, _s=src, _b=buff):
                if ctx.actor is not _s:
                    return
                data = dict(ctx.data or {})
                data["dmg_mult"] = float(data.get("dmg_mult", 1.0)) * (1.0 + float(getattr(_b, "percent", 0.0)))
                ctx.data = data
            event_manager.subscribe(
                EventType.BEFORE_ATTACK, on_before_attack,
                owner=buff, priority=150  
            )

        def remove_prep_window(src, tgt, buff):
            event_manager.unsubscribe_owner(buff)

        EffectRegistry.apply[Effect.PREP_WINDOW]  = apply_prep_window
        EffectRegistry.remove[Effect.PREP_WINDOW] = remove_prep_window
        
        #嘲諷(使AI選敵人時優先選擇)
        def apply_taunt(src,tgt,buff):
            BattleLog.output_buff(tgt.name, "嘲諷", 0)

        def remove_taunt(sec,target,buff):
            pass

        EffectRegistry.apply[Effect.TAUNT] = apply_taunt
        EffectRegistry.remove[Effect.TAUNT] = remove_taunt
        
        def apply_stun(src, tgt, buff):
            charges = int(getattr(buff, "duration", 1) or 1)
            # 記在 buff.extra
            if not hasattr(buff, "extra") or not isinstance(buff.extra, dict):
                buff.extra = {}
            buff.extra["_stun_left"] = charges

            tgt.stun = max(0, getattr(tgt, "stun", 0)) + charges
            BattleLog.output_buff(tgt.name, f"陷入暈眩（{charges} 回合）", 0)

            def on_before_action(ev, ctx: EventContext, _t=tgt, _b=buff):
                if ctx.actor is not _t:
                    return
                left = int(_b.extra.get("_stun_left", 0))
                if left <= 0:
                    return

                ctx.cancel()
                BattleLog.output_buff(_t.name, "被暈眩，無法行動！", 0)
                _b.extra["_stun_left"] = left - 1
                _t.remove_stun()  # 角色計數 -1

                if _b.extra["_stun_left"] <= 0:
                    event_manager.unsubscribe_owner(_b)
                    try:
                        _t.remove_buff_by_id(_b.id)
                    except Exception:
                        _b.duration = 0

            event_manager.subscribe(EventType.BEFORE_ACTION, on_before_action,
                                    priority=1000, owner=buff)

        def remove_stun(src, tgt, buff):
            # 被驅散時，把「尚未消耗」的次數從角色身上扣回來
            left = 0
            if hasattr(buff, "extra") and isinstance(buff.extra, dict):
                left = int(buff.extra.get("_stun_left", 0))
                buff.extra["_stun_left"] = 0
            if left > 0:
                tgt.stun = max(0, getattr(tgt, "stun", 0) - left)
            event_manager.unsubscribe_owner(buff)



        EffectRegistry.apply[Effect.STUN]  = apply_stun
        EffectRegistry.remove[Effect.STUN] = remove_stun