"""Command-line launcher for VoiceIn."""

from __future__ import annotations

import argparse
import logging
import sys

import sounddevice as sd

from openai import OpenAI

from voicein.config import load_config
from voicein.daemon import VoiceDaemon
from voicein.tray import TrayController

LOGGER = logging.getLogger('voicein.cli')


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(levelname)s %(message)s',
    )


def list_inputs() -> int:
    print('Pulse/PortAudio microphones (max_input_channels > 0)')
    devices = sd.query_devices()

    print()
    hostapis = sd.query_hostapis()

    try:
        default_input, _default_output = sd.default.device
    except Exception:
        default_input = None

    matched = False
    for idx, meta in enumerate(devices):
        max_in = int(meta.get('max_input_channels') or 0)
        if max_in <= 0:
            continue
        matched = True

        host_idx = meta.get('hostapi')
        host_tag = '?'
        if host_idx is not None and hostapis:
            host_tag = hostapis[host_idx]['name']

        flag = '*' if idx == default_input else ' '

        hz = meta.get('default_samplerate')
        try:
            hz_fmt = '--' if not hz else f'{int(hz)} Hz'
        except (TypeError, ValueError):
            hz_fmt = '--'

        label = meta.get('name', '<unknown>')
        print(f'{flag} {idx:03d}: in={max_in:<2} {hz_fmt:<8} [{host_tag}] {label}')

    if not matched:
        print('-- no capture devices enumerated --')

    print()
    print('Use the trailing index inside ~/.config/voicein/config.toml as input_device.')
    return 0


def launch_tray(verbose: bool) -> int:
    configure_logging(verbose)
    cfg = load_config()

    if not cfg.openai_api_key:
        LOGGER.error(
            'Missing API key — set VOICEIN_OPENAI_API_KEY in project .env '
            'or ~/.config/voicein/.env (OPENAI_API_KEY also accepted).'
        )
        return 3

    client = OpenAI(api_key=cfg.openai_api_key)
    tray = TrayController(cfg)
    daemon_obj = VoiceDaemon(cfg, tray=tray, client=client)
    tray.bind_daemon(lambda d=daemon_obj: d)

    daemon_obj.bootstrap()
    LOGGER.info('Tray indicator ready - left-click default action toggles recording')
    tray.run()
    LOGGER.info('VoiceIn exited')

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='VoiceIn recorder')

    subs = parser.add_subparsers(dest='command')

    run = subs.add_parser('run', help='Start tray recorder (default)')
    run.add_argument('-v', '--verbose', action='store_true')

    subs.add_parser('list-devices', help='Enumerate capture devices')

    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    if not raw:
        raw = ['run']
    elif raw[0] not in {'run', 'list-devices'}:

        raw = ['run'] + raw

    parser = build_parser()
    args = parser.parse_args(raw)

    if args.command == 'list-devices':
        configure_logging(verbose=False)
        return list_inputs()

    verbose = bool(getattr(args, 'verbose', False))
    return launch_tray(verbose)


if __name__ == '__main__':
    sys.exit(main())

