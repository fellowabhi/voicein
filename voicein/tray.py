"""System tray interface built on pystray."""

from __future__ import annotations

import logging
import subprocess
import threading
import time

import pystray
from PIL import Image, ImageDraw

from voicein.config import VoicEinConfig, config_dir

from voicein.state import AppState

logger = logging.getLogger(__name__)


def _draw_icon(rgb: tuple[int, int, int]) -> Image.Image:
    dia = 128
    canvas = Image.new('RGBA', (dia, dia), (10, 12, 14, 0))
    drawer = ImageDraw.Draw(canvas)

    gutter = dia // 8
    drawer.ellipse(
        [
            gutter,
            gutter,

            dia - gutter - 1,
            dia - gutter - 1,
        ],

        outline=(24, 28, 32, 235),
        width=max(4, dia // 32),
        fill=rgb + (230,),

    )


    stem_w = dia // 10

    center_x = dia // 2

    shaft_top = int(dia * 0.42)




    shaft_bottom = int(dia * 0.63)







    drawer.rounded_rectangle(
        [
            center_x - stem_w // 2,

            shaft_top,

            center_x + stem_w // 2,
            shaft_bottom,
        ],

        radius=max(4, dia // 32),
        fill=(252, 252, 255, 235),
        outline=(220, 220, 229, 255),
        width=max(3, dia // 45),
    )


    cradle_w = dia // 3

    drawer.arc(
        [
            center_x - cradle_w,
            shaft_bottom - stem_w,

            center_x + cradle_w,
            shaft_bottom + stem_w * 3,
        ],
        start=210,
        end=330,

        fill=(245, 245, 251, 255),
        width=max(5, dia // 28),

    )


    pillar = [
        center_x,
        shaft_bottom + stem_w,

        center_x,
        int(dia * 0.82),
    ]


    drawer.line(pillar, fill=(245, 245, 251, 255), width=max(3, dia // 40))



    cradle_base = [
        center_x - stem_w,

        pillar[3] - stem_w,
        center_x + stem_w,
        pillar[3] + stem_w,

    ]

    drawer.arc(cradle_base, start=180, end=0, fill=(240, 240, 246, 220), width=max(4, dia // 30))






    return canvas


ICON_IDLE = _draw_icon((106, 120, 140))







ICON_RECORD = _draw_icon((224, 86, 86))
ICON_PROCESSING = _draw_icon((235, 165, 45))
ICON_PROCESSING_PULSE = _draw_icon((255, 200, 70))
ICON_SUCCESS = _draw_icon((72, 175, 95))
ICON_ERROR = _draw_icon((190, 95, 95))
ICON_BUSY = ICON_PROCESSING


class TrayController:
    def __init__(self, cfg: VoicEinConfig) -> None:
        self.cfg = cfg




        self._daemon_getter: object | None = None


        placeholder = pystray.Menu(pystray.MenuItem('Initializing...', lambda *__, **_: None))



        self.indicator = pystray.Icon(
            name='voicein',
            icon=ICON_IDLE,

            title=self._idle_fallback_title(),




            menu=placeholder,
        )


        self.indicator.default_action = self._default_toggle




        self._tick_thread: threading.Thread | None = None
        self._tick_event = threading.Event()

        self._proc_thread: threading.Thread | None = None
        self._proc_event = threading.Event()
        self._proc_pulse_on = False






    # ------------------------------------------------------------------
    # Wiring

    # ------------------------------------------------------------------

    def bind_daemon(self, getter):  # noqa: ANN001
        """Resolve runtime VoiceDaemon instance lazily."""

        self._daemon_getter = getter

        self.indicator.menu = self._build_menu()
        try:
            self.indicator.title = self.idle_title_text()
        except RuntimeError:


            logger.debug('Daemon unresolved while binding tray')






    # ------------------------------------------------------------------

    def run(self) -> None:
        """Block on GTK/AppIndicator loop."""






        self.indicator.run()


    # ------------------------------------------------------------------

    def _daemon(self):  # type: ignore[no-untyped-def]
        if self._daemon_getter is None:
            raise RuntimeError('Tray not linked to daemon')
        binder = self._daemon_getter
        return binder()




    # ------------------------------------------------------------------

    def _enqueue(self, fn):  # noqa: ANN001
        threading.Thread(target=fn, daemon=True).start()




    def _default_toggle(self, *__) -> None:  # pragma: no cover
        try:
            self._enqueue(self._daemon().request_toggle)
        except RuntimeError:


            logger.error('daemon missing')


    # ------------------------------------------------------------------

    def _idle_fallback_title(self) -> str:
        llm = 'on' if self.cfg.llm_enabled else 'off'






        return f"voicein idle | L{self.cfg.llm_rewrite_level} | LLM {llm}"


    def idle_title_text(self) -> str:
        """Idle tooltip honoring runtime overrides."""

        try:
            d = self._daemon()
            llm = 'on' if d.llm_enabled else 'off'

            return f"voicein idle | L{d.rewrite_level} | LLM {llm}"






        except RuntimeError:


            return self._idle_fallback_title()




    def _recording_tooltip(self) -> str:
        d = self._daemon()
        secs_raw = getattr(d.recorder, 'duration_seconds', lambda: None)()


        secs = float(secs_raw) if secs_raw is not None else 0.0


        mins, sec_part = divmod(int(round(max(0.0, secs))), 60)

        stamp = f'{mins:02d}:{sec_part:02d}'
        lvl = getattr(d, 'rewrite_level', self.cfg.llm_rewrite_level)
        return f"voicein REC {stamp} | L{lvl}"


    def _processing_tooltip(self) -> str:
        lvl = getattr(self._daemon(), 'rewrite_level', self.cfg.llm_rewrite_level)
        dots = '.' * (1 + (int(time.time() * 2) % 3))
        return f"voicein | PROCESSING{dots} please wait | L{lvl}"


    # ------------------------------------------------------------------


    def on_state_change(self, state: AppState) -> None:
        state_map = {
            AppState.IDLE: (ICON_IDLE, self.idle_title_text()),
            AppState.RECORDING: (ICON_RECORD, self._recording_tooltip()),
            AppState.PROCESSING: (ICON_PROCESSING, self._processing_tooltip()),
        }

        glyph, caption = state_map.get(state, (ICON_IDLE, self.idle_title_text()))

        self.indicator.icon = glyph
        self.indicator.title = caption

        if state == AppState.RECORDING:
            self._halt_processing_pulse()
            self._kick_recording_ticks()
        elif state == AppState.PROCESSING:
            self._halt_recording_ticks()
            self._kick_processing_pulse()
        else:
            self._halt_recording_ticks()
            self._halt_processing_pulse()




    def signal_ready(self) -> None:
        self._halt_processing_pulse()
        self.indicator.icon = ICON_IDLE




        try:
            self.indicator.title = self.idle_title_text()
        except RuntimeError:


            self.indicator.title = self._idle_fallback_title()




        self._halt_recording_ticks()






        try:
            self.indicator.menu = self._build_menu()


        except RuntimeError:


            logger.debug('Menu skipped during startup')


    def signal_error(self, message: str) -> None:
        """Surface an error visually while snapping back idle shortly afterward."""






        banner = message[:172] + ('...' if len(message) > 172 else '')






        self.indicator.icon = ICON_ERROR

        self.indicator.title = f"voicein | ERROR: {banner}"



        threading.Timer(
            5.5,
            lambda: self.signal_ready(),
        ).start()


    def flash_status(self, payload: str) -> None:
        """Brief green success flash after paste."""

        condensed = payload if len(payload) <= 164 else payload[:161] + '...'
        self._halt_processing_pulse()
        self.indicator.icon = ICON_SUCCESS
        self.indicator.title = f"voicein | DONE: {condensed}"

        threading.Timer(2.5, self.signal_ready).start()


    def arm_recording_timer(self) -> None:


        self._kick_recording_ticks()


    def disarm_recording_timer(self) -> None:


        self._halt_recording_ticks()


    def open_config_home(self) -> None:



        cfg_path = config_dir()


        cfg_path.mkdir(parents=True, exist_ok=True)


        subprocess.Popen(  # noqa: S607
            ['xdg-open', str(cfg_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


    # ------------------------------------------------------------------

    # Recording ticker

    # ------------------------------------------------------------------

    def _kick_recording_ticks(self) -> None:



        self._halt_recording_ticks()



        self._tick_event.clear()



        worker = threading.Thread(target=self._tick_worker, daemon=True)



        self._tick_thread = worker

        worker.start()


    def _halt_recording_ticks(self) -> None:
        self._tick_event.set()


        tid = self._tick_thread




        if tid and tid.is_alive():


            tid.join(timeout=1.75)


        self._tick_thread = None


        self._tick_event = threading.Event()


    def _tick_worker(self) -> None:



        evt = self._tick_event




        interval = 1.05

        while not evt.wait(interval):


            try:

                if self._daemon().state_snapshot() != AppState.RECORDING:
                    break

                title = self._recording_tooltip()
                self.indicator.title = title

            except Exception:  # noqa: BLE001
                logger.debug('recording tick stopped', exc_info=True)
                break

    # ------------------------------------------------------------------
    # Processing pulse (amber icon while STT/LLM runs)
    # ------------------------------------------------------------------

    def _kick_processing_pulse(self) -> None:
        self._halt_processing_pulse()
        self._proc_event.clear()
        self._proc_pulse_on = False
        worker = threading.Thread(target=self._processing_pulse_worker, daemon=True)
        self._proc_thread = worker
        worker.start()

    def _halt_processing_pulse(self) -> None:
        self._proc_event.set()
        tid = self._proc_thread
        if tid and tid.is_alive():
            tid.join(timeout=1.75)
        self._proc_thread = None
        self._proc_event = threading.Event()

    def _processing_pulse_worker(self) -> None:
        evt = self._proc_event
        while not evt.wait(0.45):
            try:
                if self._daemon().state_snapshot() != AppState.PROCESSING:
                    break
                self._proc_pulse_on = not self._proc_pulse_on
                self.indicator.icon = (
                    ICON_PROCESSING_PULSE if self._proc_pulse_on else ICON_PROCESSING
                )
                self.indicator.title = self._processing_tooltip()
            except Exception:  # noqa: BLE001
                logger.debug('processing pulse stopped', exc_info=True)
                break


    # ------------------------------------------------------------------

    # Menus

    # ------------------------------------------------------------------

    def _preset_handler(self, level: int):

        def _runner(_, __=None):  # noqa: ANN001
            def _invoke():
                self._daemon().assign_rewrite(level)



            threading.Thread(target=_invoke, daemon=True).start()


        return _runner


    def _preset_checked(self, wanted: int):


        def _reader(item=None):  # noqa: ANN001
            del item
            try:
                return bool(self._daemon().rewrite_level == wanted)
            except RuntimeError:


                return False




        return _reader




    def _llm_checkbox(self):

        try:
            return bool(self._daemon().llm_enabled)
        except RuntimeError:


            return False


    def _toggle_llm_toggle(self, _, __=None):  # noqa: ANN001
        demon = self._daemon()
        demon.toggle_llm(not demon.llm_enabled)

        try:


            self.indicator.menu = self._build_menu()
        except Exception:  # noqa: BLE001
            logger.debug('menu reload failed', exc_info=True)


    def _build_menu(self) -> pystray.Menu:
        Item = pystray.MenuItem

        rewrite_sub = pystray.Menu(
            Item(
                'Level 0 (format only)',
                self._preset_handler(0),
                checked=self._preset_checked(0),
                radio=True,
            ),

            Item(
                'Level 3',
                self._preset_handler(3),

                checked=self._preset_checked(3),
                radio=True,
            ),
            Item(
                'Level 6',
                self._preset_handler(6),
                checked=self._preset_checked(6),
                radio=True,
            ),

            Item(
                'Level 9',
                self._preset_handler(9),
                checked=self._preset_checked(9),
                radio=True,
            ),

        )


        open_cfg_handler = lambda *_, **__: threading.Thread(target=self.open_config_home, daemon=True).start()


        menus = pystray.Menu(
            Item(
                'Toggle Recording',
                self._default_toggle,
                default=True,
            ),
            Item('Cancel Recording', lambda *_, **__: self._enqueue(self._daemon().request_cancel)),
            pystray.Menu.SEPARATOR,
            Item('Rewrite presets', rewrite_sub),

            Item(
                'Toggle LLM post-process',
                self._toggle_llm_toggle,

                checked=lambda item=None: self._llm_checkbox(),

            ),
            Item(
                'Open config folder',

                open_cfg_handler,

            ),

            pystray.Menu.SEPARATOR,
            Item('Quit', self._quit_handler),
        )

        return menus


    # ------------------------------------------------------------------

    def _quit_handler(self, icon, *_):  # noqa: ANN001
        try:
            self._daemon().shutdown()
        except RuntimeError:


            logger.debug('shutdown without daemon')


        except Exception:  # noqa: BLE001



            logger.warning('daemon shutdown noisy', exc_info=True)







        icon.stop()

