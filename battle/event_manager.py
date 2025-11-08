from enum import Enum,auto 
from dataclasses import dataclass, field
from typing import Any,Callable,Dict,List

class EventType(Enum):
    TURN_START = auto()
    BEFORE_ACTION = auto()
    BEFORE_ATTACK = auto()
    DAMAGE_CALC = auto()
    BEFORE_TAKE_DAMAGE = auto()
    AFTER_TAKE_DAMAGE = auto()
    AFTER_ATTACK = auto()
    TURN_END = auto()
    APPLY_BUFF = auto()
    REMOVE_BUFF = auto()
    SKILL_CAST = auto()
    SKILL_RESOLVE = auto()

@dataclass
class EventContext:
    actor : Any = None
    target: Any = None
    skill: Any = None
    dmg: float = 0.0
    data: Dict[str,Any] = field(default_factory=dict)
    canceled:bool = False
    stop: bool = False
    
    def cancel(self): self.canceled = True
    def stop_propagation(self): self.stop = True
    
Handler = Callable[[EventType,EventContext],None]

class _Entry:
    __slots__ = ("priority","handler","once","owner") 
    def __init__(self,priority:int ,handler: Handler,once: bool,owner: Any):
        self.priority = priority
        self.handler  = handler
        self.once = once
        self.owner = owner

class EventManager:
    def __init__(self):
        self._listeners: Dict [EventType,List[_Entry]] = {}
    
    def subscribe(self,event: EventType,handler: Handler, *,
                  priority: int = 0,once: bool = False,owner: Any = None):
        lst = self._listeners.setdefault(event,[])
        lst.append(_Entry(priority,handler,once,owner))
        #高優先先執行
        lst.sort(key = lambda e : -e.priority)
        return handler #token
    
    def unsubscribe(self,event : EventType,handler: Handler):
        lst = self._listeners.get(event)
        if not lst: return
        self._listeners[event] = [e for e in lst if e.handler is not handler]
    
    def unsubscribe_owner(self,owner: Any):
        for ev, lst in self._listeners.items():
            self._listeners[ev] = [e for e in lst if e.owner is not owner]
    
    def emit(self,event:EventType, **kwargs)->EventContext:
        ctx: EventContext = kwargs.get("ctx") or EventContext()
        
        for k ,v in kwargs.items():
            if k != "ctx" :
                setattr(ctx,k,v)
        
        for entry in list(self._listeners.get(event,[])):
            entry.handler(event, ctx) 
            if entry.once:
                self.unsubscribe(event, entry.handler)
            if ctx.stop:
                break
        return ctx
    
#全域單例
event_manager = EventManager()           
                