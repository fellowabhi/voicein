# VoiceIn

Toggle dictation for **Ubuntu GNOME X11**: record from the system tray (or optional global shortcut), transcribe with OpenAI, optionally refine with GPT-4o-mini, then paste via clipboard + `xdotool`.

## Requirements

- Ubuntu 24.04+ GNOME session on **X11** (clipboard paste uses `xdotool`)
- Microphone access
- `xdotool`, `xclip`, PortAudio (`libportaudio2` / headers for build)
- Python 3.10+

## Install

From the repo root:

```bash
chmod +x install.sh
./install.sh
```

Set your API key in the **project** `.env` (recommended):

```
VOICEIN_OPENAI_API_KEY=sk-...
```

Or in `~/.config/voicein/.env`. The project file wins when both exist. `OPENAI_API_KEY` is still accepted as a fallback.

Optional: edit `~/.config/voicein/config.toml`.

Start the daemon (user systemd example in `install.sh`):

```bash
systemctl --user enable --now voicein.service
```

Or run once:

```bash
/path/to/repo/.venv/bin/voicein run
```

### List microphones

```bash
.venv/bin/python -m voicein list-devices
```

## Usage

- **Tray icon**: left-click **Toggle** — recording on/off. While recording: left-click again to stop; STT runs, then formatted text pastes where the caret is focused.
- **Menus**: Cancel, rewrite level presets (0/3/6/9), pause LLM, open config folder, Quit.
- **Shortcut** (optional): default `Super+Shift+V` toggles like the tray. Press **Escape** while recording to cancel.

## `rewrite_level` (0–10)

- **0** (default): remove fillers & obvious STT glitches; apply spoken layout commands (**new paragraph**, **bullet point**); **no paraphrasing**.
- Higher values gradually allow clearer wording / prompt-style structure while **still forbidding invented requirements or facts**. See `[llm]` in example config.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
voicein run --foreground
```

## License

MIT
