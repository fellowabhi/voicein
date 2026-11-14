"""Command-line launcher for VoiceIn."""

from __future__ import annotations

import argparse
import logging
import sys

LOGGER = logging.getLogger('voicein.cli')


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(levelname)s %(message)s',
    )


def list_inputs() -> int:
    import sounddevice as sd

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


def setup_web_auth(*, password: str | None, rotate: bool) -> int:
    from voicein.web_auth import (
        WebAuth,
        generate_password,
        hash_password,
        load_auth,
        validate_new_password,
        write_auth,
    )

    existing = load_auth()
    if existing is not None and not rotate and not password:
        from voicein.web_auth import auth_path

        print(f'Web password already set ({auth_path()}).')
        print('Re-run with --rotate to generate a new one (signs everyone out).')
        return 0

    chosen = (password or '').strip() or generate_password()
    err = validate_new_password(chosen)
    if err:
        LOGGER.error('%s', err)
        return 2

    import secrets

    from voicein.web_auth import auth_path

    salt, hashed = hash_password(chosen)
    write_auth(
        WebAuth(
            password_salt=salt,
            password_hash=hashed,
            session_secret=secrets.token_bytes(32),
            session_days=existing.session_days if existing else 90,
        )
    )

    print(f'Wrote {auth_path()} (mode 600)')
    if password:
        print('Password saved (hash only). It will not be shown again.')
    else:
        print()
        print('  Web password (save this; it is not stored in plain text):')
        print(f'    {chosen}')
        print()
        print('  Stays signed in for 90 days on this phone after login.')
    return 0


def launch_web() -> int:
    from voicein.config import load_config
    from voicein.web import serve

    cfg = load_config()
    if not cfg.openai_api_key:
        LOGGER.error('Missing API key — set VOICEIN_OPENAI_API_KEY in project .env')
        return 3
    serve(host=cfg.web_host, port=cfg.web_port, public_host=cfg.web_public_host)
    return 0


def launch_tray(verbose: bool) -> int:
    from openai import OpenAI

    from voicein.config import load_config
    from voicein.daemon import VoiceDaemon
    from voicein.tray import TrayController

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

    toggle = subs.add_parser(
        'toggle',
        help='On-demand mode: start/stop recording via GNOME shortcut (no pynput)',
    )
    toggle.add_argument('-v', '--verbose', action='store_true')

    subs.add_parser('record-session', help=argparse.SUPPRESS)
    subs.add_parser(
        'toggle-tray',
        help=argparse.SUPPRESS,
    )

    web = subs.add_parser('web', help='Phone web recorder (localhost; put Cloudflare in front)')
    web.add_argument('-v', '--verbose', action='store_true')

    setup = subs.add_parser('web-setup', help='Create or rotate the web UI password')
    setup.add_argument('--password', help='Set this password instead of generating one')
    setup.add_argument('--rotate', action='store_true', help='Replace an existing password')

    subs.add_parser('list-devices', help='Enumerate capture devices')

    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    if not raw:
        raw = ['run']
    elif raw[0] not in {
        'run',
        'list-devices',
        'toggle',
        'record-session',
        'toggle-tray',
        'web',
        'web-setup',
    }:

        raw = ['run'] + raw

    parser = build_parser()
    args = parser.parse_args(raw)

    if args.command == 'list-devices':
        configure_logging(verbose=False)
        return list_inputs()

    if args.command == 'web-setup':
        return setup_web_auth(
            password=getattr(args, 'password', None),
            rotate=bool(getattr(args, 'rotate', False)),
        )

    if args.command == 'web':
        configure_logging(verbose=bool(getattr(args, 'verbose', False)))
        return launch_web()

    if args.command == 'toggle':
        from voicein.toggle_session import handle_toggle

        return handle_toggle(verbose=bool(getattr(args, 'verbose', False)))

    if args.command == 'record-session':
        from voicein.toggle_session import run_record_session

        return run_record_session()

    if args.command == 'toggle-tray':
        from voicein.tray_toggle import run_toggle_tray

        return run_toggle_tray()

    verbose = bool(getattr(args, 'verbose', False))
    return launch_tray(verbose)


if __name__ == '__main__':
    sys.exit(main())
