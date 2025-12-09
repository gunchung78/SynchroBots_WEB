 const logBox = document.getElementById("log-box");

    function appendLog(target, action, ok = true) {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      const ss = String(now.getSeconds()).padStart(2, "0");
      const time = `${hh}:${mm}:${ss}`;

      if (logBox.querySelector(".log-box-empty")) {
        logBox.innerHTML = "";
      }

      const line = document.createElement("div");
      line.className = "log-line";

      const spanTime = document.createElement("span");
      spanTime.className = "log-time";
      spanTime.textContent = time;

      const spanTag = document.createElement("span");
      spanTag.className = "log-tag";
      spanTag.textContent = ok ? `${target}` : `${target} ERR`;

      const spanMsg = document.createElement("span");
      spanMsg.className = "log-msg";
      spanMsg.textContent = ok
        ? `${action} 명령 전송 완료`
        : `${action} 명령 전송 실패`;

      line.appendChild(spanTime);
      line.appendChild(spanTag);
      line.appendChild(spanMsg);

      logBox.prepend(line);
    }

    async function sendCommand(target, action, extra = {}) {
      const urlMap = {
        AGV: "/api/v1/control/agv",
        ROBOT: "/api/v1/control/robot",
        PLC: "/api/v1/control/plc",
      };
      const url = urlMap[target] || "/api/v1/control/unknown";
      const payload = { action, ...extra };

      try {
        // 실제 연동 시 fetch 로직 연결
        /*
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        */
        appendLog(target, action, true);
      } catch (e) {
        appendLog(target, action, false);
        console.error(e);
      }
    }

    // 버튼 이벤트 바인딩
    document.querySelectorAll("button[data-target]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.getAttribute("data-target");
        const action = btn.getAttribute("data-action");
        const extraRaw = btn.getAttribute("data-extra");
        let extra = {};
        if (extraRaw) {
          try { extra = JSON.parse(extraRaw); } catch (e) {}
        }
        sendCommand(target, action, extra);
      });
    });