"""HTML for the phone recorder (login + talk)."""

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="theme-color" content="#111318"/>
  <title>VoiceIn</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #111318; color: #eee;
           min-height: 100dvh; display: flex; align-items: center; justify-content: center; }
    form { width: min(22rem, 92vw); display: flex; flex-direction: column; gap: 0.85rem; }
    h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 0.3rem; }
    p { margin: 0; color: #9aa3ad; font-size: 0.9rem; line-height: 1.4; }
    input { font-size: 1.05rem; padding: 0.85rem 0.9rem; border-radius: 12px; border: 1px solid #333;
            background: #1b1e24; color: #fff; }
    button { font-size: 1.05rem; padding: 0.9rem; border: 0; border-radius: 12px;
             background: #4f8cff; color: #fff; font-weight: 600; }
    .err { color: #ff8b8b; min-height: 1.2em; }
  </style>
</head>
<body>
  <form method="post" action="/login" autocomplete="current-password">
    <h1>VoiceIn</h1>
    <p>Unlock once. This phone stays signed in for 90 days.</p>
    <input type="password" name="password" placeholder="Password" required autofocus
           autocomplete="current-password" enterkeyhint="go"/>
    <button type="submit">Continue</button>
    <p class="err">%ERROR%</p>
  </form>
</body>
</html>
"""

APP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="theme-color" content="#111318"/>
  <title>VoiceIn</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #111318; color: #eee;
           min-height: 100dvh; display: flex; flex-direction: column; align-items: center;
           justify-content: center; gap: 1.2rem; padding: 1.25rem; }
    h1 { font-size: 1.2rem; margin: 0; }
    #status { min-height: 2.6em; text-align: center; color: #9aa3ad; font-size: 0.95rem; line-height: 1.4; }
    #rec { width: min(12rem, 70vw); height: min(12rem, 70vw); border-radius: 50%; border: 0;
           font-size: 1.15rem; font-weight: 700; background: #2d6dff; color: #fff; }
    #rec.hot { background: #c62828; }
    #rec:disabled { opacity: 0.55; }
    form { margin: 0; }
    .out { font-size: 0.8rem; color: #667; }
  </style>
</head>
<body>
  <h1>VoiceIn</h1>
  <p id="status">Tap to record. Tap again to send.</p>
  <button id="rec" type="button">Record</button>
  <form method="post" action="/logout"><button class="out" type="submit">Sign out</button></form>
  <script>
    const btn = document.getElementById('rec');
    const status = document.getElementById('status');
    let rec = null, chunks = [], stream = null, recording = false, sending = false;

    function mime() {
      const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
      for (const t of types) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
      }
      return '';
    }

    async function start() {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = mime();
      rec = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
      chunks = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
      rec.start(250);
      recording = true;
      btn.classList.add('hot');
      btn.textContent = 'Stop';
      status.textContent = 'Recording… tap to send.';
    }

    async function stopAndSend() {
      if (!rec) return;
      sending = true;
      btn.disabled = true;
      const blobP = new Promise((resolve) => { rec.onstop = () => resolve(); });
      rec.stop();
      await blobP;
      stream.getTracks().forEach((t) => t.stop());
      recording = false;
      btn.classList.remove('hot');
      btn.textContent = 'Sending';
      status.textContent = 'Transcribing on the laptop…';
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
      rec = null; stream = null; chunks = [];
      try {
        const res = await fetch('/transcribe', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': blob.type || 'application/octet-stream',
            'X-VoiceIn': '1',
          },
          body: blob,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          status.textContent = data.error || ('Failed (' + res.status + ')');
        } else {
          status.textContent = data.ok ? 'Pasted on the computer.' : (data.error || 'Done.');
        }
      } catch (err) {
        status.textContent = 'Network error. Try again.';
      }
      sending = false;
      btn.disabled = false;
      btn.textContent = 'Record';
    }

    btn.addEventListener('click', async () => {
      if (sending) return;
      try {
        if (!recording) await start();
        else await stopAndSend();
      } catch (err) {
        status.textContent = 'Microphone permission needed.';
        recording = false;
        btn.classList.remove('hot');
        btn.textContent = 'Record';
      }
    });
  </script>
</body>
</html>
"""
