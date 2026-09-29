"""帮派战沙盘与战术指令系统"""
import math
from dataclasses import dataclass, field

# 占领易主所需的持续占领秒数
CAPTURE_HOLD_SECONDS = 5.0
# 全局指令冷却（秒）
GLOBAL_ORDER_COOLDOWN = 1.0
# 单类型指令冷却（秒）
ORDER_TYPE_COOLDOWN = 3.0
# 行军基准速度（坐标单位/秒，按1个兵计算）
BASE_MARCH_SPEED = 10.0
# 停战强制保护期（秒）
TRUCE_PROTECTION_SECONDS = 300.0
# 断补给时每秒兵力衰减比例
SUPPLY_ATTRITION_RATE = 0.01
# 断补给时攻击力惩罚
SUPPLY_ATTACK_PENALTY = 0.5

TERRAIN_MODIFIERS = {
    "plain":    {"move_speed": 1.0, "defense": 1.0, "vision": 1.0},
    "mountain": {"move_speed": 0.5, "defense": 1.5, "vision": 0.7},
    "forest":   {"move_speed": 0.8, "defense": 1.2, "vision": 0.5},
    "river":    {"move_speed": 0.6, "defense": 1.1, "vision": 0.9},
}

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
        self.order_type_cooldown: dict[tuple, float] = {}  # (guild, type) -> last time
        self.truces: dict[tuple, float] = {}  # (guildA, guildB) -> 签约时间
        self.truce_violations: list[str] = []  # 全服公告
        self.battle_streak: dict[str, int] = {}  # guild -> 连续作战场次

    # fix1: 兵力优势 + 持续占领N秒才易主
    def capture_stronghold(self, sid: str, attacker: str, attacker_troops: int, duration: float) -> bool:
        sh = self.strongholds[sid]
        defense = sh.troops * self.get_defense_bonus(sid)
        if attacker_troops <= defense:
            return False
        if duration < CAPTURE_HOLD_SECONDS:
            return False
        sh.owner = attacker
        sh.troops = attacker_troops
        return True

    # fix2: 按距离和地形计算行军时间，大部队更慢
    def calculate_march_time(self, from_sid: str, to_sid: str, troops: int) -> float:
        a = self.strongholds[from_sid]
        b = self.strongholds[to_sid]
        distance = math.hypot(b.x - a.x, b.y - a.y)
        speed = BASE_MARCH_SPEED * TERRAIN_MODIFIERS.get(b.terrain, TERRAIN_MODIFIERS["plain"])["move_speed"]
        # 兵力越多行军越慢
        speed /= 1.0 + math.log10(max(troops, 1)) * 0.1
        return distance / speed if speed > 0 else float("inf")

    # fix3: 全局冷却 + 单指令冷却
    def can_issue_order(self, guild: str, current_time: float, order_type: str = None) -> bool:
        last = self.order_cooldown.get(guild)
        if last is not None and current_time - last < GLOBAL_ORDER_COOLDOWN:
            return False
        if order_type is not None:
            last_type = self.order_type_cooldown.get((guild, order_type))
            if last_type is not None and current_time - last_type < ORDER_TYPE_COOLDOWN:
                return False
        return True

    # fix4: 补给线状态；断补给时兵力衰减、攻击降低
    def check_supply_line(self, sid: str) -> bool:
        return self.strongholds[sid].supply_connected

    def apply_supply_attrition(self, sid: str, elapsed: float):
        sh = self.strongholds[sid]
        if not sh.supply_connected:
            sh.troops = max(0, int(sh.troops * (1 - SUPPLY_ATTRITION_RATE * elapsed)))

    def get_attack_power(self, sid: str) -> float:
        sh = self.strongholds[sid]
        power = float(sh.troops)
        if not sh.supply_connected:
            power *= SUPPLY_ATTACK_PENALTY
        return power

    # fix5: 士气按结果、伤亡比、连续作战综合计算
    def update_morale(self, guild: str, battle_result: str, casualties: float):
        morale = self.morale.get(guild, 100.0)
        streak = self.battle_streak.get(guild, 0) + 1
        self.battle_streak[guild] = streak
        fatigue = min(streak * 0.5, 5.0)  # 连续作战疲劳
        if battle_result == "win":
            gain = 10.0 * (1.0 - casualties)  # 惨胜收益大减
            morale += gain - fatigue
        else:
            loss = 10.0 * (0.5 + casualties)  # 大败更伤，小败也掉
            morale -= loss + fatigue
        self.morale[guild] = max(0.0, morale)

    # fix6: 地形影响移动、防御、视野
    def get_terrain_modifier(self, sid: str) -> dict:
        terrain = self.strongholds[sid].terrain
        return dict(TERRAIN_MODIFIERS.get(terrain, TERRAIN_MODIFIERS["plain"]))

    # fix7: 防守方有工事 + 地形加成
    def get_defense_bonus(self, sid: str) -> float:
        sh = self.strongholds[sid]
        return sh.defense_bonus * self.get_terrain_modifier(sid)["defense"]

    # fix8: 停战协议有强制保护期，违约有惩罚并全服公告
    def enforce_truce(self, guild_a: str, guild_b: str, current_time: float = 0.0) -> bool:
        key = tuple(sorted((guild_a, guild_b)))
        self.truces[key] = current_time
        return True

    def is_at_truce(self, guild_a: str, guild_b: str, current_time: float = None) -> bool:
        key = tuple(sorted((guild_a, guild_b)))
        if key not in self.truces:
            return False
        if current_time is None:
            return True
        return current_time - self.truces[key] < TRUCE_PROTECTION_SECONDS

    def violate_truce(self, violator: str, guild_a: str, guild_b: str):
        self.morale[violator] = max(0.0, self.morale.get(violator, 100.0) - 20.0)
        self.truce_violations.append(
            f"【全服公告】{violator} 撕毁了 {guild_a} 与 {guild_b} 的停战协议，士气大跌！"
        )
