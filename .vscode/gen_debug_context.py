#!/usr/bin/env python3
"""
gen_debug_context.py — Auto-generates Zephyr debug context from the Makefile.

Reads COMPILE_DIR and BOARD from the active (uncommented) lines in the
workspace Makefile, then resolves:
  - The Zephyr SDK version installed at ~/.zephyr_ide/toolchains/
  - The GDB toolchain prefix for the board's CPU architecture
  - Whether the SDK uses the new gnu/ subdirectory layout (SDK 1.0+)
  - Any SVD file present in .vscode/ or the workspace root

Writes the results as "zephyr.*" keys into .vscode/settings.json so that
launch.json can reference them via ${config:zephyr.*} variable substitution.

Run automatically via the "gen-debug-context" VS Code preLaunchTask.
"""

import re
import sys
from pathlib import Path

# ── Markers for the auto-generated block in settings.json ────────────────────
_BLOCK_START = '    // ─── Zephyr debug context (auto-generated — do not edit manually) ─────'
_BLOCK_END   = '    // ─────────────────────────────────────────────────────────────────────────'


# ── Board → GDB architecture mapping ─────────────────────────────────────────
def _board_to_gdb_arch(board: str) -> str:
    b = board.lower()
    b_base = b.split('/')[0]
    if any(x in b for x in ['esp32c3', 'esp32h2', 'esp32c6', 'esp32c2']):
        return 'riscv32-espressif_esp_zephyr-elf'
    if 'esp32s2' in b:
        return 'xtensa-espressif_esp32s2_zephyr-elf'
    if 'esp32s3' in b:
        return 'xtensa-espressif_esp32s3_zephyr-elf'
    if 'esp32' in b:
        return 'xtensa-espressif_esp32_zephyr-elf'
    if any(x in b_base for x in ['hifive', 'riscv', 'rv32', 'rv64', 'vexriscv', 'litex']):
        return 'riscv64-zephyr-elf'
    # Default: ARM Cortex-M (STM32, nRF, LPC, SAM, i.MX, …)
    return 'arm-zephyr-eabi'


# ── Helpers ───────────────────────────────────────────────────────────────────
def _active_makefile_var(makefile_text: str, var: str):
    """Return the value of the first non-commented  VAR ?= value  line."""
    for line in makefile_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        m = re.match(rf'^{re.escape(var)}\s*\??\s*=\s*(.+)', stripped)
        if m:
            return m.group(1).strip()
    return None


def _find_sdk(ws: Path):
    """
    Return the name of the latest Zephyr SDK directory found under
    ~/.zephyr_ide/toolchains/, e.g. "zephyr-sdk-1.0.1".
    Returns None if not found.
    """
    sdk_base = Path.home() / '.zephyr_ide' / 'toolchains'
    if not sdk_base.exists():
        return None
    sdks = sorted(sdk_base.glob('zephyr-sdk-*'))
    return sdks[-1].name if sdks else None


def _find_gdb_toolchain_path(sdk_version: str, gdb_arch: str) -> str:
    """
    Return the toolchain path segment relative to the SDK root.

    SDK 1.0+ changed the layout:
      old: <sdk>/arm-zephyr-eabi/bin/arm-zephyr-eabi-gdb
      new: <sdk>/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gdb

    Returns 'gnu/arm-zephyr-eabi' or 'arm-zephyr-eabi'.
    """
    sdk_dir = Path.home() / '.zephyr_ide' / 'toolchains' / sdk_version
    new_layout = sdk_dir / 'gnu' / gdb_arch
    if new_layout.exists():
        return f'gnu/{gdb_arch}'
    return gdb_arch


def _find_svd(ws: Path, board: str):
    """
    Look for a .svd file in the workspace root or .vscode/ that best matches
    the board name. Returns a workspace-relative path like "STM32C562.svd"
    or ".vscode/STM32F407.svd", or an empty string if nothing found.
    """
    # Search workspace root first, then .vscode/
    svd_files = list(ws.glob('*.svd')) + list((ws / '.vscode').glob('*.svd'))
    if not svd_files:
        return ''

    if len(svd_files) == 1:
        rel = svd_files[0].relative_to(ws)
        return str(rel).replace('\\', '/')

    # Try to find the best match by board name
    board_key = re.sub(r'[^a-z0-9]', '', board.lower())
    for svd in svd_files:
        stem_key = re.sub(r'[^a-z0-9]', '', svd.stem.lower())
        if board_key in stem_key or stem_key in board_key:
            rel = svd.relative_to(ws)
            return str(rel).replace('\\', '/')

    rel = svd_files[0].relative_to(ws)
    return str(rel).replace('\\', '/')  # fallback: first one


def _update_settings(settings_path: Path, values: dict):
    """
    Update the auto-generated zephyr.* block in settings.json.
    Creates the block before the closing } on first run; replaces it on
    subsequent runs. All other content (including user comments) is preserved.
    """
    content = settings_path.read_text(encoding='utf-8')

    lines = [f'    "{k}": "{v}"' for k, v in values.items()]
    block_body = ',\n'.join(lines) + ','
    new_block = f'{_BLOCK_START}\n{block_body}\n{_BLOCK_END}'

    if _BLOCK_START in content:
        # Replace existing block in-place
        pattern = re.escape(_BLOCK_START) + r'.*?' + re.escape(_BLOCK_END)
        content = re.sub(pattern, new_block, content, flags=re.DOTALL)
    else:
        # First run: insert before the final closing brace
        last_brace = content.rfind('}')
        before = content[:last_brace].rstrip()
        if before and not before.endswith(','):
            before += ','
        content = before + '\n\n' + new_block + '\n}\n'

    settings_path.write_text(content, encoding='utf-8')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ws = Path(__file__).parent.parent  # .vscode/ -> workspace root

    # 1. Parse Makefile
    makefile_path = ws / 'Makefile'
    if not makefile_path.exists():
        print(f'ERROR: Makefile not found at {makefile_path}', file=sys.stderr)
        sys.exit(1)
    makefile = makefile_path.read_text(encoding='utf-8')

    compile_dir = _active_makefile_var(makefile, 'COMPILE_DIR')
    board       = _active_makefile_var(makefile, 'BOARD') or 'nucleo_c562re'

    if not compile_dir:
        print(
            'ERROR: No active COMPILE_DIR found in Makefile.\n'
            '       Uncomment exactly one  COMPILE_DIR ?= ...  line.',
            file=sys.stderr,
        )
        sys.exit(1)

    print(f'[gen_debug_context]')
    print(f'  COMPILE_DIR  : {compile_dir}')
    print(f'  BOARD        : {board}')

    # 2. Find SDK version
    sdk_version = _find_sdk(ws)
    if sdk_version:
        print(f'  SDK version  : {sdk_version}')
    else:
        sdk_version = 'zephyr-sdk-1.0.1'  # reasonable fallback
        print(
            f'  WARNING: No Zephyr SDK found at ~/.zephyr_ide/toolchains/.\n'
            f'           Falling back to "{sdk_version}". Install the Zephyr IDE extension.',
        )

    # 3. GDB architecture prefix
    gdb_arch = _board_to_gdb_arch(board)
    print(f'  GDB arch     : {gdb_arch}')

    # 4. GDB toolchain path (handles gnu/ layout in SDK 1.0+)
    gdb_toolchain_path = _find_gdb_toolchain_path(sdk_version, gdb_arch)
    print(f'  GDB toolchain: {gdb_toolchain_path}')

    # 5. SVD file
    svd_file = _find_svd(ws, board)
    if svd_file:
        print(f'  SVD file     : {svd_file}')
    else:
        print(f'  SVD file     : (none found — peripheral viewer unavailable)')

    # 6. Update settings.json
    settings_path = ws / '.vscode' / 'settings.json'
    _update_settings(settings_path, {
        'zephyr.compileDir':        compile_dir,
        'zephyr.board':             board,
        'zephyr.sdkVersion':        sdk_version,
        'zephyr.gdbArch':           gdb_arch,
        'zephyr.gdbToolchainPath':  gdb_toolchain_path,
        'zephyr.svdFile':           svd_file,
        'C_Cpp.default.compileCommands':
            f'${{workspaceFolder}}/{compile_dir}/build/compile_commands.json',
    })
    print('  settings.json updated  ✓')

    # 7. Copy ELF to fixed debug location so launch.json never uses a stale path.
    #    (VS Code caches ${config:*} values and may not pick up settings.json
    #    changes written by the preLaunchTask before resolving the executable path.)
    import shutil
    elf_src = ws / compile_dir / 'build' / 'zephyr' / 'zephyr.elf'
    elf_dst = ws / '.vscode' / 'debug' / 'zephyr.elf'
    if elf_src.exists():
        elf_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(elf_src), str(elf_dst))
        print(f'  Debug ELF: {elf_src.relative_to(ws)}  →  .vscode/debug/zephyr.elf  ✓')
    else:
        print(
            f'  WARNING: ELF not found at {elf_src.relative_to(ws)}\n'
            f'           Run  make build  first.',
            file=sys.stderr,
        )


if __name__ == '__main__':
    main()
