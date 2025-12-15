// ================================
// 제어 로그 영역
// ================================
// ================================
// Control Logs (Pagination)
// ================================
const logBox = document.getElementById("log-box");
const pagerEl = document.getElementById("log-pagination");

let LOG_LIMIT = 25;
let LOG_PAGE = 1;          // 1부터
let LOG_GROUP_SIZE = 10;   // 한 번에 보일 페이지 버튼 개수(1~10, 11~20...)

// trigger_event / action_type 을 사람이 읽을 수 있는 문구로 바꾸는 헬퍼
function resolveActionLabelFromLog(log) {
  const trig = (log.trigger_event || "").toUpperCase();

  // AMR
  if (trig.endsWith("AMR_ESTOP"))   return "긴급 정지 (E-Stop)";
  if (trig.endsWith("AMR_RESTART")) return "운행 재개";

  // ARM
  if (trig.endsWith("ARM_ESTOP"))   return "긴급 정지 (E-Stop)";
  if (trig.endsWith("ARM_HOME"))    return "홈 포지션 복귀";
  if (trig.endsWith("ARM_RESTART")) return "운행 재개";

  // PLC
  if (trig.endsWith("PLC_OUTPUT_ON"))  return "출력 ON";
  if (trig.endsWith("PLC_OUTPUT_OFF")) return "출력 OFF";
  if (trig.endsWith("PLC_MANUAL_START")) return "수동 시작";

  // fallback
  return log.action_type || "명령";
}

function formatDateTimeYmdHms(iso) {
  const d = iso ? new Date(iso) : new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

// DB에서 받은 한 줄 로그를 log-box에 그리는 함수 (단일 정의)
function renderLogLineFromDb(log) {
  if (!logBox) return;

  const timeStr = formatDateTimeYmdHms(log.created_at);
  const targetLabel = log.target_type || "-";      // AMR / ARM / PLC
  const equipmentId = log.equipment_id || "";
  const ok = (log.result_status || "SUCCESS") === "SUCCESS";
  const actionLabel = resolveActionLabelFromLog(log);

  const line = document.createElement("div");
  line.className = "log-line";

  const spanTime = document.createElement("span");
  spanTime.className = "log-time";
  spanTime.textContent = timeStr;

  const spanTag = document.createElement("span");
  spanTag.className = "log-tag";
  spanTag.textContent = targetLabel;

  const spanMsg = document.createElement("span");
  spanMsg.className = "log-msg";

  const msgBase = equipmentId ? `[${equipmentId}] ${actionLabel}` : actionLabel;
  spanMsg.textContent = ok
    ? `${msgBase} 명령 전송 완료`
    : `${msgBase} 명령 전송 실패`;

  line.appendChild(spanTime);
  line.appendChild(spanTag);
  line.appendChild(spanMsg);

  logBox.appendChild(line);
}

function makePageBtn(label, page, disabled) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "log-page-btn";
  btn.textContent = label;
  btn.disabled = !!disabled;

  btn.addEventListener("click", async () => {
    LOG_PAGE = page;
    await loadControlLogsFromDb(); // 페이지 이동
  });

  return btn;
}

function buildPagination(total, currentPage) {
  if (!pagerEl) return;

  pagerEl.innerHTML = "";

  const totalPages = Math.max(1, Math.ceil(total / LOG_LIMIT));

  // 현재 페이지가 속한 "묶음" 계산 (1~10 / 11~20 ...)
  const groupIndex = Math.floor((currentPage - 1) / LOG_GROUP_SIZE);
  const startPage = groupIndex * LOG_GROUP_SIZE + 1;
  const endPage = Math.min(totalPages, startPage + LOG_GROUP_SIZE - 1);

  // « 첫페이지
  pagerEl.appendChild(makePageBtn("«", 1, currentPage === 1));

  // ‹ 이전 묶음
  const prevGroupPage = Math.max(1, startPage - LOG_GROUP_SIZE);
  pagerEl.appendChild(makePageBtn("‹", prevGroupPage, startPage === 1));

  // 숫자 버튼들
  for (let p = startPage; p <= endPage; p++) {
    const btn = makePageBtn(String(p), p, false);
    if (p === currentPage) btn.classList.add("is-active");
    pagerEl.appendChild(btn);
  }

  // 다음 묶음 ›
  const nextGroupPage = Math.min(totalPages, startPage + LOG_GROUP_SIZE);
  pagerEl.appendChild(makePageBtn("›", nextGroupPage, endPage === totalPages));

  // 마지막페이지 »
  pagerEl.appendChild(makePageBtn("»", totalPages, currentPage === totalPages));
}

async function loadControlLogsFromDb() {
  if (!logBox) return;

  const offset = (LOG_PAGE - 1) * LOG_LIMIT;

  try {
    const res = await fetch(`/api/v1/control/logs?source=WEB&limit=${LOG_LIMIT}&offset=${offset}`);
    if (!res.ok) throw new Error("HTTP " + res.status);

    // ✅ 페이징 응답 형태
    // { items: [...], paging: { total, limit, offset } }
    const data = await res.json();
    const logs = data.items || [];
    const paging = data.paging || { total: 0, limit: LOG_LIMIT, offset };

    logBox.innerHTML = "";

    if (!logs.length) {
      const empty = document.createElement("div");
      empty.className = "log-box-empty";
      empty.textContent = "아직 전송된 제어 명령이 없습니다.";
      logBox.appendChild(empty);
    } else {
      logs.forEach(renderLogLineFromDb);
    }

    buildPagination(paging.total || 0, LOG_PAGE);
  } catch (e) {
    console.error("[CONTROL LOGS] fetch error:", e);
  }
}




// ================================
// 제어 명령 전송 (백엔드 → control_logs INSERT용)
// ================================
async function sendCommand(target, payloadForLog = {}) {
  const { url, body, label, equipment_id } = payloadForLog;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }

    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error || "control api error");
    }

    console.log("[CONTROL OK]", target, body);

    // 🔥 성공하면 DB에서 최신 로그 다시 읽어와서 오른쪽 패널 전체 갱신
    await loadControlLogsFromDb();
    await refreshEquipmentStatus(); // ✅ status 갱신 반영
  } catch (e) {
    // 실패했을 때는 아직 DB 로그가 없을 수도 있으니, 기존 appendLog 로 임시 표시
    appendLog(target, payloadForLog.equipment_id, label, false);
    console.error("[CONTROL ERROR]", e);
  }
}

// ================================
// 동적 버튼 클릭 처리 (이벤트 위임)
// ================================
document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-target]");
  if (!btn) return;

  const target = btn.getAttribute("data-target");          // AMR / ROBOT / PLC
  const targetType = btn.getAttribute("data-target-type"); // AMR / ARM / PLC
  const actionKey = btn.getAttribute("data-action-key");   // ESTOP / RESUME / ...
  const actionType = btn.getAttribute("data-action-type"); // AGV_ESTOP / ARM_HOME ...
  const actionLabel = btn.getAttribute("data-action-label") || actionKey;
  const equipmentId = btn.getAttribute("data-equipment-id") || null;
  const extraRaw = btn.getAttribute("data-extra");
  let extra = {};
  if (extraRaw) {
    try {
      extra = JSON.parse(extraRaw);
    } catch (e) {
      console.warn("data-extra JSON parse error:", e);
    }
  }

  const urlMap = {
    AMR: "/api/v1/control/amr",
    ROBOT: "/api/v1/control/robot",
    PLC: "/api/v1/control/plc",
  };
  const url = urlMap[target] || "/api/v1/control/unknown";
  const triggerEvent = `USER_CLICK_${actionType}`.toUpperCase();

  // 서버로 보내는 payload
  const body = {
    equipment_id: equipmentId,
    target_type: targetType, // control_logs.target_type 에 매핑
    action_key: actionKey,   // 사람이 보기 좋은 키 (선택)
    action_type: actionType,
    trigger_event: triggerEvent,
  };

  sendCommand(target, {
    url,
    body,
    label: actionLabel,
    equipment_id: equipmentId,
  });
});

// ================================
// 장비 상태 조회 → 장비별 제어 UI 렌더링
// ================================

// equipment_type 별로 어디에, 어떤 버튼을 쓸지 설정
const CONTROL_CONFIG = {
  AMR: {
    containerId: "amr-control-list",
    target: "AMR",      // sendCommand target (로그용)
    targetType: "AMR",  // DB control_logs.target_type
    buttons: [
      {
        actionKey: "ESTOP",
        actionType: "AMR_ESTOP",         // DB control_logs.action_type
        label: "긴급 정지 (E-Stop)",
        style: "btn-danger",
        icon: "⛔",
      },
      {
        actionKey: "RESTART",
        actionType: "AMR_RESTART",
        label: "운행 재개",
        style: "btn-outline",
        icon: "▶",
      },
    ],
  },
  ARM: {
    containerId: "robot-control-list",
    target: "ROBOT",
    targetType: "ARM",
    buttons: [
      {
        actionKey: "ESTOP",
        actionType: "ARM_ESTOP",
        label: "긴급 정지 (E-Stop)",
        style: "btn-danger",
        icon: "⛔",
      },
      {
        actionKey: "HOME",
        actionType: "ARM_HOME",
        label: "홈 포지션 복귀",
        style: "btn-primary",
        icon: "🏠",
      },
      {
        actionKey: "RESTART",
        actionType: "ARM_RESTART",
        label: "운행 재개",
        style: "btn-outline",
        icon: "▶",
      },
    ],
  },
  // PLC: {
  //   containerId: "plc-control-list",
  //   target: "PLC",
  //   targetType: "PLC",
  //   buttons: [
  //     {
  //       actionKey: "OUTPUT_ON",
  //       actionType: "PLC_OUTPUT_ON",
  //       label: "출력 ON",
  //       style: "btn-primary",
  //       icon: "🔌",
  //       extra: { coil: "Y002" }, // 필요 시 data-extra 로 들어갈 값
  //     },
  //     {
  //       actionKey: "OUTPUT_OFF",
  //       actionType: "PLC_OUTPUT_OFF",
  //       label: "출력 OFF",
  //       style: "btn-outline",
  //       icon: "💤",
  //       extra: { coil: "Y002" },
  //     },
  //   ],
  // },
};

// 한 타입(AMR/ARM/PLC)에 대해 장비 리스트 렌더링
function renderEquipmentListForType(type, equipmentList) {
  const config = CONTROL_CONFIG[type];
  if (!config) return;

  const container = document.getElementById(config.containerId);
  if (!container) return;

  container.innerHTML = "";

  if (!equipmentList.length) {
    const empty = document.createElement("div");
    empty.className = "log-box-empty";
    empty.textContent = "등록된 장비가 없습니다.";
    container.appendChild(empty);
    return;
  }

  equipmentList.forEach(({ id, info }) => {
    const row = document.createElement("div");
    row.className = "equipment-row";
    row.dataset.equipmentId = id;

    // 상단: 장비 이름 / 위치 / 상태
    const statusRow = document.createElement("div");
    statusRow.className = "status-row";

    const nameSpan = document.createElement("span");
    const name = info.equipment_name || id;
    // const loc = info.location ? ` @ ${info.location}` : "";
    // nameSpan.textContent = `${name}${loc}`;
    nameSpan.textContent = `${name}`;

    const valueSpan = document.createElement("span");
    valueSpan.className = "value";
    const status = info.status || "UNKNOWN";
    valueSpan.textContent = status;

    if (!info.is_online) {
      valueSpan.classList.add("status-offline");
    }

    statusRow.appendChild(nameSpan);
    statusRow.appendChild(valueSpan);

    // 하단: 버튼 행
    const btnRow = document.createElement("div");
    btnRow.className = "btn-row";

    config.buttons.forEach((btnDef) => {
      const btn = document.createElement("button");
      btn.className = `control-btn ${btnDef.style}`;
      btn.setAttribute("data-target", config.target);             // AGV / ROBOT / PLC
      btn.setAttribute("data-target-type", config.targetType);    // AMR / ARM / PLC
      btn.setAttribute("data-action-key", btnDef.actionKey);      // ESTOP / HOME ...
      btn.setAttribute("data-action-type", btnDef.actionType);    // AGV_ESTOP ...
      btn.setAttribute("data-action-label", btnDef.label);
      btn.setAttribute("data-equipment-id", id);

      if (btnDef.extra) {
        btn.setAttribute("data-extra", JSON.stringify(btnDef.extra));
      }

      const iconSpan = document.createElement("span");
      iconSpan.className = "icon";
      iconSpan.textContent = btnDef.icon;

      const labelNode = document.createTextNode(" " + btnDef.label);

      btn.appendChild(iconSpan);
      btn.appendChild(labelNode);

      btnRow.appendChild(btn);
    });

    row.appendChild(statusRow);
    row.appendChild(btnRow);

    container.appendChild(row);
  });
}

// 전체 장비 상태 조회 후 타입별로 분배해서 렌더링
async function refreshEquipmentStatus() {
  try {
    const res = await fetch("/api/v1/control/equipment/status");
    if (!res.ok) throw new Error("HTTP " + res.status);

    const data = await res.json();
    // data: { "AMR01": {...}, "AMR02": {...}, "ARM01": {...}, ... }

    const buckets = {
      AMR: [],
      ARM: [],
      PLC: [],
    };

    Object.entries(data).forEach(([id, info]) => {
      const type = info.equipment_type;
      if (!buckets[type]) return; // AMR/ARM/PLC만
      buckets[type].push({ id, info });
    });

    Object.entries(buckets).forEach(([type, list]) => {
      renderEquipmentListForType(type, list);
    });
  } catch (err) {
    console.error("[equipment status] fetch error:", err);
  }
}


const PLC_EQUIPMENT_ID = "CONVEYOR01"; // 너 환경에 맞게

async function manualStartPlc() {
  const res = await fetch("/api/v1/control/plc/manual_start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      equipment_id: PLC_EQUIPMENT_ID,
      trigger_event: "USER_CLICK_PLC_MANUAL_START",
    }),
  });

  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  if (data.ok === false) throw new Error(data.error || "manual_start fail");
  return data;
}

async function savePlcState(patch) {
  const res = await fetch("/api/v1/control/plc/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      equipment_id: PLC_EQUIPMENT_ID,
      ...patch,
    }),
  });

  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();

  // 만약 너가 리스트/ok 형태를 섞었다면 여기 맞춰야 함
  if (data.ok === false) throw new Error(data.error || "api error");

  return data; // {ok:true, data:{...}} 형태라고 가정
}

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-plc-action]");
  if (!btn) return;

  const action = btn.dataset.plcAction;

  try {
    // ✅ 좌측: 클릭 즉시 반영
    if (action === "RUN_MODE") {
      const runMode = btn.dataset.runMode;

      // MANUAL을 모델에서 뺐으면 여기서 막아야 함
      if (runMode === "MANUAL") {
        console.warn("MANUAL은 DB 저장 대상에서 제외됨");
        return;
      }

      await savePlcState({ run_mode: runMode });
      await loadPlcStateToUi(); // 저장 후 UI 다시 동기화
      return;
    }

    if (action === "DIRECTION") {
      const direction = btn.dataset.direction;
      await savePlcState({ direction });
      await loadPlcStateToUi();
      return;
    }

    if (action === "MANUAL_START") {
      await manualStartPlc();
      // 필요하면 로그 갱신만(선택)
      await loadControlLogsFromDb?.();
      return;
    }

    // ✅ 우측: 변경 적용 버튼 누를 때만 저장
    if (action === "APPLY_PARAMS") {
      const freqEl = document.getElementById("plc-frequency");
      const accEl  = document.getElementById("plc-acceleration");
      const decEl  = document.getElementById("plc-deceleration");

      const patch = {
        frequency: freqEl ? freqEl.value : null,
        acceleration: accEl ? accEl.value : null,
        deceleration: decEl ? decEl.value : null,
      };

      await savePlcState(patch);
      await loadPlcStateToUi();
      return;
    }
  } catch (e) {
    console.error("[PLC_STATE] update fail:", e);
  }
});

async function loadPlcStateToUi() {
  try {
    const res = await fetch(`/api/v1/control/plc/state?equipment_id=${encodeURIComponent(PLC_EQUIPMENT_ID)}`);
    if (!res.ok) throw new Error("HTTP " + res.status);

    const rows = await res.json(); // ✅ 지금은 배열
    if (!rows.length) return;

    const s = rows[0];

    // input 값 반영
    const freqEl = document.getElementById("plc-frequency");
    const accEl  = document.getElementById("plc-acceleration");
    const decEl  = document.getElementById("plc-deceleration");

    if (freqEl) freqEl.value = (s.frequency ?? "");
    if (accEl)  accEl.value  = (s.acceleration ?? "");
    if (decEl)  decEl.value  = (s.deceleration ?? "");

    // run_mode 버튼 처리
    document.querySelectorAll("[data-run-mode]").forEach(btn => {
      const isActive = btn.dataset.runMode === s.run_mode;
      btn.classList.toggle("is-inactive", !isActive);
    });

    // direction 버튼 처리
    document.querySelectorAll("[data-direction]").forEach(btn => {
      const isActive = btn.dataset.direction === s.direction;
      btn.classList.toggle("is-inactive", !isActive);
    });

  } catch (e) {
    console.error("[PLC_STATE] load failed:", e);
  }
}

// 페이지 로드 시 호출
loadPlcStateToUi();

// 페이지 로드 시 한 번 상태 불러와서 장비별 제어 UI 렌더링
refreshEquipmentStatus();
loadControlLogsFromDb();
