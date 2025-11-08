from battle.buff import Buff, Target

class Skill:
    def __init__(self, name, desc, cd, cost, buffs,target=Target.ENEMY, growth = None):
        self.name = name
        self.desc = desc
        self.cd = cd
        self.cdtime = 0
        self.cost = cost
        self.buffs = buffs
        self.target = target
        self.maxLevel = 10
        self.currLevel = 1
        self.growth_map = growth

    def is_available(self):
        return self.cdtime == 0

    def be_used(self):
        self.cdtime = self.cd
        return self.buffs

    def next_turn(self):
        self.cdtime = max(0, self.cdtime - 1)
    
    def level_up(self):
        if self.currLevel >= self.maxLevel:
            print(f"{self.name} 已達最高等級 Lv.{self.maxLevel}")
            return False

        upgraded = False
        for buff in self.buffs:
            growth = self.growth_map.get(buff.name)
            if growth:
                buff.percent += growth.get("percent", 0)
                buff.base += growth.get("base", 0)
                upgraded = True

        if upgraded:
            self.currLevel += 1
            print(f"✨ {self.name} 升級為 Lv.{self.currLevel}")
        else:
            print(f"⚠️ {self.name} 無對應成長設定，升級無效")

        return upgraded