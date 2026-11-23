"""Exercise the Zheyou WebViews, model selector and clicks against a local table."""

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from urllib.request import Request, urlopen

from websocket import create_connection
from websockets.sync.server import serve

from server import ADDRESS, EPSILON, LOCAL_KEY, ROOT, S42, epsilon_opening


def wait(check, seconds=20):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        try:
            if result := check():
                return result
        except OSError:
            pass
        sleep(0.1)
    raise AssertionError(f"Timed out waiting for {check.__name__}")


def varint(number):
    result = bytearray()
    while number >= 128:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def number(field, value):
    return varint(field << 3) + varint(value)


def blob(field, value):
    if isinstance(value, str):
        value = value.encode()
    return varint((field << 3) | 2) + varint(len(value)) + value


def wrapper(name, payload):
    return blob(1, name) + blob(2, payload)


def action_frame(step, name, payload):
    key = b"\x84\x5e\x4e\x42\x39\xa2\x1f\x60\x1c"
    coded = bytes(x ^ (((23 ^ len(payload)) + 5 * i + key[i % len(key)]) & 255)
                  for i, x in enumerate(payload))
    return b"\x01" + wrapper(".lq.ActionPrototype", number(1, step) + blob(2, name) + blob(3, coded))


def opening(handsize, deck, operation_type):
    auth = b"\x02\x01\x00" + wrapper(".lq.FastTest.authGame", number(1, 81) + blob(3, f"offline-{handsize}"))
    seats = b"".join(number(3, i) for i in range(81, 81 + handsize))
    accepted = b"\x03\x01\x00" + wrapper("", seats + number(4, 1))
    score = 35000 if handsize == 3 else 25000
    operation = blob(2, number(1, 1)) + number(4, 20000) + number(5, 5000)
    if operation_type != 1:
        operation += blob(2, number(1, operation_type) + blob(2, deck[-1]))
    board = (b"".join(blob(4, tile) for tile in deck) + number(6, score) * handsize
             + blob(7, operation) + number(13, 54 if handsize == 3 else 69) + blob(14, "1m"))
    return auth, accepted, action_frame(1, "ActionNewRound", board)


def operation_request(tile, operation_type):
    return b"\x02\x02\x00" + wrapper(".lq.FastTest.inputOperation", number(1, operation_type) + blob(3, tile))


class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/board":
            self.reply(json.dumps(self.server.board).encode(), "application/json")
            return
        page = b'''<!doctype html><meta charset="utf-8"><title>Offline table</title>
<style>html,body {margin:0;overflow:hidden} canvas {display:block;width:100vw;height:100vh;background:#07564d}</style>
<canvas width="1200" height="850"></canvas><script>
async function poll(){
  const board=await fetch('/board').then(r=>r.json());
  if(!board){setTimeout(poll,100);return;}
  const ws=new WebSocket('ws://127.0.0.1:'+board.port+'/gateway');
  ws.binaryType='arraybuffer';
  ws.onopen=()=>ws.send(new Uint8Array(board.auth)); window.gateway=ws;
  let ready=false;
  let reachAt=null;
  let selectedTooSoon=false;
  ws.onmessage=event=>{if(new Uint8Array(event.data)[0]===1)ready=true;};
  const canvas=document.querySelector('canvas');
  window.addEventListener('pointerdown',e=>{
    if(board.action!=='reach'||reachAt===null)return;
    const rect=canvas.getBoundingClientRect();
    const y=(e.clientY-rect.top)*9/rect.height;
    selectedTooSoon=y>8&&e.timeStamp-reachAt<650;
  },true);
  window.addEventListener('pointerup',e=>{
    if(!ready||!e.isTrusted)return;
    const rect=canvas.getBoundingClientRect();
    const x=(e.clientX-rect.left)*16/rect.width, y=(e.clientY-rect.top)*9/rect.height;
    const index=Math.round((x-2.23125)/0.790625);
    fetch('/pointer',{method:'POST',body:JSON.stringify({x,y,index,trusted:e.isTrusted,target:e.target?.nodeName,rect:rect.toJSON()})});
    if(Math.abs(y-7)<0.35){
      if(board.action==='reach'){reachAt=e.timeStamp;return;}
      if(board.action==='kita'){
        ready=false;
        ws.send(new Uint8Array(board.requests[0]));
      }
      return;
    }
    if(Math.abs(y-8.3625)>0.5||!board.requests[index]||board.action==='kita'||(board.action==='reach'&&(reachAt===null||selectedTooSoon)))return;
    ready=false;
    ws.send(new Uint8Array(board.requests[index]));
  },true);
}
poll();
</script>'''
        self.reply(page, "text/html")

    def do_POST(self):
        self.server.pointers.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.reply(b"ok", "text/plain")

    def reply(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class DevTools:
    def __init__(self, target):
        self.ws = create_connection(target["webSocketDebuggerUrl"], suppress_origin=True, timeout=6)
        self.id = 0

    def evaluate(self, expression):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": "Runtime.evaluate", "params": {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        }}))
        while True:
            result = json.loads(self.ws.recv())
            if result.get("id") == self.id:
                value = result["result"]
                assert "exceptionDetails" not in value, value.get("exceptionDetails")
                return value["result"].get("value")


def available_models():
    req = Request(f"http://{ADDRESS[0]}:{ADDRESS[1]}/v3/models", headers={"Authorization": f"Bearer {LOCAL_KEY}"})
    with urlopen(req, timeout=1) as reply:
        return {model["id"] for model in json.load(reply)["models"]}


def react_model(model, seat, events):
    body = json.dumps({"model": model, "player_id": seat, "events": events}).encode()
    req = Request(f"http://{ADDRESS[0]}:{ADDRESS[1]}/v3/react", body,
                  headers={"Authorization": f"Bearer {LOCAL_KEY}"})
    with urlopen(req, timeout=3) as reply:
        result = json.load(reply)
    assert result["model"] == model, result
    return result


def react_epsilon(seat, events):
    return react_model(EPSILON, seat, events)["reaction"]


def verify_ranked_recommendations():
    start, round_start, draw = epsilon_opening()
    for model in (EPSILON, S42):
        hands = round_start["tehais"] + ([["?"] * 13] if model == S42 else [])
        scores = [25000] * 4 if model == S42 else [35000] * 3
        events = [dict(start, num_players=len(scores)), dict(round_start, scores=scores, tehais=hands), draw]
        reply = react_model(model, 0, events)
        reaction = reply["reaction"]
        candidates = reply.get("candidates", [])
        assert len(candidates) == 3, (model, candidates)
        assert len({item["action"] for item in candidates}) == 3, candidates
        chosen = {"kita": "nukidora"}.get(reaction["type"], reaction["type"])
        if chosen == "dahai":
            chosen += ":" + reaction["pai"]
        assert candidates[0]["action"] == chosen, (reaction, candidates)
        weights = [item["prob"] for item in candidates]
        assert all(0 <= weight <= 1 for weight in weights) and 0 < sum(weights) <= 1.000001, weights
        assert weights[1] >= weights[2], weights
        assert all(item["action"].split(":", 1)[1] in hands[0] + [draw["pai"]]
                   for item in candidates if item["action"].startswith("dahai:")), candidates
        print(model, "returned three distinct legal recommendations", flush=True)


def verify_first_discard_replay():
    for seat, pai, wind, kyoku in [(0, "1p", "E", 1), (2, "9m", "S", 3)]:
        start_game, start_kyoku, _ = epsilon_opening()
        hand = ["2p", "3p", "8p", "2s", "2s", "4s", "5sr", "6s", "7s", "7s", "E", "S", "F"]
        hands = [["?"] * 13 for _ in range(4)]
        hands[seat] = hand
        start_game.update(id=seat)
        start_kyoku.update(tehais=hands, scores=[35000, 35000, 35000, 0], oya=seat, bakaze=wind, kyoku=kyoku)
        events = [start_game, start_kyoku, {"type": "tsumo", "actor": seat, "pai": pai},
                  {"type": "dahai", "actor": seat, "pai": pai, "tsumogiri": False}]
        for other, discard in [((seat + 1) % 3, "W"), ((seat + 2) % 3, "4p")]:
            events.extend([{"type": "tsumo", "actor": other, "pai": "?"},
                           {"type": "dahai", "actor": other, "pai": discard, "tsumogiri": True}])
        events.append({"type": "tsumo", "actor": seat, "pai": "9p"})
        reaction = react_epsilon(seat, events)
        assert reaction["actor"] == seat, reaction
        print("Epsilon replayed dealer's first discard", pai, "and returned", reaction["type"], flush=True)


def verify_delayed_kan_dora(react=react_epsilon):
    start_game, start_kyoku, _ = epsilon_opening()
    start_game["id"] = 2
    start_kyoku["tehais"] = [["?"] * 13 for _ in range(2)] + [
        "1m 9m 2p 3p 4p 6p 8p 2s 3s 6s 8s 9s E".split(),
    ]

    def draw(actor, tile="?"):
        return {"type": "tsumo", "actor": actor, "pai": tile}

    def discard(actor, tile):
        return {"type": "dahai", "actor": actor, "pai": tile, "tsumogiri": False}

    # Dealer adds to two earlier pons, then the client sends both markers together.
    first = {"type": "dora", "dora_marker": "5p"}
    second = {"type": "dora", "dora_marker": "4s"}
    history = [start_game, start_kyoku, draw(0), discard(0, "9m")]
    for called, next_discard in [("1s", "C"), ("W", "3p")]:
        history.extend([draw(1), discard(1, called),
                        {"type": "pon", "actor": 0, "target": 1, "pai": called, "consumed": [called] * 2},
                        discard(0, next_discard)])
    history.extend([draw(1), discard(1, "P"), draw(2, "E"), discard(2, "1m"), draw(0),
                    {"type": "kakan", "actor": 0, "pai": "1s", "consumed": ["1s"] * 3}, draw(0),
                    {"type": "kakan", "actor": 0, "pai": "W", "consumed": ["W"] * 3}])
    tail = [discard(0, "5sr"), draw(1), discard(1, "F"), draw(2, "7s")]
    expected = react(2, history + [first, draw(0), second] + tail)
    assert expected["actor"] == 2 and expected["type"] in ("dahai", "reach"), expected
    assert react(2, history + [draw(0), first, second] + tail) == expected

    for action, markers in [({"type": "kita", "actor": 0, "pai": "N"}, [first]),
                            ({"type": "ankan", "actor": 0, "consumed": ["7p"] * 4}, [first, second])]:
        chain = history[:-1] + [action]
        expected = react(2, chain + markers + [draw(0)] + tail)
        assert react(2, chain + [draw(0)] + markers + tail) == expected, action
    print("Epsilon accepted batched dora after successive added kans, north extraction and closed kan", flush=True)


def test_table(page, page_url, players, deck, model, action="dahai"):
    operation_type = {"dahai": 1, "reach": 7, "kita": 11}[action]
    auth, accepted, notify = opening(players, deck, operation_type)
    page.board = None
    page.pointers = []
    moves = []
    sorted_deck = sorted(deck, key=lambda tile: ("mpsz".index(tile[1]), 4.5 if tile[0] == "0" else int(tile[0])))
    allowed_tiles = ["4z"] if action == "kita" else sorted_deck
    requests = {operation_request(tile, operation_type): tile for tile in allowed_tiles}

    def game(peer):
        assert peer.recv(timeout=8) == auth
        peer.send(accepted)
        peer.send(notify)
        tile = requests[peer.recv(timeout=15)]
        peer.send(b"\x03\x02\x00" + wrapper("", b""))
        if action == "kita":
            peer.send(action_frame(2, "ActionBaBei", number(1, 0) + number(9, 1)))
        else:
            peer.send(action_frame(2, "ActionDiscardTile", blob(2, tile) + number(3, int(action == "reach"))))
        moves.append(tile)

    with serve(game, "127.0.0.1", 0) as gateway, TemporaryDirectory(prefix="zheyou-offline-", ignore_cleanup_errors=True) as temp:
        Thread(target=gateway.serve_forever, daemon=True).start()
        app = Path(temp)
        exe = app / "ZheyouClient.exe"
        pending = ROOT / "ZheyouClient.next.exe"
        shutil.copy2(pending if pending.is_file() else ROOT / "ZheyouClient.exe", exe)
        (app / "configs").mkdir()
        cfg = (ROOT / "defaults" / "config.toml").read_text(encoding="utf-8")
        cfg = re.sub(r'(?m)^start_url\s*=.*$', f'start_url = "{page_url}"', cfg)
        cfg = re.sub(r'(?m)^base_url\s*=.*$', 'base_url = "http://127.0.0.1:25034"', cfg)
        cfg = re.sub(r'(?m)^key\s*=.*$', 'key = ""', cfg)
        cfg = re.sub(r'(?m)^model_([34]p)\s*=.*$', r'model_\1 = ""', cfg)
        cfg = re.sub(r'(\[bot\.api\]\s*)enabled\s*=\s*(true|false)', r'\1enabled = false', cfg)
        cfg = re.sub(r'(\[autoplay\]\s*)enabled\s*=\s*(true|false)', r'\1enabled = true', cfg)
        cfg = re.sub(r'(\[autoplay\.full_auto\]\s*)enabled\s*=\s*(true|false)', r'\1enabled = false', cfg)
        (app / "configs" / "config.toml").write_text(cfg, encoding="utf-8")
        shutil.copy2(ROOT / "defaults" / "delay.lua", app / "configs" / "delay.lua")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            debug_port = sock.getsockname()[1]
        env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=(
            f'--remote-debugging-port={debug_port} --no-proxy-server '
            '--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"'
        ))
        process = subprocess.Popen([str(exe)], cwd=app, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        pages = []

        def targets():
            with urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=1) as reply:
                return json.load(reply)

        def target(match):
            return next((item for item in targets() if match in item["url"]), None)

        def reactions():
            for log in (app / "logs").rglob("inspector.jsonl"):
                for line in log.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("kind") == "bot_reaction" and event.get("action", {}).get("type") == action:
                        return event
            return None

        def confirmed():
            for log in (app / "logs").rglob("all.log"):
                lines = log.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if "turn finished" in line and "outcome=Accepted" in line:
                        return line
            return None

        try:
            ui = DevTools(wait(lambda: target("tauri.localhost")))
            pages.append(ui)
            wait(lambda: ui.evaluate('!!document.querySelector("[data-local-model-selector]")'))
            ui.evaluate('document.querySelector("[data-local-model-selector]").click()')
            wait(lambda: ui.evaluate('document.querySelectorAll("[data-model-mode]").length===2'))

            def set_model(mode, value):
                ui.evaluate('(() => {const s=document.querySelector(`[data-model-mode="' + mode + '"]`);'
                            f's.value={json.dumps(value)};s.dispatchEvent(new Event("change",{{bubbles:true}}));' + '})()')

            def selected():
                return ui.evaluate('Object.fromEntries([...document.querySelectorAll("[data-model-mode]")].map(s=>[s.dataset.modelMode,s.value]))')

            chosen_3p = EPSILON if model in (EPSILON, S42) else "native-3p"
            chosen_4p = S42 if model else "native-4p"
            for mode, value in (("3p", chosen_3p), ("4p", chosen_4p)):
                if selected().get(mode) != value:
                    set_model(mode, value)
                    wait(lambda: selected().get(mode) == value)
            api = ui.evaluate('window.__TAURI_INTERNALS__.invoke("get_config").then(c=>[c.bot.api.base_url,c.bot.api.enabled,c.bot.api.model_3p,c.bot.api.model_4p])')
            assert api == ["http://127.0.0.1:25034", model is not None,
                           chosen_3p if model else "", chosen_4p if model else ""], api
            ui.evaluate('document.querySelector("[role=dialog] button").click()')
            wait(lambda: not selected())
            if model == EPSILON:
                ui.evaluate('document.querySelector("[data-local-inference-reconnect]").click()')
                wait(lambda: ui.evaluate('window.__TAURI_INTERNALS__.invoke("get_config")'
                                         '.then(c=>c.bot.api.base_url==="http://127.0.0.1:25034/"'
                                         '&& c.bot.api.model_3p==="epsilon-prism-3p")'))
                wait(lambda: ui.evaluate('!!document.querySelector("[data-local-reconnect-status]")?.textContent'))
            offset = (ROOT / "logs" / "local-models.log").stat().st_size
            page.board = {"port": gateway.socket.getsockname()[1], "auth": list(auth),
                          "requests": [list(operation_request(tile, operation_type)) for tile in allowed_tiles],
                          "action": action}
            result = wait(reactions)
            note = wait(lambda: ui.evaluate('document.querySelector("[data-recommendation-reason]")?.textContent'))
            expected_note = {"dahai": r"(?:向听|听牌)", "reach": "立直本身", "kita": "拔北宝牌"}[action]
            assert re.search(expected_note, note), note
            click = wait(lambda: moves and moves[0])
            new_log = (ROOT / "logs" / "local-models.log").read_bytes()[offset:].decode()
            if model:
                action_type = "native" if model.startswith("native-") else action
                assert f"{model} seat=0" in new_log and f"action={action_type}" in new_log, new_log
            else:
                assert not new_log, new_log
            translated = {f"{i}z": honor for i, honor in enumerate("ESWNPFC", 1)}
            translated.update({"0p": "5pr", "0s": "5sr", "0m": "5mr"})
            assert result["action"]["pai"] == translated.get(click, click), (result["action"], click)
            title = result["meta"]["show"]["title"]
            if model in (EPSILON, S42):
                assert model in title, result
                items = result["meta"]["show"]["items"]
                assert len(items) == 3 and all("prob" in item for item in items), items
                assert items[0]["pais"][0] == result["action"]["pai"], items
                assert wait(lambda: ui.evaluate(
                    '[...document.querySelectorAll("[data-recommendation-preference]")].filter(e=>e.textContent.includes("偏好")).length===3'
                )), items
                overflow = ui.evaluate('''(() => {
                    const card = document.querySelector('[data-recommendation-preference]').closest('section');
                    const rows = [card, ...card.querySelectorAll('header, ol, li')];
                    return rows.filter(row => row.scrollWidth > row.clientWidth + 1)
                        .map(row => [row.tagName, row.clientWidth, row.scrollWidth]);
                })()''')
                assert not overflow, f"Recommendation overflow at the default sidebar width: {overflow}"
                assert ui.evaluate('!document.querySelector("[data-tauri-drag-region] > .pointer-events-none.absolute.inset-0")')
            else:
                assert not any(external in title for external in (EPSILON, S42)), result
            outcome = wait(confirmed, seconds=6)
            elapsed = int(re.search(r"elapsed_ms=(\d+)", outcome)[1])
            assert "attempts=1 " in outcome and elapsed < 5000, outcome
            print(model or "native (HTTP off)", result["action"], "table confirmed", click, f"{elapsed} ms", flush=True)

            ui.evaluate('document.querySelector("[data-local-model-selector]").click()')
            wait(selected)
            for mode, value in (("3p", "native-3p"), ("4p", "native-4p")):
                if selected().get(mode) != value:
                    set_model(mode, value)
                    wait(lambda: selected().get(mode) == value)
            assert ui.evaluate('window.__TAURI_INTERNALS__.invoke("get_config").then(c=>!c.bot.api.enabled)')
            print("Native selected in both slots and HTTP disabled", flush=True)
        except Exception:
            print("Mock page pointers", page.pointers, flush=True)
            for log in (app / "logs").rglob("*.log"):
                if log.name in ("all.log", "bot.log"):
                    print(f"{log.name}:\n" + "\n".join(log.read_text(encoding="utf-8").splitlines()[-18:]))
            raise
        finally:
            for page in pages:
                page.ws.close()
            process.terminate()
            process.wait(timeout=8)
            sleep(1)


def main():
    wait(lambda: {EPSILON, S42} <= available_models())
    verify_ranked_recommendations()
    verify_first_discard_replay()
    verify_delayed_kan_dora()
    with ThreadingHTTPServer(("127.0.0.1", 0), Page) as page:
        page.board = None
        Thread(target=page.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{page.server_port}/offline"
        try:
            four = "2m 4m 7m 1p 3p 7p 8p 1s 4s 6s 1z 2z 5z 9m".split()
            three = "1p 3p 8p 2s 2s 4s 0s 6s 7s 7s 1z 2z 6z 9p".split()
            test_table(page, url, 4, four, S42)
            test_table(page, url, 3, three, EPSILON)
            test_table(page, url, 3, three, "native-3p")
            test_table(page, url, 4, four, None)
            test_table(page, url, 4, "2m 3m 4m 5p 6p 7p 2s 3s 4s 7s 8s 1z 1z 1p".split(), S42, "reach")
            test_table(page, url, 3, [*three[:-1], "4z"], EPSILON, "kita")
        finally:
            page.shutdown()


if __name__ == "__main__":
    main()
