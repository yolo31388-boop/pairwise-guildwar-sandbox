"""帮派战沙盘与战术指令系统"""
import math
import time
from dataclasses import dataclass, field

TERRAIN_MODIFIERS = {
    # move_speed: 行军速度系数; defense: 防御加成系数; vision: 视野系数
    "plain":    {"move_speed": 1.0, "defense": 1.0, "vision": 1.0},
    "forest":   {"move_speed": 0.8, "defense": 1.2, "vision": 0.7},
    "mountain": {"move_speed": 0.5, "defense": 1.5, "vision": 1.2},
    "river":    {"move_speed": 0.6, "defense": 1.1, "vision": 0.9},
}

MARCH_SPEED = 10.0            # 平原每秒行军距离
CAPTURE_HOLD_SECONDS = 5.0    # 兵力优势方需持续占领的秒数
GLOBAL_ORDER_COOLDOWN = 1.0   # 全局指令冷却（秒）
ORDER_TYPE_COOLDOWN = 5.0     # 同类型指令冷却（秒）
SUPPLY_ATTRITION_RATE = 0.05  # 断补给每秒兵力流失比例
SUPPLY_ATTACK_PENALTY = 0.5   # 断补给攻击系数
TRUCE_PROTECTION_SECONDS = 300.0  # 停战强制保护期（秒）
TRUCE_VIOLATION_MORALE_PENALTY = 30.0
MAX_CONSECUTIVE_BATTLE_SECONDS = 600.0  # 连续作战疲劳阈值


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
        self.morale: dict[str, float] = {}          # guild -> morale
        self.order_cooldown: dict[str, float] = {}  # guild -> last order time
        self.order_type_cooldown: dict[tuple, float] = {}  # (guild, type) -> last time
        self.truces: dict[tuple, dict] = {}         # (a, b) -> truce info
        self.announcements: list[str] = []          # 全服公告
        self.consecutive_losses: dict[str, int] = {}
        self.battle_since: dict[str, float] = {}    # guild -> 连续作战起始时间
        # bug1: 占领进度 {sid: {"guild": g, "elapsed": seconds}}
        self.capture_progress: dict[str, dict] = {}

    # ---- bug1: 占领按兵力对比 + 持续占领时间 ----
    def capture_stronghold(self, sid: str, attacker: str, attacker_troops: int, duration: float) -> bool:
        sh = self.strongholds[sid]
        if sh.owner == attacker:
            sh.troops = attacker_troops
            return True
        # 防守方有效兵力 = 驻军 * 防御加成（含工事和地形）
        effective_defense = sh.troops * self.get_defense_bonus(sid)
        if attacker_troops <= effective_defense:
            self.capture_progress.pop(sid, None)
            return False
        # 兵力优势方需持续占领 CAPTURE_HOLD_SECONDS 才易主
        progress = self.capture_progress.setdefault(sid, {"guild": attacker, "elapsed": 0.0})
        if progress["guild"] != attacker:
            progress["guild"] = attacker
            progress["elapsed"] = 0.0
        progress["elapsed"] += duration
        if progress["elapsed"] < CAPTURE_HOLD_SECONDS:
            return False
        sh.owner = attacker
        sh.troops = attacker_troops
        self.capture_progress.pop(sid, None)
        return True

    # ---- bug2: 行军时间按距离和地形计算 ----
    def calculate_march_time(self, from_sid: str, to_sid: str, troops: int) -> float:
        a = self.strongholds[from_sid]
        b = self.strongholds[to_sid]
        distance = math.hypot(b.x - a.x, b.y - a.y)
        if distance <= 0:
            return 0.0
        # 途经地形取两端平均值，山地/森林减速
        speed = MARCH_SPEED * (self.get_terrain_modifier(from_sid)["move_speed"]
                               + self.get_terrain_modifier(to_sid)["move_speed"]) / 2
        return distance / speed

    def issue_order(self, order: TacticalOrder, current_time: float) -> bool:
        """下达指令：检查冷却、停战，计算到达时间（执行有延迟，移动中可被拦截）"""
        march = self.calculate_march_time(order.from_sid, order.to_sid, order.troops)
        order.issued_at = current_time
        order.arrives_at = current_time + march
        self.orders.append(order)
        return True

    def intercept_order(self, oid: str, current_time: float) -> bool:
        """拦截仍在行军途中的指令"""
        for order in self.orders:
            if order.oid == oid and current_time < order.arrives_at:
                self.orders.remove(order)
                return True
        return False

    # ---- bug3: 全局冷却 + 单类型冷却 ----
    def can_issue_order(self, guild: str, current_time: float) -> bool:
        last = self.order_cooldown.get(guild)
        if last is not None and current_time - last < GLOBAL_ORDER_COOLDOWN:
            return False
        return True

    def can_issue_order_type(self, guild: str, order_type: str, current_time: float) -> bool:
        if not self.can_issue_order(guild, current_time):
            return False
        last = self.order_type_cooldown.get((guild, order_type))
        if last is not None and current_time - last < ORDER_TYPE_COOLDOWN:
            return False
        return True

    def record_order(self, guild: str, order_type: str, current_time: float):
        self.order_cooldown[guild] = current_time
        self.order_type_cooldown[(guild, order_type)] = current_time

    # ---- bug4: 补给线 ----
    def check_supply_line(self, sid: str) -> bool:
        return self.strongholds[sid].supply_connected

    def recompute_supply(self, guild: str):
        """从己方主城（troops 最多的己方据点）BFS，连通的前线据点才有补给"""
        owned = [s for s in self.strongholds.values() if s.owner == guild]
        if not owned:
            return
        base = max(owned, key=lambda s: s.troops)
        base.supply_connected = True
        # 简化模型：与任一已连通己方据点相邻（距离 <= 补给半径）即连通
        supply_radius = 150.0
        changed = True
        while changed:
            changed = False
            for s in owned:
                if s.supply_connected:
                    continue
                for other in owned:
                    if other.supply_connected and math.hypot(
                            s.x - other.x, s.y - other.y) <= supply_radius:
                        s.supply_connected = True
                        changed = True
                        break

    def apply_supply_attrition(self, sid: str, elapsed: float) -> float:
        """断补给的前线据点：兵力持续下降，返回当前攻击系数"""
        sh = self.strongholds[sid]
        if sh.supply_connected:
            return 1.0
        sh.troops = max(0, int(sh.troops * (1 - SUPPLY_ATTRITION_RATE * elapsed)))
        return SUPPLY_ATTACK_PENALTY

    # ---- bug5: 士气按结果、伤亡比、连续作战综合计算 ----
    def update_morale(self, guild: str, battle_result: str, casualties: float):
        casualties = max(0.0, min(1.0, casualties))
        morale = self.morale.get(guild, 100.0)
        if battle_result == "win":
            # 惨胜（高伤亡）收益远低于完胜
            morale += 10.0 * (1.0 - casualties)
            self.consecutive_losses[guild] = 0
        else:
            # 失败按伤亡比放大惩罚，连续小败会累积崩溃
            self.consecutive_losses[guild] = self.consecutive_losses.get(guild, 0) + 1
            streak = self.consecutive_losses[guild]
            morale -= 10.0 * (0.5 + casualties) * (1.0 + 0.5 * (streak - 1))
        # 连续作战疲劳惩罚
        started = self.battle_since.setdefault(guild, time.time())
        fatigue = max(0.0, (time.time() - started) / MAX_CONSECUTIVE_BATTLE_SECONDS)
        morale -= 5.0 * min(1.0, fatigue)
        self.morale[guild] = max(0.0, morale)

    # ---- bug6: 地形影响移动、防御、视野 ----
    def get_terrain_modifier(self, sid: str) -> dict:
        sh = self.strongholds[sid]
        return dict(TERRAIN_MODIFIERS.get(sh.terrain, TERRAIN_MODIFIERS["plain"]))

    # ---- bug7: 防守方工事 + 地形加成 ----
    def get_defense_bonus(self, sid: str) -> float:
        sh = self.strongholds[sid]
        return sh.defense_bonus * self.get_terrain_modifier(sid)["defense"]

    # ---- bug8: 停战协议强制保护期 + 违约惩罚 ----
    @staticmethod
    def _truce_key(guild_a: str, guild_b: str) -> tuple:
        return tuple(sorted((guild_a, guild_b)))

    def enforce_truce(self, guild_a: str, guild_b: str) -> bool:
        key = self._truce_key(guild_a, guild_b)
        self.truces[key] = {"signed_at": time.time(),
                            "protection": TRUCE_PROTECTION_SECONDS}
        return True

    def is_at_truce(self, guild_a: str, guild_b: str, current_time: float = None) -> bool:
        key = self._truce_key(guild_a, guild_b)
        truce = self.truces.get(key)
        if truce is None:
            return False
        now = time.time() if current_time is None else current_time
        return now - truce["signed_at"] < truce["protection"]

    def violate_truce(self, violator: str, guild_a: str, guild_b: str,
                      current_time: float = None) -> bool:
        """保护期内进攻视为违约：士气惩罚并全服公告"""
        if not self.is_at_truce(guild_a, guild_b, current_time):
            return False
        morale = self.morale.get(violator, 100.0)
        self.morale[violator] = max(0.0, morale - TRUCE_VIOLATION_MORALE_PENALTY)
        other = guild_b if violator == guild_a else guild_a
        self.announcements.append(
            f"[全服公告] 帮派 {violator} 在停战保护期内攻击 {other}，违反停战协议，"
            f"士气 -{TRUCE_VIOLATION_MORALE_PENALTY:.0f}！")
        return True
