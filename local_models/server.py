# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local MJAI inference for the Zheyou model selector."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from math import exp, isfinite
import os
from pathlib import Path
from queue import Empty, Queue
import re
from shutil import copy2
import subprocess
import sys
from threading import Lock, Thread
from time import perf_counter


ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = ROOT / "models"
ADDRESS = ("127.0.0.1", 25034)
LOCAL_KEY = "zheyou-local-inference"
S42 = "mortal-s42"
EPSILON = "epsilon-prism-3p"
MODEL_GAMES = {S42: "4p", EPSILON: "3p", "native-4p": "4p", "native-3p": "3p"}
NAMES = {S42: "Mortal-S42", EPSILON: "Epsilon-Prism 3P", "native-4p": "Native 4P", "native-3p": "Native 3P"}
LOG = logging.getLogger("local_models")
MORTAL_ACTIONS = tuple(f"dahai:{tile}" for tile in (
    [f"{number}{suit}" for suit in "mps" for number in range(1, 10)]
    + list("ESWNPFC") + ["5mr", "5pr", "5sr"]
)) + ("reach", "chi_low", "chi_low", "chi_low", "pon", "kan", "hora", "ryukyoku", "none")
COARSE_ACTIONS = {"chi": "chi_low", "ankan": "kan", "kakan": "kan", "daiminkan": "kan", "kita": "nukidora"}


def action_label(reaction):
    kind = reaction["type"]
    if kind == "dahai":
        return f"dahai:{reaction['pai']}"
    return COARSE_ACTIONS.get(kind, kind)


def top_candidates(reaction, scores):
    chosen = action_label(reaction)
    scores = {label: score for label, score in scores.items() if isfinite(score)}
    if chosen not in scores:
        return []
    best = max(scores.values())
    weights = {label: exp(score - best) for label, score in scores.items()}
    total = sum(weights.values())
    alternatives = sorted((label for label in scores if label != chosen), key=scores.get, reverse=True)
    return [{"action": label, "prob": weights[label] / total} for label in [chosen, *alternatives[:2]]]


class Mortal:
    def __init__(self):
        sys.path.insert(0, str(MODEL_ROOT / S42))
        LOG.info("Loading Mortal CPU runtime")
        import torch
        import inference

        torch.set_num_threads(2)
        LOG.info("Loading Mortal weights")
        self.engine = inference.load_engine("cpu")
        self.session = inference.Session
        LOG.info("Warming Mortal with a local test hand")
        self.react(0, inference.synthetic_events())

    def react(self, seat, events):
        session = self.session(self.engine, seat)
        for event in events[:-1]:
            session.bot.react(json.dumps(event), can_act=False)
        reaction = session.react(events[-1]) or {"type": "none"}
        meta = reaction.pop("meta", None) or {}
        indices = [index for index in range(len(MORTAL_ACTIONS)) if meta.get("mask_bits", 0) & (1 << index)]
        q_values = meta.get("q_values") or []
        scores = {}
        if len(indices) == len(q_values):
            for index, score in zip(indices, q_values):
                label = MORTAL_ACTIONS[index]
                scores[label] = max(score, scores.get(label, score))
        chosen = action_label(reaction)
        if chosen != "hora" and chosen in scores and scores.get("hora", float("-inf")) > scores[chosen]:
            # Libriichi can veto a model-selected win that fails its scoring guard.
            del scores["hora"]
        if reaction["type"] == "reach" and not reaction.get("pai"):
            discard = session.react(reaction)
            if not discard or discard.get("type") != "dahai":
                raise ValueError("Mortal did not choose a riichi discard")
            reaction["pai"] = discard["pai"]
        return reaction, top_candidates(reaction, scores)


class WorkerProcess:
    def __init__(self, model, args, directory, env, output):
        self.model = model
        self.process = subprocess.Popen(
            [str(Path(sys.executable).with_name("python.exe")), "-B", "-u", *args],
            cwd=directory,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=output,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.lines = Queue()
        Thread(target=self.read, daemon=True).start()
        try:
            line = self.receive(40)
            if not line or json.loads(line) != {"ready": True}:
                raise RuntimeError(f"{model} did not start")
        except Exception:
            self.close()
            raise

    def read(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def receive(self, timeout):
        try:
            line = self.lines.get(timeout=timeout)
        except Empty as error:
            raise TimeoutError(f"{self.model} worker did not answer") from error
        if line is None:
            raise ConnectionError(f"{self.model} worker exited")
        return line

    def exchange(self, seat, events):
        try:
            self.process.stdin.write(json.dumps({"player_id": seat, "events": events}) + "\n")
            self.process.stdin.flush()
        except OSError as error:
            # Windows can report a dead child pipe as EINVAL instead of EPIPE.
            raise ConnectionError(f"{self.model} worker pipe closed") from error
        line = self.receive(2)
        reply = json.loads(line)
        if "error" in reply:
            raise ValueError(reply["error"])
        return reply

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


class Epsilon(WorkerProcess):
    def __init__(self, output):
        directory = MODEL_ROOT / "epsilon-3p"
        jar = directory / "epsilon-prism-3p-1.0-SNAPSHOT-all.jar"
        env = dict(os.environ, PYTORCH_FLAVOR="cpu", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        cache = ROOT / "runtime" / "djl"
        if cache.is_dir():
            env.update(DJL_CACHE_DIR=str(cache), ENGINE_CACHE_DIR=str(cache))
        super().__init__(EPSILON, [str(Path(__file__).with_name("epsilon_worker.py")), str(jar)], directory, env, output)
        try:
            self.react(0, epsilon_opening())
        except Exception:
            self.close()
            raise

    def react(self, seat, events):
        reply = self.exchange(seat, events)
        reaction = reply["reaction"]
        return reaction, top_candidates(reaction, reply["scores"])


class MortalWorker(WorkerProcess):
    def __init__(self, output):
        env = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        super().__init__(S42, [str(Path(__file__).resolve()), "--mortal-worker"], ROOT, env, output)

    def react(self, seat, events):
        reply = self.exchange(seat, events)
        return reply["reaction"], reply["candidates"]


def run_mortal_worker():
    # Load the packaged PyTorch and its native libraries on the worker's main thread.
    engine = Mortal()
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            reaction, candidates = engine.react(request["player_id"], request["events"])
            reply = {"reaction": reaction, "candidates": candidates}
        except Exception as error:
            reply = {"error": str(error)}
        print(json.dumps(reply, allow_nan=False), flush=True)


def epsilon_opening():
    return [
        {"type": "start_game", "id": 0, "num_players": 3},
        {"type": "start_kyoku", "bakaze": "E", "dora_marker": "1m", "kyoku": 1, "honba": 0,
         "kyotaku": 0, "oya": 0, "scores": [35000] * 3,
         "tehais": [["1p", "3p", "8p", "2s", "2s", "4s", "5sr", "6s", "7s", "7s", "E", "S", "F"],
                    ["?"] * 13, ["?"] * 13]},
        {"type": "tsumo", "actor": 0, "pai": "N"},
    ]


class Models:
    def __init__(self, java_log):
        self.java_log = java_log
        self.factories = {S42: MortalWorker, EPSILON: Epsilon}
        self.locks = {S42: Lock(), EPSILON: Lock()}
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.workers = {model: self.pool.submit(self.load, model, factory, java_log)
                        for model, factory in self.factories.items()}

    @staticmethod
    def load(model, factory, *args):
        try:
            instance = factory(*args)
        except Exception:
            LOG.exception("%s could not start", model)
            raise
        LOG.info("%s ready", model)
        return instance

    def available(self):
        return [model for model in MODEL_GAMES if model not in self.workers or (
            self.workers[model].done() and self.workers[model].exception() is None
        )]

    def react(self, model, seat, events):
        if model not in self.workers:
            # A successful response without a decision lets the client use its built-in result.
            return None, []
        with self.locks[model]:
            worker = self.workers[model]
            if not worker.done() or worker.exception() is not None:
                raise RuntimeError(f"{NAMES[model]} is not ready. See logs/local-models.log")
            instance = worker.result()
            try:
                return instance.react(seat, events)
            except (ConnectionError, TimeoutError) as error:
                LOG.warning("Restarting %s after transport failure: %s", model, error)
                self.workers[model] = self.pool.submit(self.restart, model, instance)
                raise

    def restart(self, model, instance):
        instance.close()
        return self.load(model, self.factories[model], self.java_log)

    def close(self):
        self.pool.shutdown()
        for worker in self.workers.values():
            if worker.exception() is None:
                worker.result().close()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(8)
        super().setup()

    def send_json(self, status, data):
        payload = json.dumps(data, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        if self.headers.get("Authorization") == "Bearer " + LOCAL_KEY:
            return True
        self.send_json(401, {"error": "Invalid local inference key"})
        return False

    def do_GET(self):
        if self.path == "/readyz":
            ready = {EPSILON, S42} <= set(self.server.models.available())
            self.send_json(200 if ready else 503, {"ready": ready})
        elif self.path == "/healthz":
            self.send_json(200, {"status": "ok", "queue_depth": 0})
        elif self.path in ("/v3/models", "/v3/key"):
            if not self.authorized():
                return
            if self.path == "/v3/models":
                self.send_json(200, {"models": [
                    {"id": model, "game": MODEL_GAMES[model], "desc": NAMES[model]}
                    for model in self.server.models.available()
                ]})
            else:
                self.send_json(200, {"plan": "local"})
        else:
            self.send_json(404, {"error": "Route not found"})

    def do_POST(self):
        if self.path != "/v3/react":
            self.send_json(404, {"error": "Route not found"})
            return
        if not self.authorized():
            return
        try:
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 1_000_000:
                raise ValueError("Invalid MJAI request size")
            request = json.loads(self.rfile.read(length))
            seat, events = request["player_id"], request["events"]
            start = next(event for event in reversed(events) if event["type"] == "start_kyoku")
            model = request.get("model") or f"native-{len(start['scores'])}p"
            if MODEL_GAMES.get(model) == "3p" and start["scores"][3:] == [0]:
                hands = start["tehais"]
                if len(hands) == 4 and hands[3] == ["?"] * 13:
                    # AkagiMS pads sanma to a four-seat cloud request. Epsilon expects three.
                    start["scores"] = start["scores"][:3]
                    start["tehais"] = hands[:3]
                    for event in events:
                        if event["type"] == "start_game" and event.get("names", [])[3:] == [""]:
                            event["names"] = event["names"][:3]
            count = len(start["scores"])
            game = f"{count}p"
            if MODEL_GAMES.get(model) != game or type(seat) is not int or not 0 <= seat < count:
                raise ValueError("Model or seat does not match the table")
        except (KeyError, TypeError, ValueError, StopIteration) as error:
            self.send_json(400, {"error": str(error) or "Missing start_kyoku"})
            return

        begin = perf_counter()
        try:
            reaction, candidates = self.server.models.react(model, seat, events)
        except Exception as error:
            LOG.warning("%s failed for seat %d: %s", model, seat, error)
            self.send_json(503, {"error": f"{NAMES[model]}: {error}"})
            return

        LOG.info("%s seat=%d events=%d action=%s %.1fms", model, seat, len(events),
                 reaction["type"] if reaction else "native", (perf_counter() - begin) * 1000)
        self.send_json(200, {"reaction": reaction, "model": model, "candidates": candidates})

    def log_message(self, *_):
        pass


def run_client(logs):
    executable = ROOT / "ZheyouClient.exe"
    env = os.environ.copy()
    env.setdefault("RUST_BACKTRACE", "1")
    try:
        with (logs / "zheyou-process.log").open("ab") as output, subprocess.Popen(
            [str(executable)], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
        ) as client:
            LOG.info("Zheyou client started pid=%d", client.pid)
            status = client.wait()
    except OSError:
        LOG.exception("Could not launch the Zheyou client")
        raise

    LOG.log(logging.ERROR if status else logging.INFO,
            "Zheyou client exited pid=%d status=%d (0x%08X)", client.pid, status, status & 0xFFFFFFFF)
    if status:
        raise subprocess.CalledProcessError(status, client.args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true", help="launch the Zheyou client")
    parser.add_argument("--managed", action="store_true", help="exit when the launcher closes its input")
    parser.add_argument("--mortal-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mortal_worker:
        run_mortal_worker()
        return

    if (ROOT / "runtime" / "python").is_dir():
        config_dir = ROOT / "configs"
        config_dir.mkdir(exist_ok=True)
        for name in ("config.toml", "delay.lua"):
            if not (config_dir / name).exists():
                copy2(ROOT / "defaults" / name, config_dir / name)
        config = config_dir / "config.toml"
        source = config.read_text(encoding="utf-8")
        pinned = re.sub(r'(?ms)^\[bot\.api\][^\n]*\n(.*?)(?=^\[|\Z)', lambda match:
            re.sub(r'(?m)^(base_url|key|proxy|proxy_enabled)\s*=.*\n?', '', match[0]).replace('[bot.api]\n',
                '[bot.api]\nbase_url = "http://127.0.0.1:25034"\nkey = "zheyou-local-inference"\nproxy = ""\nproxy_enabled = false\n', 1), source)
        if pinned != source:
            pending = config.with_suffix(".tmp")
            pending.write_text(pinned, encoding="utf-8")
            pending.replace(config)

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(filename=logs / "local-models.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    with ThreadingHTTPServer(ADDRESS, Handler) as server, (logs / "epsilon.log").open("ab") as java_log:
        server.models = Models(java_log)
        LOG.info("Listening on http://%s:%d", *ADDRESS)
        try:
            if args.launch:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    run_client(logs)
                finally:
                    server.shutdown()
                    thread.join()
            elif args.managed:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    sys.stdin.readline()
                finally:
                    server.shutdown()
                    thread.join()
            else:
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.models.close()


if __name__ == "__main__":
    main()
