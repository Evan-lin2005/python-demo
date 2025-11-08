_log_sink = None
def set_log_sink(fn):  # fn: (str) -> None
    global _log_sink
    _log_sink = fn

def _out(msg: str):
    if _log_sink:
        _log_sink(msg)
    else:
        print(msg)

class BattleLog:
    @staticmethod
    def output_damage(src, tgt, dmg):
        _out(f"{src} 對 {tgt} 造成 {dmg:.0f} 點傷害")

    @staticmethod
    def output_buff(name, effect, val):
        if val >= 0:
            _out(f"{name} 提升了 {val:.0f} 點 {effect}")
        else:
            _out(f"{name} 降低了 {-val:.0f} 點 {effect}")

    @staticmethod
    def output_dot(name, effect, val):
        _out(f"{name} 損失了 {abs(val):.0f} 點血量 ， 因為 {effect}")

    @staticmethod
    def output_miss(src, tgt):
        _out(f"{src} 攻擊 {tgt} 被閃避了！")

