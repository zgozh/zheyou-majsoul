import pathlib
import struct
import tomllib
import unittest

import brotli

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_default_config_uses_local_models_and_keeps_tuned_values(self):
        state = tomllib.loads((ROOT / 'defaults' / 'config.toml').read_text(encoding='utf-8'))
        api = state['bot']['api']
        self.assertEqual((api['enabled'], api['base_url'], api['model_3p'], api['model_4p']),
                         (True, 'http://127.0.0.1:25034', 'epsilon-prism-3p', 'mortal-s42'))
        self.assertFalse(api['proxy_enabled'])
        self.assertEqual(state['autoplay']['majsoul']['hover_delay_ms'], 300)
        self.assertEqual(state['autoplay']['majsoul']['pre_click_delay_max_ms'], 3000)
        self.assertEqual(state['game']['panel_width'], 220)

    def test_bundle_guards_inference_and_omits_paid_settings(self):
        package = (ROOT / 'ZheyouClient.exe').read_bytes()
        size = struct.unpack_from('<Q', package, 0x12CFB98)[0]
        ui = brotli.decompress(package[0x1122A59:0x1122A59 + size]).decode('utf-8')
        self.assertFalse('https://mjapi.shinkuan.me' in ui, 'legacy paid URL in UI')
        self.assertFalse(b'https://mjapi.shinkuan.me' in package, 'legacy paid default in EXE')
        self.assertIn('function zheyouLocalApi', ui)
        for legacy in ('function $D(', 'function U9(', 'native_api_redeem', 'qC(KC)',
                       'https://discord.gg/', 'https://github.com/shinkuan/'):
            self.assertNotIn(legacy, ui)
        self.assertIn('var WC=`https://github.com/zgozh/zheyou-majsoul`', ui)
        self.assertIn('var JC=`0.1.0`,YC=[]', ui)


if __name__ == '__main__':
    unittest.main()
