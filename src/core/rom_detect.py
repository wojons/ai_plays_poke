"""
ROM detection utilities.

Reads cartridge headers to determine platform (GB vs GBA) and extract
the game title without needing to spin up a full emulator.
"""

from __future__ import annotations

from pathlib import Path


def detect_platform(rom_path: str | Path) -> str:
    """
    Detect whether *rom_path* is a GB or GBA ROM by reading the cartridge header.

    Heuristic:
        - If the Nintendo logo check byte at offset ``0x0104`` equals ``0xCE``
          AND the file size is ≤ 2 MiB, it is a **GB** ROM.
        - Otherwise it is assumed to be a **GBA** ROM.

    Returns:
        ``"gb"`` or ``"gba"``.
    """
    rom_path = Path(rom_path)
    if not rom_path.is_file():
        raise FileNotFoundError(f"ROM not found: {rom_path}")

    # GB ROMs have the Nintendo logo starting at 0x0104 with 0xCE 0xED ...
    # GBA ROMs have the logo at 0x04, and byte 0x0104 is *not* 0xCE.
    with open(rom_path, "rb") as fh:
        fh.seek(0x0104)
        byte_104 = fh.read(1)

    is_gb_logo = (byte_104 == b"\xCE") and (rom_path.stat().st_size <= 2_097_152)

    return "gb" if is_gb_logo else "gba"


def get_game_name(rom_path: str | Path) -> str:
    """
    Extract the game title from the ROM cartridge header.

    - **GB**: title is at bytes ``0x134–0x143`` (up to 16 chars, uppercase).
    - **GBA**: title is at bytes ``0xA0–0xAB`` (up to 12 chars, uppercase).

    Returns:
        The game title as a trimmed string, or ``"UNKNOWN"``.
    """
    rom_path = Path(rom_path)
    if not rom_path.is_file():
        raise FileNotFoundError(f"ROM not found: {rom_path}")

    platform = detect_platform(rom_path)

    with open(rom_path, "rb") as fh:
        if platform == "gb":
            fh.seek(0x0134)
            raw = fh.read(16)
        else:  # gba
            fh.seek(0x00A0)
            raw = fh.read(12)

    # Decode as ASCII, stopping at null bytes.
    title = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    return title if title else "UNKNOWN"


# ── quick smoke-test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    for rom in sys.argv[1:]:
        plat = detect_platform(rom)
        name = get_game_name(rom)
        print(f"{rom:60s}  platform={plat}  title={name!r}")
