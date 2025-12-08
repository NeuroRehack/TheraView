HTML_PAGE = b"""
<html>
  <body style="font-family: sans-serif; margin: 0; padding: 0; text-align: center;">

    <div style="margin-top: 20px;">
      <img src="/stream" width="640" height="480"
        style="object-fit: cover; border: 2px solid black; max-width: 95vw; height: auto;">
    </div>

    <br>

    <div id="rec_status" style="font-size: 28px; font-weight: bold; color: red;">
      Recording active
    </div>

    <div id="file_name" style="font-size: 22px; margin-top: 8px; color: black;">
    </div>

    <br>

    <button id="rec_btn"
      style="
        font-size: 34px;
        padding: 24px 50px;
        width: 80vw;
        max-width: 420px;
        border-radius: 14px;
      "
      onclick="toggleRecord()">
      Stop recording
    </button>

    <br><br>

    <button
      onclick="exitServer()"
      style="
        font-size: 30px;
        padding: 20px 45px;
        width: 75vw;
        max-width: 380px;
        border-radius: 14px;
        background-color: #333;
        color: white;
      "
    >
      Exit
    </button>

    <br><br>

    <div id="mem_status" style="font-size: 20px; margin-top: 8px; color: gray;">
    </div>

    <div id="bt_status" style="font-size: 18px; margin-top: 6px; color: gray;">
      Bluetooth: checking...
    </div>

    <script>
      function updateMem() {
        fetch('/mem', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => {
            document.getElementById("mem_status").innerText =
              data.free_gb + " GB free";
          });
      }

      function updateFilename() {
        fetch('/filename', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => {
            if (data.name) {
              const simple = data.name.split('/').pop();
              document.getElementById("file_name").innerText = simple;
            } else {
              document.getElementById("file_name").innerText = "";
            }
          });
      }

      function toggleRecord() {
        fetch('/toggle_record', { cache: 'no-store' })
          .then(() => setTimeout(updateStatus, 250));
      }

      function updateStatus() {
        fetch('/status', { cache: 'no-store' })
          .then(r => r.json())
          .then(data => {
            const s = document.getElementById("rec_status");
            const b = document.getElementById("rec_btn");
            const bt = document.getElementById("bt_status");

            if (data.record_active) {
              s.innerText = "Recording active";
              s.style.color = "red";
              b.innerText = "Stop recording";
            } else {
              s.innerText = "Recording off";
              s.style.color = "gray";
              b.innerText = "Start recording";
            }

            if (!data.available) {
              bt.innerText = "Bluetooth remote not available";
              bt.style.color = "darkred";
            } else if (data.connected) {
              bt.innerText = "Bluetooth remote connected";
              bt.style.color = "green";
            } else {
              bt.innerText = "Bluetooth remote searching...";
              bt.style.color = "orange";
            }
          });
      }

      function exitServer() {
        fetch('/exit', { cache: 'no-store' })
          .then(() => {
            alert("Server stopped");
          });
      }

      setInterval(updateStatus, 1500);
      setInterval(updateMem, 5000);
      setInterval(updateFilename, 2000);

      updateStatus();
      updateMem();
      updateFilename();
    </script>

  </body>
</html>
"""
