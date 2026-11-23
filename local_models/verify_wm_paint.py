"""Verify the two redraw outcomes in the published AkagiMS x64 executable."""

from pathlib import Path
from struct import unpack_from
import sys


def verify(executable):
    image = executable.read_bytes()
    branch = 0x15749F
    assert image[branch - 2:branch] == b"\x84\xc0", "Expected test al, al after the redraw flush"
    assert image[branch:branch + 2] == b"\x0f\x84", "Expected je for a false redraw result"
    success = branch + 6
    reentry = success + unpack_from("<i", image, branch + 2)[0]

    # A successful flush must still run both event-loop calls before dispatching WM_PAINT.
    assert success == 0x1574A5 and image[0x1574CF] == 0xE9
    dispatch = 0x1574D4 + unpack_from("<i", image, 0x1574D0)[0]
    assert image[dispatch:dispatch + 8] == bytes.fromhex("48 89 d9 ba 0f 00 00 00")
    assert reentry == dispatch, (
        f"Reentrant redraw jumps to 0x{reentry:x}; expected normal WM_PAINT dispatch at 0x{dispatch:x}"
    )
    print(f"{executable.name}: successful and reentrant redraws take the expected paths")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
