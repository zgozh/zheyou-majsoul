# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run Mortal S42.8k with the bundled upstream model and observation encoder."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'runtime' / 'mortal'))


def load_engine(device: str = 'cpu'):
    import torch
    from engine import MortalEngine
    from model import Brain, DQN

    identity = json.loads((ROOT / 'model-identity.json').read_text())
    checkpoint = ROOT / identity['file']
    with checkpoint.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if digest != identity['sha256']:
        raise ValueError('Checkpoint checksum mismatch')
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if set(state) != {'mortal', 'current_dqn'}:
        raise ValueError('Unexpected checkpoint fields')
    target = torch.device(device)
    if target.type not in ('cpu', 'cuda'):
        raise ValueError('Supported devices: cpu and cuda')
    brain = Brain(version=4, conv_channels=192, num_blocks=40).eval()
    dqn = DQN(version=4).eval()
    brain.load_state_dict(state['mortal'], strict=True)
    dqn.load_state_dict(state['current_dqn'], strict=True)
    return MortalEngine(
        brain, dqn, is_oracle=False, version=4, device=target,
        enable_amp=target.type == 'cuda', enable_quick_eval=False,
        enable_rule_based_agari_guard=True, name='S42.8k',
        boltzmann_epsilon=0,
    )


class Session:
    """Maintain one perspective for one game; feed every observed mjai event."""
    def __init__(self, engine, seat: int):
        from libriichi.mjai import Bot
        if seat not in range(4):
            raise ValueError('Seat must be in 0..3')
        self.bot = Bot(engine, seat)

    def react(self, event: dict | str) -> dict | None:
        raw = self.bot.react(event if isinstance(event, str) else json.dumps(event))
        return None if raw is None else json.loads(raw)


def synthetic_events(seat: int = 0, draw: str = '1p') -> list[dict]:
    hands = [['?'] * 13 for _ in range(4)]
    hands[seat] = ['2m', '3m', '4m', '5p', '6p', '7p', '2s', '3s', '4s', '7s', '8s', 'E', 'E']
    return [
        {'type': 'start_game', 'names': ['p0', 'p1', 'p2', 'p3']},
        {'type': 'start_kyoku', 'bakaze': 'E', 'dora_marker': '1m',
         'kyoku': 1, 'honba': 0, 'kyotaku': 0, 'oya': seat,
         'scores': [25000] * 4, 'tehais': hands},
        {'type': 'tsumo', 'actor': seat, 'pai': draw},
    ]


def smoke(engine) -> dict:
    import numpy as np
    from libriichi.consts import obs_shape, ACTION_SPACE
    if tuple(obs_shape(4)) != (1012, 34) or ACTION_SPACE != 46:
        raise ValueError('Observation/action contract mismatch')
    obs = np.zeros((1012, 34), dtype=np.float32)
    masks = np.zeros((2, 46), dtype=bool)
    masks[0, 45] = True
    masks[1, [0, 8, 17, 26, 33, 45]] = True
    actions, values, returned, greedy = engine.react_batch([obs, obs], list(masks), None)
    values = np.asarray(values)
    if not np.isfinite(values[masks]).all() or not np.isneginf(values[~masks]).all():
        raise ValueError('Q-value contract failed')
    if actions[0] != 45 or not all(masks[i, a] for i, a in enumerate(actions)):
        raise ValueError('Illegal action')
    if not np.array_equal(returned, masks) or not all(greedy):
        raise ValueError('Mask or greedy contract failed')
    reactions = []
    for seat in range(4):
        for draw in ('1p', '9s'):
            session = Session(engine, seat)
            reaction = None
            for event in synthetic_events(seat, draw):
                reaction = session.react(event)
            if reaction is None or reaction.get('actor') != seat:
                raise ValueError('Missing or incorrect mjai reaction')
            if draw == '9s' and reaction['type'] != 'hora':
                raise ValueError('Winning-hand smoke failed')
            if draw == '1p' and reaction['type'] not in ('dahai', 'reach'):
                raise ValueError('Discard-hand smoke failed')
            result = {'seat': seat, 'draw': draw, 'type': reaction['type']}
            if reaction['type'] == 'reach':
                followup = session.react(reaction)
                if followup is None or followup['type'] != 'dahai':
                    raise ValueError('Riichi follow-up discard failed')
                result['followup'] = followup['type']
            reactions.append(result)
    return {'result': 'pass', 'tensor_batches': 2, 'synthetic_mjai_cases': reactions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='cpu', choices=['cpu', 'cuda'])
    parser.add_argument('--seat', type=int, choices=range(4), default=0)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    engine = load_engine(args.device)
    if args.smoke:
        print(json.dumps(smoke(engine), indent=2))
        return
    session = Session(engine, args.seat)
    for line in sys.stdin:
        reaction = session.react(json.loads(line))
        if reaction is not None:
            print(json.dumps(reaction), flush=True)


if __name__ == '__main__':
    main()
