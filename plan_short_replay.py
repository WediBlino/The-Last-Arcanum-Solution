#!/usr/bin/env python3
import argparse
import struct

from solve_holy_latch_corrected import ENEMIES, MT19937


SPELLS = [
    ("Fireball", 30),
    ("Lightning Strike", 200),
    ("Vigor", 500),
    ("Holy Smite", 1000),
    ("Skyfall", 2000),
    ("The Last Arcanum", 999999999),
]


class Planner:
    def __init__(self, seed, policy):
        self.seed = seed
        self.rng = MT19937(seed)
        self.policy = policy
        self.hist = []
        self.hp = 100
        self.max_hp = 100
        self.atk = 20
        self.defense = 20
        self.gold = 100
        self.owned = ["Attack"]
        self.shop = SPELLS[:]
        self.enemy_type = 0
        self.trace = []

    def buy_stat(self, stat_input):
        cost = 500 if stat_input >= 4 else 50
        inc = 500 if stat_input >= 4 else 50
        if self.gold < cost:
            return False
        self.hist.extend([2, 2, stat_input, 0, 0])
        self.gold -= cost
        if stat_input in (1, 4):
            self.max_hp = min(9999, self.max_hp + inc)
        elif stat_input in (2, 5):
            self.atk = min(9999, self.atk + inc)
        elif stat_input in (3, 6):
            self.defense = min(9999, self.defense + inc)
        else:
            raise ValueError(stat_input)
        self.trace.append(("buy_stat", stat_input, self.gold, self.atk, self.defense, self.max_hp, self.hp, len(self.hist)))
        return True

    def buy_spell_by_name(self, name):
        for i, (spell, cost) in enumerate(self.shop, 1):
            if spell == name and self.gold >= cost:
                self.hist.extend([2, 1, i, 0, 0])
                self.gold -= cost
                self.owned.append(spell)
                del self.shop[i - 1]
                self.trace.append(("buy_spell", spell, i, self.gold, list(self.owned), len(self.hist)))
                return True
        return False

    def maybe_buy_stats(self):
        # Policy syntax is a list of stat inputs to buy when affordable.
        changed = True
        while changed:
            changed = False
            for stat_input, limit in self.policy["stat_plan"]:
                current = {1: self.max_hp, 4: self.max_hp, 2: self.atk, 5: self.atk, 3: self.defense, 6: self.defense}[stat_input]
                if current < limit and self.buy_stat(stat_input):
                    changed = True
                    break

    def fight_cost(self, enemy):
        name, hp, atk, defense, gold, typ = enemy
        dmg = max(0, self.atk - defense)
        if dmg <= 0:
            return None
        turns = (hp + dmg - 1) // dmg
        taken = max(0, atk - self.defense) * max(0, turns - 1)
        if self.hp - taken <= 0:
            return None
        if turns > self.policy["max_turns"]:
            return None
        return turns, taken

    def step_battle(self):
        idx = self.rng.randint(0, 10)
        enemy = ENEMIES[idx]
        self.enemy_type = enemy[5]
        cost = self.fight_cost(enemy)
        if cost is None:
            self.hist.extend([1, 0])
            self.trace.append(("flee", idx, enemy[0], self.gold, self.hp, self.atk, self.defense, len(self.hist)))
            return
        turns, taken = cost
        self.hist.append(1)
        self.hist.extend([1] * turns)
        self.hist.append(0)
        self.hp -= taken
        self.gold += enemy[4]
        self.trace.append(("kill", idx, enemy[0], turns, taken, self.gold, self.hp, self.atk, self.defense, len(self.hist)))

    def latch_and_finish(self, max_latch_draws=200):
        for _ in range(max_latch_draws):
            idx = self.rng.randint(0, 10)
            enemy = ENEMIES[idx]
            self.hist.extend([1, 0])
            self.enemy_type = enemy[5]
            self.trace.append(("latch_try", idx, enemy[0], self.enemy_type, len(self.hist)))
            if self.enemy_type == 4:
                holy_input = self.owned.index("Holy Smite") + 1
                self.hist.extend([3, holy_input, 0])
                self.trace.append(("challenge", holy_input, len(self.hist)))
                return True
        return False

    def run(self, budget):
        self.maybe_buy_stats()
        draws = 0
        while self.gold < 1000 and len(self.hist) < budget - 20 and draws < self.policy["max_draws"]:
            self.maybe_buy_stats()
            if self.gold >= 1000:
                break
            self.step_battle()
            draws += 1
        if self.gold < 1000:
            return False
        if not self.buy_spell_by_name("Holy Smite"):
            return False
        ok = self.latch_and_finish()
        return ok and len(self.hist) <= budget


def payload(seed, hist):
    data = bytearray(0x108)
    struct.pack_into("<II", data, 0, seed, len(hist))
    data[8 : 8 + len(hist)] = hist
    return bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--stop", type=int, default=100000)
    ap.add_argument("--budget", type=int, default=256)
    args = ap.parse_args()

    policies = [
        {"name": "one_shot_atk_only", "stat_plan": [(2, 420), (5, 920)], "max_turns": 1, "max_draws": 200},
        {"name": "one_shot_atk_ramp", "stat_plan": [(2, 720), (5, 1220)], "max_turns": 1, "max_draws": 200},
        {"name": "one_shot_big_atk_early", "stat_plan": [(2, 220), (5, 720), (2, 920)], "max_turns": 1, "max_draws": 200},
        {"name": "small_atk_def_then_big_atk", "stat_plan": [(2, 70), (3, 70), (5, 570)], "max_turns": 4, "max_draws": 200},
        {"name": "small_atk_def_then_big_def_atk", "stat_plan": [(2, 70), (3, 70), (6, 570), (5, 570)], "max_turns": 6, "max_draws": 200},
        {"name": "balanced_small", "stat_plan": [(2, 220), (3, 220)], "max_turns": 5, "max_draws": 200},
        {"name": "def_first", "stat_plan": [(3, 120), (2, 170), (5, 670)], "max_turns": 6, "max_draws": 200},
        {"name": "atk_first", "stat_plan": [(2, 170), (3, 120), (5, 670)], "max_turns": 5, "max_draws": 200},
    ]
    with open("short_replay_planner_results.txt", "w", encoding="utf-8") as out:
        for seed in range(args.start, args.stop):
            for policy in policies:
                p = Planner(seed, policy)
                if p.run(args.budget):
                    line = (
                        f"FOUND seed={seed} policy={policy['name']} len={len(p.hist)} "
                        f"gold={p.gold} hp={p.hp} atk={p.atk} def={p.defense} hist={bytes(p.hist).hex()}"
                    )
                    print(line, flush=True)
                    out.write(line + "\n")
                    for t in p.trace:
                        out.write(repr(t) + "\n")
                    out.flush()
                    return 0
            if seed % 1000 == 0:
                print(f"checked {seed}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
