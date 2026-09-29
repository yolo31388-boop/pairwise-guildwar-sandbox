"""帮派战沙盘与战术指令系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guildwar.sandbox import GuildwarSandbox, Stronghold, TacticalOrder

class TestCaptureRequiresDuration:
    def test_capture_needs_sustained_occupation(self):
        gs = GuildwarSandbox()
        gs.strongholds["s1"] = Stronghold("s1", "fort", owner="A", troops=10)
        # 100人打10人，但只占了1秒
        result = gs.capture_stronghold("s1", "B", 100, duration=0.1)
        assert result == False  # bug1: 兵力优势直接占领

class TestMarchTime:
    def test_troops_take_time_to_march(self):
        gs = GuildwarSandbox()
        gs.strongholds["s1"] = Stronghold("s1", "a", x=0, y=0)
        gs.strongholds["s2"] = Stronghold("s2", "b", x=100, y=100)
        t = gs.calculate_march_time("s1", "s2", 1000)
        assert t > 0  # bug2: 0

class TestOrderCooldown:
    def test_cannot_spam_orders(self):
        gs = GuildwarSandbox()
        gs.order_cooldown["A"] = 100.0
        assert gs.can_issue_order("A", 101.0) == True
        assert gs.can_issue_order("A", 100.5) == False  # bug3: 都返回True

class TestSupplyLine:
    def test_cut_supply_weakens_troops(self):
        gs = GuildwarSandbox()
        gs.strongholds["s1"] = Stronghold("s1", "front", owner="A", troops=100, supply_connected=False)
        assert gs.check_supply_line("s1") == False  # bug4: True
        # 断补给应该有惩罚

class TestMoraleByCasualties:
    def test_morale_affected_by_casualty_ratio(self):
        gs = GuildwarSandbox()
        gs.morale["A"] = 100
        gs.update_morale("A", "win", casualties=0.9)  # 惨胜
        m1 = gs.morale["A"]
        gs.morale["A"] = 100
        gs.update_morale("A", "win", casualties=0.1)  # 完胜
        m2 = gs.morale["A"]
        assert m2 > m1  # bug5: 都是+10

class TestTerrain:
    def test_mountain_slows_movement(self):
        gs = GuildwarSandbox()
        gs.strongholds["s1"] = Stronghold("s1", "m", terrain="mountain")
        mod = gs.get_terrain_modifier("s1")
        assert mod["move_speed"] < 1.0  # bug6: 1.0
        assert mod["defense"] > 1.0

class TestDefenseBonus:
    def test_defenders_have_bonus(self):
        gs = GuildwarSandbox()
        gs.strongholds["s1"] = Stronghold("s1", "fort", defense_bonus=1.5)
        assert gs.get_defense_bonus("s1") > 1.0  # bug7: 1.0

class TestTruceEnforcement:
    def test_truce_prevents_attacks(self):
        gs = GuildwarSandbox()
        gs.enforce_truce("A", "B")
        # 应该有方法检查是否在停战中
        assert hasattr(gs, "is_at_truce")
        assert gs.is_at_truce("A", "B") == True  # bug8: 没有强制力
