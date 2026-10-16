"""Wallshot test of the hub over a real WebSocket: a hit through a wall is refused, one on an open line counts, a player who keeps shooting through walls is banned.

Runs server.py in-process on a free port with a throwaway database (the real one is not touched), signs up
three players, starts an FM_BATTLE room on 03gate and sends positions + hits like a client. A shooter behind
the map's buildings hits the victim (must be refused: no hp message), then a shooter in the open (must land).

  python tools/test_wallshot.py          (needs assets/maps/03gate/shots.wtc: python tools/build_collision.py 03gate)
"""
import base64
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import server  # noqa: E402

MAP = "03gate"
VICTIM, CLEAR, BLOCKED = [-2.56, 0.02, 24.32], [2.56, 0.02, 24.32], [2.56, 0.02, -24.32]   # feet positions


class WS:
    """minimal stdlib WebSocket client (text frames, masked)"""

    def __init__(self, port, token):
        self.s = socket.create_connection(("127.0.0.1", port))
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /ws?token={token} HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.s.recv(1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.msgs = []
        self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def _exact(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise EOFError
            b += c
        return b

    def _reader(self):
        try:
            while True:
                b0, b1 = self._exact(2)
                n = b1 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self._exact(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._exact(8))[0]
                data = self._exact(n)
                if b0 & 0x0F == 1:
                    with self.lock:
                        self.msgs.append(json.loads(data))
        except (EOFError, OSError):
            pass

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n))
        self.s.sendall(head + mask + bytes(c ^ mask[i & 3] for i, c in enumerate(data)))

    def take(self, t):
        with self.lock:
            got = [m for m in self.msgs if m.get("t") == t]
            self.msgs = [m for m in self.msgs if m.get("t") != t]
        return got

    def wait(self, t, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            got = self.take(t)
            if got:
                return got[-1]
            time.sleep(0.02)
        raise TimeoutError(t)


def api(port, path, body=None, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    return json.loads(urllib.request.urlopen(req).read())


def main():
    if not os.path.exists(os.path.join(ROOT, "assets", "maps", MAP, "shots.wtc")):
        sys.exit(f"assets/maps/{MAP}/shots.wtc yok: python tools/build_collision.py {MAP}")
    tmp = tempfile.mkdtemp()
    server.DB_PATH = os.path.join(tmp, "test.db")
    server.init_db()
    srv = server.Server(("::", 0), server.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    users = []
    for i, nick in enumerate(("Kurban", "Acik", "Duvar")):
        r = api(port, "/api/register", {"username": f"lostest{i}x", "password": "secret12", "nickname": nick})
        users.append((r["token"], r["me"]["id"]))
    victim, clear, blocked = (WS(port, tok) for tok, _ in users)
    vid = users[0][1]
    sid = api(port, "/api/servers", token=users[0][0])
    sid = (sid.get("servers") if isinstance(sid, dict) else sid)[0]["id"]
    for c in (victim, clear, blocked):
        c.send({"t": "lobby.join", "server": sid, "channel": 0})
    time.sleep(0.2)
    clear.send({"t": "room.create", "room": {"name": "los", "mode": "FM_BATTLE", "map": MAP, "mission": "50 kills",
                                             "time": "10 min", "max": 8}})
    time.sleep(0.2)
    room = next(r for r in server.HUB.rooms.values() if r.map == MAP)
    for c in (victim, blocked):
        c.send({"t": "room.join", "id": room.id})
    time.sleep(0.2)
    victim.send({"t": "room.team", "team": "blue"})
    blocked.send({"t": "room.team", "team": "red"})
    time.sleep(0.1)
    for c in (victim, blocked):
        c.send({"t": "room.ready", "ready": True})
    time.sleep(0.1)
    clear.send({"t": "room.start"})
    for c in (victim, clear, blocked):
        c.wait("match.start")
        c.send({"t": "match.enter", "loadout": {"primary": 3041}})
    time.sleep(0.3)
    mt = room.match
    assert mt and mt["map"] == MAP, "match did not start"
    with server.HUB.lock:   # skip the load wait / ready countdown
        mt["startsAt"] = time.time() - 1
    teams = {u: mt["players"][u]["team"] for u in mt["players"]}
    assert teams[vid] != teams[users[1][1]] and teams[vid] != teams[users[2][1]], teams
    for c, pos in ((victim, VICTIM), (clear, CLEAR), (blocked, BLOCKED)):
        c.send({"t": "st", "p": pos, "y": 0, "pi": 0, "k": "human", "f": 0, "w": 3041})
    victim.send({"t": "fx", "k": "fire"})   # ends the spawn protection
    time.sleep(0.3)
    for c in (victim, clear, blocked):
        c.take("hp")

    ok = True
    t0 = time.perf_counter()
    for _ in range(3):
        blocked.send({"t": "hit", "to": vid, "dmg": 60, "w": 3041, "loc": "torso"})
        time.sleep(0.15)
    time.sleep(0.2)
    got = victim.take("hp")
    rej = mt["players"][users[2][1]].get("rejected", 0)
    print(f"duvar arkasindan 3 vurus: hp mesaji {len(got)}, reddedilen {rej}  ->", "OK" if not got and rej == 3 else "HATA")
    ok &= not got and rej == 3
    hp0 = mt["players"][vid]["hp"]
    clear.send({"t": "hit", "to": vid, "dmg": 60, "w": 3041, "loc": "torso"})
    time.sleep(0.3)
    got = victim.take("hp")
    hp = got[-1]["hp"] if got else None
    print(f"acik hattan 1 vurus: hp mesaji {len(got)}, hp {hp0} -> {hp}  ->", "OK" if hp is not None and hp < hp0 else "HATA")
    ok &= hp is not None and hp < hp0
    # keeps shooting through the wall: banned (WALL_BAN), kicked to the login screen, the login refused
    for _ in range(12):
        blocked.send({"t": "hit", "to": vid, "dmg": 60, "w": 3041, "loc": "torso"})
        time.sleep(0.2)
        if any(m.get("t") == "kicked" for m in blocked.msgs):
            break
    kick = blocked.take("kicked")
    banned = bool(kick and kick[-1].get("banned"))
    print(f"israrli duvar vurusu: kicked {kick[-1] if kick else None}  ->", "OK" if banned else "HATA")
    ok &= banned
    try:
        api(port, "/api/login", {"username": "lostest2x", "password": "secret12"})
        err = None
    except urllib.error.HTTPError as e:
        err = (e.code, json.loads(e.read()).get("error"))
    print(f"banli hesap girisi: {err}  ->", "OK" if err and err[0] == 403 else "HATA")
    ok &= bool(err and err[0] == 403)
    with server.db() as con:   # the others are not banned
        others = con.execute("SELECT COUNT(*) FROM users WHERE banned IS NOT NULL AND username != 'lostest2x'").fetchone()[0]
    print(f"diger banli hesap: {others}  ->", "OK" if others == 0 else "HATA")
    ok &= others == 0
    print(f"sure {time.perf_counter() - t0:.2f} s")
    srv.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
