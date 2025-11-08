from battle.effect_registry import EffectRegistry
from battle import buff as Buff
from battle.event_manager import event_manager, EventType, EventContext
basichp = 100
basicpatk = 10
basicpdef = 6
basicmatk = 8
basicmdef = 3
basicvit = 100
basiccri = 5.0
basiccridmg = 1.5
basicmiss = 0.05
basichit = 0.05
basicshield = 0

class Character():
    def __init__(self,name,job,hp = basichp,patk = basicpatk ,pdef = basicpdef,matk = basicmatk,mdef = basicmdef):
        from character.jobs_library import JobLibrary
        from battle.skill_library import SkillLibrary
        self.lv = 1
        self.exp = 0
        self.name = name
        self.job = job
        job_data = JobLibrary.get(job)
        self.stats = stats = job_data["stats"] #職業之數值加成
        self.max_hp = self.hp = hp * stats["hp"]
        self.max_patk = self.patk = patk * stats["patk"]
        self.max_pdef = self.pdef = pdef * stats["pdef"]
        self.max_matk = self.matk = matk * stats["matk"]
        self.max_mdef = self.mdef = mdef *stats["mdef"]
        self.max_vit = self.vit = basicvit
        self.max_cri = self.cri = 0.1 * stats["cri"]
        self.max_cridmg = self.cridmg = basiccridmg
        self.max_miss = self.miss = 0.05 * stats["miss"]
        self.max_hit  = self.hit = basichit
        self.shield = basicshield
        self.buffs = []
        self.skills = []
        self.skip_turn = False
        self.stun = 0
        self._job_growth = job_data.get("growth", {})
        for skill_name in job_data["skills"]:
            skill = SkillLibrary.get(skill_name)
            if skill:
                self.skills.append(skill)

        print(f"{self.name} ({self.job}) 已建立，技能：{[s.name for s in self.skills]}")

        
    def is_dead(self) ->bool :
        return self.hp <= 0
    
    def take_damage(self, dmg, attacker=None):
        # 允許事件修改最終傷害
        ctx = EventContext(actor=attacker, target=self, dmg=float(dmg))
        event_manager.emit(EventType.BEFORE_TAKE_DAMAGE, ctx=ctx)

        # 把可修改過的傷害帶入護盾/無敵等傳統結算
        damage = max(0.0, ctx.dmg)

        # 護盾
        if self.shield > 0:
            absorbed = min(damage, float(self.shield))
            self.shield -= absorbed
            damage -= absorbed

        # 無敵
        if damage <= 0.0:
            actual = 0
        else:
            before = self.hp
            self.hp = max(0, self.hp - int(round(damage)))
            actual = before - self.hp

        # 扣血後事件（提供實際造成的數字）
        ctx.dmg = float(actual)
        event_manager.emit(EventType.AFTER_TAKE_DAMAGE, ctx=ctx)
        return actual
        
    
    def add_hp(self, add):
        # 回血
        if add >= 0:
            self.hp = min(self.hp + add, self.max_hp)
        # 扣血
        else:
            damage = -add
            if self.shield > 0:
                absorbed = min(damage, self.shield)
                self.shield -= absorbed
                damage -= absorbed
            self.hp = max(0, self.hp - damage)

    def add_shield(self, add):
        self.shield = max(0, self.shield + add)

    # === 攻防數值 ===
    def add_patk(self, add):
        self.patk = max(0, self.patk + add)

    def add_matk(self, add):
        self.matk = max(0, self.matk + add)

    def add_pdef(self, add):
        self.pdef = max(0, self.pdef + add)

    def add_mdef(self, add):
        self.mdef = max(0, self.mdef + add)

    # === 爆擊相關 ===
    def add_cri(self, add):
        self.cri = max(0.0, self.cri + add)

    def add_cridmg(self, add):
        # 保底 1.5 倍爆傷（
        self.cridmg = max(basiccridmg, self.cridmg + add)

    # === 命中與閃避 ===
    def add_hit(self, add):
        self.hit = max(0.0, self.hit + add)

    def add_miss(self, add):
        self.miss = max(0.0, self.miss + add)
    
    #=== 處理戰鬥 ===
    #接收效果
    def receive_buff(self, src, buff):
        buff.source = src
        event_manager.emit(EventType.APPLY_BUFF, actor=src, target=self, skill=None, data={"buff": buff})
        if buff.phase == Buff.Phase.APPLY:
            # 立刻生效（會註冊 BEFORE_TAKE_DAMAGE 等事件）
            EffectRegistry.apply[buff.effect](src, self, buff)
            if buff.duration != 0:
                buff._fresh = True
                self.buffs.append(buff)
        else:
            self.buffs.append(buff)

    #觸發時機
    def trigger_phase(self, phase):
        expired = []
        for buff in self.buffs:
            if buff.phase == phase:
                if phase == Buff.Phase.APPLY:
                    # ✅ 首次不扣回合；之後經過 APPLY 才開始倒數
                    if getattr(buff, "_fresh", False):
                        buff._fresh = False
                    else:
                        buff.duration -= 1
                else:
                    #  START/END：每次經過都套用並倒數
                    EffectRegistry.apply[buff.effect](buff.source, self, buff)
                    buff.duration -= 1

            if buff.duration <= 0:
                # 解除
                EffectRegistry.remove[buff.effect](buff.source, self, buff)
                event_manager.emit(EventType.REMOVE_BUFF, actor=buff.source, target=self,
                                data={"buff": buff})
                expired.append(buff)

        for b in expired:
            self.buffs.remove(b)

        
    #處理眩暈
    def remove_stun(self):
        if self.stun > 0:
            self.stun -= 1
    
    #處理立即觸發之長時間效果
    def buff_end_round(self):
        expired = []
        for buff in self.buffs:
            if buff.phase == Buff.Phase.APPLY:
                buff.duration -= 1
            if buff.duration <= 0:
                EffectRegistry.remove[buff.effect](buff.source, self, buff)
                event_manager.emit(EventType.REMOVE_BUFF, actor=buff.source, target=self, data={"buff": buff})  # ★ 新增
                expired.append(buff)
        for b in expired:
            self.buffs.remove(b)              
    #展示學會之技能
    def show_skills(self):
        for i, s in enumerate(self.skills):
            print(f"{i}. {s.name} ({s.desc}) CD:{s.cdtime}/{s.cd}")

    def choose_skill(self, idx):
        skill = self.skills[idx]
        if skill.is_available():
            return skill.be_used()
        else:
            print(f"⚠️ 技能 {skill.name} 冷卻中！")
            return []
    
    def reduce_cd(self):
        for s in self.skills:
            s.next_turn()
            
    def learn_skill(self, skill_name):
        from battle.skill_library import SkillLibrary
        skill = SkillLibrary.get(skill_name)
        if skill:
            self.skills.append(skill)   # 加入 Skill 物件
            print(f"{self.name} 學會了技能【{skill_name}】！")
        else:
            print(f"❌ 技能 {skill_name} 不存在於技能庫")

    def level_up(self, times: int = 1):
        for _ in range(times):
            self.lv += 1
            # 依曲線加屬性
            inc_hp   = self._growth_inc("hp",   self.lv)
            inc_patk = self._growth_inc("patk", self.lv)
            inc_pdef = self._growth_inc("pdef", self.lv)
            inc_matk = self._growth_inc("matk", self.lv)
            inc_mdef = self._growth_inc("mdef", self.lv)
            inc_cri  = self._growth_inc("cri",  self.lv)

            self.max_hp  += inc_hp;   self.hp  += inc_hp
            self.max_patk+= inc_patk; self.patk+= inc_patk
            self.max_pdef+= inc_pdef; self.pdef+= inc_pdef
            self.max_matk+= inc_matk; self.matk+= inc_matk
            self.max_mdef+= inc_mdef; self.mdef+= inc_mdef
            self.max_cri += inc_cri;  self.cri += inc_cri

    
    def obtained_exp(self, earned_exp: int):
        self.exp += int(earned_exp)          
        while self.exp >= self.lv * self.lv * 100:
            self.level_up(1)

    def set_lv(self, lv: int):
        if lv <= self.lv: return
        self.level_up(lv - self.lv)
    
    def _growth_inc(self, key, new_lv):
        g = self._job_growth.get(key)
        if not g: return 0.0
        base = float(g.get("base", 0.0))
        pl   = float(g.get("per_level", 0.0))
        # 這一次升到 new_lv 
        raw  = base + pl * max(0, new_lv - 1)
        # 乘上職業基礎倍率
        mult = float(self.stats.get(key, 1.0))
        return raw * mult