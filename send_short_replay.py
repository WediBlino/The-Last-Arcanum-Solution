#!/usr/bin/env python3
import argparse
import socket
import struct
import time


HIST_HEX = (
    "0202020000020202000001000100010001000100010001000100010101000202020000010001000100010001000100010100"
    "0202020000010001000101000202030000010001000100010001000100010101000202030000020203000002020300000101"
    "0001000100010100010001010001000101000101000100010001000101000100010001000100010001000100010001000100"
    "0101000100010001010100010100010001000100010100010100010001010101000101010100010001000100010101010001"
    "01010001010001000201040000010001000100010001000100010001000100030200"
)


def build_payload(seed, hist):
    payload = bytearray(0x108)
    struct.pack_into("<II", payload, 0, seed, len(hist))
    payload[8 : 8 + len(hist)] = hist
    return bytes(payload)


def recv_response(sock, timeout):
    sock.settimeout(timeout)
    first = sock.recv(4)
    if len(first) < 4:
        return first
    n = struct.unpack("<I", first)[0]
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            break
        data += chunk
    return first + data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("port", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hist-hex")
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--single-connection", action="store_true")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    hist_hex = args.hist_hex
    if hist_hex is None:
        try:
            with open("short_replay_planner_results.txt", "r", encoding="utf-8") as inp:
                first = inp.readline().strip()
            hist_hex = first.split("hist=", 1)[1]
        except Exception:
            hist_hex = HIST_HEX
    hist = bytes.fromhex(hist_hex)
    payload = build_payload(args.seed, hist)
    print(f"seed={args.seed} hist_len={len(hist)} payload_len={len(payload)} hist_hex={hist.hex()}")
    if args.single_connection:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            sock.sendall(b"TLA1")
            if args.delay:
                time.sleep(args.delay)
            sock.sendall(b"TLA2" + struct.pack("<I", len(payload)) + payload)
            resp = recv_response(sock, args.timeout)
    else:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            sock.sendall(b"TLA1")
        if args.delay:
            time.sleep(args.delay)
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            sock.sendall(b"TLA2" + struct.pack("<I", len(payload)) + payload)
            resp = recv_response(sock, args.timeout)
    text = resp.decode("utf-8", "replace")
    print(f"response_hex={resp.hex()}")
    print(f"response_text={text!r}")
    decoded = b""
    if len(resp) >= 14:
        body = resp[4:]
        key = body[0] ^ ord("C")
        candidate = bytes(b ^ key for b in body)
        if candidate.startswith(b"Cyberthon{"):
            decoded = candidate
            print(f"xor_key=0x{key:02x}")
            print(f"decoded_flag={candidate.decode('utf-8', 'replace')}")
    with open("short_replay_remote_result.txt", "w", encoding="utf-8") as out:
        out.write(f"seed={args.seed} hist_len={len(hist)} payload_len={len(payload)} hist_hex={hist.hex()}\n")
        out.write(f"response_hex={resp.hex()}\n")
        out.write(f"response_text={text!r}\n")
        if decoded:
            out.write(f"xor_key=0x{key:02x}\n")
            out.write(f"decoded_flag={decoded.decode('utf-8', 'replace')}\n")
    return 0 if decoded or b"Cyberthon{" in resp else 1


if __name__ == "__main__":
    raise SystemExit(main())
