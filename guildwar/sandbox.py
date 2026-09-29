"""帮派战沙盘与战术指令系统 - 含8个bug"""
import time
from dataclasses import dataclass, field

@dataclass
class Stronghold:
    sid: str
    name: str
    owner: str = ""
    troops: int = 0
    x: int = 0
    y: int = 0
    terrain: str = "plain"  # plain/mountain/forest/river
    defense_bonus: float = 1.0
    supply_connected: bool = True

@dataclass
class TacticalOrder:
    oid: str
    type: str  # attack/defend/retreat/reinforce
    from_sid: str
    to_sid: str
    troops: int
    issued_at: float = 0
    arrives_at: float = 0

class GuildwarSandbox:
    def __init__(self):
        self.strongholds: dict[str, Stronghold] = {}
        self.orders: list[TacticalOrder] = []
        self.morale: dict[str, float] = {}  # guild -> morale
        self.order_cooldown: dict[str, float] = {}  # guild -> last order time
        self.truces: set = set()

    def capture_stronghold(self, sid: str, attacker: str, attacker_troops: int, duration: float) -> bool:
        # bug1: 只看最后一击
        sh = self.strongholds[sid]
        if attacker_troops > sh.troops:
            sh.owner = attacker
            sh.troops = attacker_troops
            return True
        return False

    def calculate_march_time(self, from_sid: str, to_sid: str, troops: int) -> float:
        # bug2: 瞬间到达
        return 0.0

    def can_issue_order(self, guild: str, current_time: float) -> bool:
        # bug3: 无冷却
        return True

    def check_supply_line(self, sid: str) -> bool:
        # bug4: 不计算补给线
        return True

    def update_morale(self, guild: str, battle_result: str, casualties: float):
        # bug5: 只看胜负
        if battle_result == "win":
            self.morale[guild] = self.morale.get(guild, 100) + 10
        else:
            self.morale[guild] = self.morale.get(guild, 100) - 10

    def get_terrain_modifier(self, sid: str) -> dict:
        # bug6: 无地形影响
        return {"move_speed": 1.0, "defense": 1.0}

    def get_defense_bonus(self, sid: str) -> float:
        # bug7: 防守无加成
        return 1.0

    def enforce_truce(self, guild_a: str, guild_b: str) -> bool:
        # bug8: 停战无强制力
        self.truces.add((guild_a, guild_b))
        return True
