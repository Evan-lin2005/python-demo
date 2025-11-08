from enum import Enum,auto

class Target(Enum):#效果指涉對象
    SELF = auto()
    ALLY = auto()
    TEAM = auto()
    ENEMY = auto()
    ENEMIES = auto()

class Phase(Enum):#回合階段
    START = auto()
    APPLY = auto()
    END = auto()
    
class Effect(Enum):#效果種類
    PHYSICDAMAGE = auto()
    MAGICDAMAGE = auto()
    DOT = auto()
    ADDHP = auto()
    ADDPATK = auto()
    ADDPDEF = auto()
    ADDMATK = auto()
    ADDMDEF = auto()
    ADDCRI = auto()
    ADDCRIDMG = auto()
    ADDVIT = auto()
    ADDMISS = auto()
    ADDHIT = auto()
    ADDSHIELD = auto()
    COUNTER = auto()     
    INVINCIBLE = auto() 
    LIFESTEAL = auto()  
    THORNS = auto()   # 反傷
    MARK = auto()          # 標記（堆疊/消耗）
    CONSUME_MARK = auto()  # 消耗標記
    PREP_WINDOW = auto()   # 準備窗：短時間提升暴擊/命中/下一擊乘數
    TAUNT = auto() #嘲諷
    STUN = auto() #暈眩
    SELF_STUN = auto() #自身暈眩
    
class Buff():#效果
    def __init__(self,target,phase,name,desc,duration,effect,percent = 0.0,base = 0.0):
        self.target = target
        self.phase = phase
        self.name = name
        self.desc = desc
        self.duration = duration
        self.effect = effect
        self.percent = percent
        self.base = base
        self.source = None
        self.applied = []#紀錄數值變化
        self._fresh = False
    