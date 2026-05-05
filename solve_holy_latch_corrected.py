#!/usr/bin/env python3
import argparse
import socket
import struct


# Normal enemy table selected by uniform_int_distribution(0, 10).
# Stats/types are reconstructed from static_init_6cd0_7520.asm constants:
# 0..3 type 1, 4..5 type 3, 6..8 type 2, 9 type 4, 10 type 5.
ENEMIES = [
    ("Vile Leaf", 20, 24, 3, 20, 1),
    ("Devil Root", 100, 60, 6, 30, 1),
    ("Cruel Rose", 300, 120, 80, 100, 1),
    ("Doom Tree", 1000, 300, 300, 500, 1),
    ("Evil Minotaur", 150, 80, 40, 80, 3),
    ("Giant Lion", 600, 300, 120, 200, 3),
    ("Despicable Crook", 15, 35, 0, 15, 2),
    ("Devious Pirate", 160, 90, 80, 120, 2),
    ("Void Lich", 1200, 200, 1200, 2000, 2),
    ("Abyssal Dragon", 30000, 2500, 2000, 5000, 4),
    ("The Crimson Lord?", 100000, 3000, 3000, 9999, 5),
]


class MT19937:
    def __init__(self, seed):
        self.mt = [0] * 624
        self.idx = 624
        self.mt[0] = seed & 0xffffffff
        for i in range(1, 624):
            self.mt[i] = (1812433253 * (self.mt[i - 1] ^ (self.mt[i - 1] >> 30)) + i) & 0xffffffff

    def gen(self):
        if self.idx >= 624:
            for i in range(624):
                y = (self.mt[i] & 0x80000000) | (self.mt[(i + 1) % 624] & 0x7fffffff)
                self.mt[i] = self.mt[(i + 397) % 624] ^ (y >> 1)
                if y & 1:
                    self.mt[i] ^= 0x9908b0df
            self.idx = 0
        y = self.mt[self.idx]
        self.idx += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9d2c5680
        y ^= (y << 15) & 0xefc60000
        y ^= y >> 18
        return y & 0xffffffff

    def randint(self, lo, hi):
        n = hi - lo + 1
        threshold = ((1 << 32) - n) % n
        while True:
            x = self.gen()
            product = x * n
            low = product & 0xffffffff
            if low >= threshold:
                return lo + (product >> 32)


def build(seed, spell_input=5, extra_reward_zero=False):
    rng = MT19937(seed)
    hist = []
    gold = 100
    owned = 1
    buys = []
    leaf_kills = 0
    normal_battles = 0

    def buy(cost, name):
        nonlocal gold, owned
        if gold < cost:
            return False
        # state0: shop, substate0: spell shop, buy first remaining, back, leave
        hist.extend([2, 1, 1, 0, 0])
        gold -= cost
        owned += 1
        buys.append(name)
        return True

    buy(30, "Fireball")
    remaining = [(200, "Lightning Strike"), (500, "Vigor"), (1000, "Holy Smite")]
    while remaining:
        cost, name = remaining[0]
        if gold >= cost:
            buy(cost, name)
            remaining.pop(0)
            continue

        idx = rng.randint(0, 10)
        normal_battles += 1
        hist.append(1)
        if idx == 0:
            # Fireball is input 2 and one-shots Vile Leaf with starting ATK.
            hist.extend([2, 0])
            gold += ENEMIES[idx][4]
            leaf_kills += 1
        else:
            hist.append(0)

        if len(hist) > 100000:
            return None

    latch = None
    latch_steps = 0
    while latch is None and latch_steps < 10000:
        idx = rng.randint(0, 10)
        normal_battles += 1
        latch_steps += 1
        hist.extend([1, 0])
        if ENEMIES[idx][5] == 4:
            latch = (idx, ENEMIES[idx][0], latch_steps)

    if latch is None:
        return None

    hist.extend([3, spell_input, 0])
    if extra_reward_zero:
        hist.append(0)

    return bytes(hist), {
        "seed": seed,
        "gold_after_buys": gold,
        "owned": owned,
        "buys": buys,
        "leaf_kills": leaf_kills,
        "normal_battles": normal_battles,
        "latch": latch,
        "spell_input": spell_input,
        "extra_reward_zero": extra_reward_zero,
        "hist_len": len(hist),
    }


def send_candidate(host, port, seed, hist, timeout=8):
    payload = struct.pack("<II", seed, len(hist)) + hist
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(b"TLA1")
        s.sendall(b"TLA2" + struct.pack("<I", len(payload)) + payload)
        first = s.recv(4)
        if len(first) < 4:
            return first
        n = struct.unpack("<I", first)[0]
        data = b""
        while len(data) < n:
            chunk = s.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return first + data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("port", type=int)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--stop", type=int, default=200)
    ap.add_argument("--spell-inputs", default="5")
    ap.add_argument("--extra-reward-zero", action="store_true")
    ap.add_argument("--timeout", type=int, default=8)
    args = ap.parse_args()

    spell_inputs = [int(x) for x in args.spell_inputs.split(",") if x]
    with open("holy_latch_corrected_results.txt", "w", encoding="utf-8") as out:
        for seed in range(args.start, args.stop):
            for spell_input in spell_inputs:
                built = build(seed, spell_input, args.extra_reward_zero)
                if built is None:
                    continue
                hist, meta = built
                line = f"candidate {meta} hist_hex={hist.hex()}"
                print(line, flush=True)
                out.write(line + "\n")
                out.flush()
                try:
                    resp = send_candidate(args.host, args.port, seed, hist, args.timeout)
                except Exception as exc:
                    resp = f"{type(exc).__name__}: {exc}".encode()
                text = resp.decode("utf-8", "replace")
                rline = f"response seed={seed} spell={spell_input} hex={resp.hex()} text={text!r}"
                print(rline, flush=True)
                out.write(rline + "\n")
                out.flush()
                if b"Cyberthon{" in resp:
                    return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
