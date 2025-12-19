HTML_PAGE = b"""<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>TheraView Control</title>
    <style>
      :root {
        --bg: #0f172a;
        --panel: #111827;
        --card: #1f2937;
        --accent: #10b981;
        --warn: #f59e0b;
        --danger: #ef4444;
        --text: #e5e7eb;
        --muted: #9ca3af;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: radial-gradient(circle at 20% 20%, #1e293b 0, #0f172a 45%),
                    radial-gradient(circle at 80% 0%, #111827 0, #0f172a 40%);
        color: var(--text);
        min-height: 100vh;
      }

      .page {
        max-width: 1100px;
        margin: 0 auto;
        padding: 24px 18px 40px;
      }

      header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding: 16px 18px;
        background: var(--panel);
        border: 1px solid #1f2937;
        border-radius: 14px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
      }

      .title {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .title h1 {
        margin: 0;
        font-size: 24px;
        letter-spacing: 0.2px;
      }

      .title span {
        color: var(--muted);
        font-size: 14px;
      }

      .record-pill {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 10px 16px;
        border-radius: 999px;
        background: rgba(239, 68, 68, 0.12);
        color: var(--danger);
        font-weight: 700;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        border: 1px solid rgba(239, 68, 68, 0.25);
      }

      .record-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--danger);
        box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.18);
      }

      .grid {
        display: grid;
        grid-template-columns: 2fr 1fr;
        gap: 18px;
        margin-top: 18px;
      }

      .card {
        background: var(--card);
        border-radius: 14px;
        border: 1px solid #1f2937;
        padding: 16px;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
      }

      .preview img {
        width: 100%;
        border-radius: 12px;
        border: 1px solid #111827;
        object-fit: cover;
        background: black;
      }

      .controls {
        display: grid;
        gap: 12px;
      }

      button {
        font-size: 18px;
        padding: 15px 18px;
        border-radius: 12px;
        border: none;
        font-weight: 700;
        color: white;
        cursor: pointer;
        transition: transform 120ms ease, opacity 120ms ease;
      }

      button:active { transform: translateY(1px); }
      button:disabled { opacity: 0.6; cursor: not-allowed; }

      #rec_btn { background: linear-gradient(135deg, #ef4444, #dc2626); }
      #rec_btn.recovering { background: linear-gradient(135deg, #f59e0b, #d97706); }
      #rec_btn.off { background: linear-gradient(135deg, #10b981, #059669); }
      #exit_btn { background: linear-gradient(135deg, #4b5563, #1f2937); }
      #video_btn { background: linear-gradient(135deg, #2563eb, #1d4ed8); }

      .status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 12px;
        margin-top: 8px;
      }

      .status-item {
        padding: 12px 14px;
        border-radius: 12px;
        background: #111827;
        border: 1px solid #1f2937;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .label { color: var(--muted); font-size: 14px; text-transform: uppercase; letter-spacing: 0.4px; }
      .value { font-size: 18px; font-weight: 700; }

      .value.green { color: var(--accent); }
      .value.orange { color: var(--warn); }
      .value.red { color: var(--danger); }

      @media (max-width: 900px) {
        .grid { grid-template-columns: 1fr; }
        header { flex-direction: column; align-items: flex-start; }
        .record-pill { align-self: flex-start; }
      }
    </style>
  </head>
  <body>
    <div class=\"page\">
      <header>
        <div class=\"title\">
          <h1>TheraView Control</h1>
          <span>Monitor capture, recording, and device health</span>
        </div>
        <div id=\"rec_status\" class=\"record-pill\">
          <span class=\"record-dot\"></span>
          <span class=\"record-text\">Recording active</span>
        </div>
      </header>

      <div class=\"grid\">
        <div class=\"card preview\">
          <div class=\"label\">Live Preview</div>
          <img src=\"/stream\" alt=\"Live preview\" width=\"640\" height=\"480\">
          <div class=\"status-grid\" style=\"margin-top: 12px;\">
            <div class=\"status-item\">
              <div class=\"label\">Recording FPS</div>
              <div id=\"record_fps\" class=\"value\">--</div>
            </div>
            <div class=\"status-item\">
              <div class=\"label\">Preview FPS</div>
              <div id=\"preview_fps\" class=\"value\">--</div>
            </div>
          </div>
        </div>

        <div class=\"card controls\">
          <button id=\"rec_btn\" onclick=\"toggleRecord()\">Stop recording</button>
          <button id=\"video_btn\" onclick=\"toggleVideo()\">Stop video system</button>
          <button id=\"exit_btn\" onclick=\"exitServer()\">Exit</button>

          <div class=\"status-grid\">
            <div class=\"status-item\">
              <div class=\"label\">Current File</div>
              <div id=\"file_name\" class=\"value\">--</div>
            </div>
            <div class=\"status-item\">
              <div class=\"label\">Storage</div>
              <div id=\"mem_status\" class=\"value\">--</div>
            </div>
            <div class=\"status-item\">
              <div class=\"label\">Bluetooth Remote</div>
              <div id=\"bt_status\" class=\"value\">Checking...</div>
            </div>
            <div class=\"status-item\">
              <div class=\"label\">RTC Module</div>
              <div id=\"rtc_status\" class=\"value\">Checking...</div>
            </div>
            <div class=\"status-item\">
              <div class=\"label\">Video System</div>
              <div id=\"video_state\" class=\"value\">Starting...</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      function setRecordingState(recordingHealthy, recovering, controlsDisabled = false) {
        const pill = document.getElementById('rec_status');
        const text = pill.querySelector('.record-text');
        const btn = document.getElementById('rec_btn');

        pill.classList.remove('warn', 'off');

        if (recordingHealthy) {
          text.textContent = 'Recording active';
          btn.textContent = 'Stop recording';
          btn.classList.remove('recovering', 'off');
          pill.style.background = 'rgba(239, 68, 68, 0.12)';
          pill.style.borderColor = 'rgba(239, 68, 68, 0.25)';
        } else if (recovering) {
          text.textContent = 'Recording recovering...';
          btn.textContent = 'Recovering';
          btn.classList.add('recovering');
          btn.classList.remove('off');
          btn.disabled = true;
          pill.style.background = 'rgba(245, 158, 11, 0.12)';
          pill.style.borderColor = 'rgba(245, 158, 11, 0.35)';
        } else {
          text.textContent = 'Recording off';
          btn.textContent = 'Start recording';
          btn.classList.add('off');
          btn.classList.remove('recovering');
          btn.disabled = false;
          pill.style.background = 'rgba(16, 185, 129, 0.12)';
          pill.style.borderColor = 'rgba(16, 185, 129, 0.25)';
        }

        btn.disabled = recovering || controlsDisabled;
      }

      function setVideoState(enabled) {
        const videoBtn = document.getElementById('video_btn');
        const recBtn = document.getElementById('rec_btn');

        if (enabled) {
          setValue('video_state', 'Running', 'green');
          videoBtn.textContent = 'Stop video system';
          videoBtn.disabled = false;
          recBtn.disabled = recBtn.classList.contains('recovering');
        } else {
          setValue('video_state', 'Stopped', 'red');
          videoBtn.textContent = 'Start video system';
          videoBtn.disabled = false;
          recBtn.disabled = true;
        }
      }

      function setValue(id, value, colorClass) {
        const el = document.getElementById(id);
        el.textContent = value;
        el.classList.remove('green', 'orange', 'red');
        if (colorClass) el.classList.add(colorClass);
      }

      function updateMem() {
        fetch('/mem', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => setValue('mem_status', data.free_gb + ' GB free'));
      }

      function updateFilename() {
        fetch('/filename', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => {
            if (data.name) {
              const simple = data.name.split('/').pop();
              setValue('file_name', simple);
            } else {
              setValue('file_name', '--', 'orange');
            }
          });
      }

      function toggleRecord() {
        fetch('/toggle_record', { cache: 'no-store' })
          .then(() => setTimeout(updateStatus, 250));
      }

      function toggleVideo() {
        fetch('/toggle_video', { cache: 'no-store' })
          .then(() => setTimeout(updateStatus, 250));
      }

      function updateStatus() {
        fetch('/status', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => {
            const videoEnabled = data.pipelines_enabled !== false;
            setVideoState(videoEnabled);

            if (!videoEnabled) {
              setRecordingState(false, false, true);
              setValue('record_fps', '--', 'red');
              setValue('preview_fps', '--', 'red');
            }

            const recordingHealthy = videoEnabled && data.record_active && data.record_running !== false;
            const recovering = videoEnabled && data.record_active && data.record_running === false;

            setRecordingState(recordingHealthy, recovering, !videoEnabled);

            if (!data.available) {
              setValue('bt_status', 'Bluetooth remote not available', 'red');
            } else if (data.connected) {
              setValue('bt_status', 'Bluetooth remote connected', 'green');
            } else {
              setValue('bt_status', 'Bluetooth remote searching...', 'orange');
            }

            if (!data.rtc || !data.rtc.present) {
              setValue('rtc_status', 'RTC module not detected', 'red');
            } else if (data.rtc.time) {
              setValue('rtc_status', 'RTC time: ' + data.rtc.time, 'green');
            } else {
              setValue('rtc_status', 'RTC detected; time unavailable', 'orange');
            }

            if (videoEnabled && data.record_fps !== null && data.record_fps !== undefined) {
              setValue('record_fps', data.record_fps.toFixed(1) + ' fps');
            } else {
              setValue('record_fps', '--', videoEnabled ? 'orange' : 'red');
            }

            if (videoEnabled && data.preview_fps !== null && data.preview_fps !== undefined) {
              setValue('preview_fps', data.preview_fps.toFixed(1) + ' fps');
            } else {
              setValue('preview_fps', '--', videoEnabled ? 'orange' : 'red');
            }
          });
      }

      function exitServer() {
        fetch('/exit', { cache: 'no-store' })
          .then(() => alert('Server stopped'));
      }

      setInterval(updateStatus, 1500);
      setInterval(updateMem, 5000);
      setInterval(updateFilename, 2000);

      updateStatus();
      updateMem();
      updateFilename();
    </script>
  </body>
</html>"""
