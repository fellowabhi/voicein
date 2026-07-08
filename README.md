# VoiceIn

Toggle dictation for **Ubuntu GNOME X11**: press a shortcut to record, transcribe with OpenAI, optionally refine with GPT-4o-mini, then paste via clipboard + `xdotool`.

**Recommended:** on-demand toggle mode (no background process, no sleep freezes).

## Requirements

- Ubuntu 24.04+ GNOME session on **X11** (clipboard paste uses `xdotool`)
- Microphone access
- `xdotool`, `xclip`, `paplay` (PulseAudio), PortAudio (`libportaudio2` / headers for build)
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

### On-demand mode (recommended)

Install the GNOME shortcut (default **Ctrl+Shift+Insert**):

```bash
./scripts/install-toggle-shortcut.sh
```

Or bind manually in **Settings → Keyboard → Custom Shortcuts** to:

```bash
/path/to/repo/scripts/voicein-toggle.sh
```

Leave `[hotkey] shortcut = ""` in config — do **not** run `voicein run` at the same time.

### Tray daemon (optional / legacy)

Foreground tray + optional in-app global shortcut (can freeze GNOME after sleep on X11):

```bash
./scripts/voicein-run.sh
# or: .venv/bin/python -m voicein run
```

User systemd / GNOME autostart files are installed by `install.sh` but **disabled by default**; enable only if you want the tray daemon at login.

### List microphones

```bash
.venv/bin/python -m voicein list-devices
```

## Usage — on-demand toggle

- **First press** — start recording (notification + start sound)
- **Second press** — stop, transcribe, paste, exit (notification + stop sound + paste sound)
- Logs: `~/.local/state/voicein/toggle.log`

### Audio cues

Configure in `~/.config/voicein/config.toml`:

```toml
[cues]
start = "/usr/share/sounds/freedesktop/stereo/device-added.oga"
stop = "/usr/share/sounds/freedesktop/stereo/device-removed.oga"
paste = "/usr/share/sounds/freedesktop/stereo/message.oga"
```

Preview system sounds:

```bash
./scripts/preview-sounds.sh
```

Paths can also use `canberra:bell` style event names.

### Skip LLM formatting

Paste raw transcription only:

```toml
[llm]
enabled = false
```

## Usage — tray daemon

- **Tray icon**: left-click toggles recording on/off; STT runs, then text pastes at the focused caret.
- **Menus**: Cancel, rewrite presets (0/3/6/9), LLM on/off, open config folder, Quit.
- **In-app shortcut** (optional, `[hotkey]` in config): same toggle; **Escape** cancels while recording.

## `rewrite_level` (0–10)

Only applies when `[llm] enabled = true`.

- **0** (default): remove fillers & obvious STT glitches; apply spoken layout commands (**new paragraph**, **bullet point**); **no paraphrasing**.
- Higher values gradually allow clearer wording / prompt-style structure while **still forbidding invented requirements or facts**. See `[llm]` in example config.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m voicein run -v
python -m voicein toggle -v
```

## License

MIT
