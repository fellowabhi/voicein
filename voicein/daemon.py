"""Core orchestrator — microphone capture → transcription → clipboard."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace

from openai import OpenAI

from voicein.audio.recorder import AudioRecorder
from voicein.config import VoicEinConfig
from voicein.hotkey import ShortcutListener
from voicein.pipeline import run_pipeline
from voicein.state import AppState
from voicein.tray import TrayController

logger = logging.getLogger(__name__)


class VoiceDaemon:
    def __init__(self, cfg: VoicEinConfig, *, tray: TrayController, client: OpenAI) -> None:
        self.cfg = cfg
        self.tray = tray
        self.client = client

        self._state_lock = threading.RLock()
        self._state = AppState.IDLE

        self.rewrite_level = cfg.llm_rewrite_level
        self.llm_enabled = cfg.llm_enabled

        self.recorder = AudioRecorder(
            sample_rate=cfg.audio_sample_rate,
            input_device=cfg.audio_input_device,
        )

        self._shutdown = threading.Event()

        self._shortcut = ShortcutListener(
            cfg.hotkey_shortcut,
            on_toggle=self.toggle_from_shortcut,
            on_cancel=self.cancel_from_shortcut,
        )

    # ------------------------------------------------------------------

    def toggle_from_shortcut(self) -> None:
        threading.Thread(target=self.request_toggle, name='voicein-shortcut', daemon=True).start()

    def cancel_from_shortcut(self) -> None:
        threading.Thread(target=self.request_cancel, name='voicein-cancel', daemon=True).start()

    def request_toggle(self) -> None:
        with self._state_lock:
            if self._state == AppState.PROCESSING:
                logger.debug('Ignoring toggle while processing')
                return

            if self._state == AppState.IDLE:
                try:
                    self.recorder.start()
                except Exception:  # noqa: BLE001
                    logger.exception('Unable to acquire microphone capture')
                    self.tray.signal_error('Microphone start failed')
                    return

                self._state = AppState.RECORDING

                self.tray.on_state_change(AppState.RECORDING)
                self.tray.arm_recording_timer()

                self._spawn_duration_guard()
                return

            if self._state == AppState.RECORDING:
                self._finalize_capture_locked()

    def request_cancel(self) -> None:

        with self._state_lock:
            if self._state != AppState.RECORDING:
                return

            logger.info('Recording cancelled from UI/hotkey')
            self.recorder.discard()
            self._state = AppState.IDLE

        self.tray.disarm_recording_timer()

        self.tray.signal_ready()

    def assign_rewrite(self, level: int) -> None:
        clipped = max(0, min(10, int(level)))

        self.rewrite_level = clipped
        logger.info('Rewrite preset set to %s', clipped)


    def toggle_llm(self, enabled: bool) -> None:


        enabled_flag = bool(enabled)

        self.llm_enabled = enabled_flag

        logger.info('LLM post-process switched %s', 'on' if enabled_flag else 'off')




    def bootstrap(self) -> None:

        self._shortcut.start()




        shortcut = getattr(self.cfg, 'hotkey_shortcut', '') or ''

        hint = shortcut if shortcut else '[tray only]'





        logger.info('VoiceDaemon online — hotkey %s', hint)







    def shutdown(self) -> None:

        self._shutdown.set()






        try:
            self._shortcut.stop()






        finally:
            try:
                with self._state_lock:
                    try:
                        self.recorder.discard()


                    finally:


                        self._state = AppState.IDLE




            finally:
                self.tray.disarm_recording_timer()


    # --------------------------------------------------------------




    def state_snapshot(self) -> AppState:


        with self._state_lock:
            return self._state




    def recording_duration(self) -> float | None:


        """Return recorder duration seconds while RECORDING."""

        with self._state_lock:


            if self._state != AppState.RECORDING:
                return None


            secs = self.recorder.duration_seconds()
            return float(secs) if secs is not None else None

    # internals ---------------------------------------------------


    def _finalize_capture_locked(self) -> None:
        """

        Preconditions: ``_state_lock`` held while ``RECORDING``.
        Consumes WAV, flips to ``PROCESSING`` and asynchronously runs API work.

        """


        if self._state != AppState.RECORDING:
            return


        try:
            wav = self.recorder.stop_and_get_wav()






        except Exception:  # noqa: BLE001
            logger.exception('Recorder teardown failed unexpectedly')
            self.recorder.discard()

            self._state = AppState.IDLE

            self.tray.disarm_recording_timer()
            self.tray.signal_error('Recorder failure')
            return

        self._state = AppState.PROCESSING
        self.tray.disarm_recording_timer()


        self.tray.on_state_change(AppState.PROCESSING)







        if not wav:
            logger.debug('Captured clip discarded as silence/short spike')
            self._state = AppState.IDLE

            self.tray.signal_ready()
            return

        worker_cfg = replace(
            self.cfg,
            llm_enabled=self.llm_enabled,

            llm_rewrite_level=self.rewrite_level,

        )

        wav_blob = wav

        def runner() -> None:


            okay = False
            detail_blob = ''

            try:


                okay, detail_blob = run_pipeline(
                    client=self.client,

                    cfg=worker_cfg,

                    wav_bytes=wav_blob,
                    rewrite_level=self.rewrite_level,
                )


            except Exception:  # noqa: BLE001




                logger.exception('Pipeline aborted')
                okay = False
                detail_blob = 'Voice pipeline crashed — inspect logs'

            finally:


                with self._state_lock:
                    self._state = AppState.IDLE

                self.tray.disarm_recording_timer()






                preview = ''

                banner = ''

                if okay:


                    snippet = detail_blob or 'Paste complete'


                    preview = snippet if len(snippet) <= 176 else snippet[:173] + '...'






                    logger.info('%s', preview)
                    self.tray.flash_status(preview)

                else:


                    banner = detail_blob or 'Voice pipeline failed'






                    logger.warning('%s', banner)

                    self.tray.signal_error(banner)



        threading.Thread(target=runner, name='voicein-pipeline', daemon=True).start()



    def _spawn_duration_guard(self) -> None:


        ceiling = getattr(self.cfg, 'audio_max_duration_secs', 0) or 0



        def watchdog() -> None:
            warned_flag = False

            while not self._shutdown.is_set():

                time.sleep(0.52)

                with self._state_lock:
                    snapshot = self._state
                    duration_secs = (
                        float(self.recorder.duration_seconds() or 0.0)
                        if snapshot == AppState.RECORDING
                        else 0.0
                    )


                if snapshot != AppState.RECORDING:


                    return

                if ceiling <= 0:


                    continue




                nearing = duration_secs >= max(3.0, ceiling - 30)

                if nearing and not warned_flag:
                    warned_flag = True





                    self.tray.flash_status(f'Auto-stop near ~{ceiling}s cap')

                if duration_secs >= ceiling:
                    logger.info('Auto finishing clip at %.2fs (cap %ss)', duration_secs, ceiling)







                    threading.Thread(target=self.request_toggle, name='voicein-cap-stop', daemon=True).start()


                    return

        threading.Thread(target=watchdog, name='voicein-duration-watch', daemon=True).start()

