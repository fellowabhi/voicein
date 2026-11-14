"""On-demand dictation: one GNOME shortcut toggles record/stop (no pynput)."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from voicein.config import load_config
from voicein.cues import play_recording_cue

logger = logging.getLogger(__name__)

PHASE_RECORDING = 'recording'
PHASE_PROCESSING = 'processing'
PHASE_SUCCESS = 'success'
PHASE_ERROR = 'error'

_PHASE_RECORDING = PHASE_RECORDING
_PHASE_PROCESSING = PHASE_PROCESSING


def runtime_dir() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return Path(base) / 'voicein'


def tray_pid_path() -> Path:
    return runtime_dir() / 'tray.pid'


def _runtime_dir() -> Path:
    return runtime_dir()


def _state_path() -> Path:
    return _runtime_dir() / 'session.json'


def _lock_path() -> Path:
    return _runtime_dir() / 'session.lock'


def _stop_cue_flag() -> Path:
    return _runtime_dir() / 'stop_cue.played'


def _mark_stop_cue_played() -> None:
    _runtime_dir().mkdir(parents=True, exist_ok=True)
    _stop_cue_flag().write_text('1', encoding='utf-8')


def _consume_stop_cue_played() -> bool:
    flag = _stop_cue_flag()
    if not flag.is_file():
        return False
    try:
        flag.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def _log_dir() -> Path:
    return Path.home() / '.local/state/voicein'


def configure_toggle_logging(*, verbose: bool) -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_dir / 'toggle.log', encoding='utf-8'),
    ]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=handlers,
        force=True,
    )


def _notify(title: str, body: str = '') -> None:
    if not load_config().feedback_desktop_notifications:
        return
    if not shutil.which('notify-send'):
        return
    args = ['notify-send', '-a', 'VoiceIn', title]
    if body:
        args.append(body)
    try:
        subprocess.run(args, check=False, timeout=3)
    except OSError:
        pass


def read_session_state() -> dict | None:
    path = _state_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _read_state() -> dict | None:
    return read_session_state()


def _write_state(*, pid: int, phase: str, detail: str = '') -> None:
    _runtime_dir().mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {'pid': pid, 'phase': phase, 'started': time.time()}
    if detail:
        payload['detail'] = detail
    _state_path().write_text(json.dumps(payload), encoding='utf-8')


def clear_session_state() -> None:
    try:
        _state_path().unlink(missing_ok=True)
    except OSError:
        pass


def _clear_state() -> None:
    clear_session_state()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_alive(pid: int) -> bool:
    return pid_alive(pid)


def ensure_toggle_tray() -> None:
    """Keep a single status tray process for toggle-mode feedback."""
    path = tray_pid_path()
    if path.is_file():
        try:
            if pid_alive(int(path.read_text(encoding='utf-8').strip())):
                return
        except (OSError, ValueError):
            pass
    subprocess.Popen(
        [sys.executable, '-m', 'voicein', 'toggle-tray'],
        env=os.environ.copy(),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _spawn_record_session() -> None:
    env = os.environ.copy()
    subprocess.Popen(
        [sys.executable, '-m', 'voicein', 'record-session'],
        env=env,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def handle_toggle(*, verbose: bool = False) -> int:
    """First press starts background capture; second press stops and transcribes."""

    _runtime_dir().mkdir(parents=True, exist_ok=True)
    lock_file = _lock_path().open('a+', encoding='utf-8')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _read_state()
        if state:
            pid = int(state.get('pid', 0))
            phase = str(state.get('phase', ''))
            if _pid_alive(pid):
                if phase == _PHASE_RECORDING:
                    cfg = load_config()
                    play_recording_cue('stop', spec=cfg.cue_sound_stop, block=False)
                    _mark_stop_cue_played()
                    configure_toggle_logging(verbose=verbose)
                    logger.info('Stopping active recording session (pid %s)', pid)
                    os.kill(pid, signal.SIGUSR1)
                    _notify('VoiceIn', 'Stopping — transcribing…')
                    return 0
                if phase == _PHASE_PROCESSING:
                    configure_toggle_logging(verbose=verbose)
                    logger.info('Session busy processing (pid %s)', pid)
                    _notify('VoiceIn', 'Still processing previous dictation…')
                    return 0
            configure_toggle_logging(verbose=verbose)
            logger.warning('Stale session file for pid %s — starting fresh', pid)
            _clear_state()

        cfg = load_config()
        play_recording_cue('start', spec=cfg.cue_sound_start, block=False)
        configure_toggle_logging(verbose=verbose)
        logger.info('Starting new recording session')
        ensure_toggle_tray()
        _spawn_record_session()
        _notify('VoiceIn', 'Recording — press shortcut again to stop')
        return 0
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def run_record_session() -> int:
    """Background worker: record until SIGUSR1, then STT → paste → exit."""

    from openai import OpenAI

    from voicein.audio.recorder import AudioRecorder
    from voicein.pipeline import run_pipeline

    configure_toggle_logging(verbose=False)
    cfg = load_config()
    ensure_toggle_tray()

    if not cfg.openai_api_key:
        logger.error('Missing API key')
        _notify('VoiceIn', 'Missing OpenAI API key in .env')
        return 3

    _write_state(pid=os.getpid(), phase=_PHASE_RECORDING)
    stop_event = threading.Event()

    def _on_stop(_signum: int, _frame: object | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGUSR1, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    recorder = AudioRecorder(
        sample_rate=cfg.audio_sample_rate,
        input_device=cfg.audio_input_device,
    )

    try:
        recorder.start()
    except Exception:  # noqa: BLE001
        logger.exception('Microphone start failed')
        _clear_state()
        _notify('VoiceIn', 'Microphone start failed')
        return 1

    ceiling = cfg.audio_max_duration_secs or 0
    if ceiling > 0:
        threading.Thread(
            target=_duration_guard,
            args=(recorder, stop_event, ceiling),
            name='voicein-toggle-cap',
            daemon=True,
        ).start()

    logger.info('Recording (pid %s)', os.getpid())
    stop_event.wait()

    _write_state(pid=os.getpid(), phase=_PHASE_PROCESSING)

    try:
        wav = recorder.stop_and_get_wav()
    except Exception:  # noqa: BLE001
        logger.exception('Recorder stop failed')
        _clear_state()
        _notify('VoiceIn', 'Recording failed')
        return 1

    if not _consume_stop_cue_played():
        play_recording_cue('stop', spec=cfg.cue_sound_stop)

    if not wav:
        logger.info('Empty or too-short clip discarded')
        _clear_state()
        _notify('VoiceIn', 'Nothing captured')
        return 0

    client = OpenAI(api_key=cfg.openai_api_key)
    try:
        okay, detail = run_pipeline(
            client=client,
            cfg=cfg,
            wav_bytes=wav,
            rewrite_level=cfg.llm_rewrite_level,
        )
    except Exception:  # noqa: BLE001
        logger.exception('Pipeline failed')
        _clear_state()
        _notify('VoiceIn', 'Transcription failed — see toggle.log')
        return 1

    if okay:
        snippet = detail.replace('\r', '').splitlines()[0][:120]
        logger.info('%s', detail)
        play_recording_cue('paste', spec=cfg.cue_sound_paste)
        _write_state(pid=0, phase=PHASE_SUCCESS, detail=snippet)
        return 0

    logger.warning('%s', detail)
    err = detail[:180] or 'Transcription failed'
    _write_state(pid=0, phase=PHASE_ERROR, detail=err)
    _notify('VoiceIn', err)
    return 1


def _duration_guard(recorder: AudioRecorder, stop_event: threading.Event, ceiling: int) -> None:
    warned = False
    while not stop_event.is_set():
        time.sleep(0.5)
        duration = recorder.duration_seconds()
        if duration is None:
            continue
        if not warned and duration >= max(3.0, ceiling - 30):
            warned = True
            _notify('VoiceIn', f'Auto-stop near ~{ceiling}s cap')
        if duration >= ceiling:
            logger.info('Auto-stop at %.1fs (cap %ss)', duration, ceiling)
            stop_event.set()
            return
