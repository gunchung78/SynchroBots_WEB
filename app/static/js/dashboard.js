function refreshAgvMap() {
  const el = document.getElementById("agv-map-bg");
  if (!el) return;

  const ts = Date.now();
  el.style.backgroundImage = `url("/api/v1/map-image?t=${ts}")`;
}

document.addEventListener("DOMContentLoaded", () => {
  refreshAgvMap();
  initCharts();
  renderMissions();
  renderEvents();
  loadControlLogs();
});

// -------------------- Mock 데이터 --------------------
const eventLogs = [
  { time: "10:21:03", device_id: "AGV03", device_type: "AGV", level: "ERR",  message: "경로 이탈 감지 · 속도 자동 감속" },
  { time: "10:20:11", device_id: "ARM01", device_type: "ARM", level: "INFO", message: "픽업 완료 · 다음 공정으로 이송" },
  { time: "10:19:44", device_id: "PLC01", device_type: "PLC", level: "INFO", message: "센서 IN_07 ON (팔레트 감지)" },
  { time: "10:18:22", device_id: "AGV01", device_type: "AGV", level: "WARN", message: "충돌 가능 구역 진입 · 감속" },
  { time: "10:17:01", device_id: "ARM02", device_type: "ARM", level: "ERR",  message: "그리퍼 미채결 · 재시도 필요" },
  { time: "10:16:33", device_id: "PLC01", device_type: "PLC", level: "WARN", message: "비상 스위치 ON 입력 감지" },
  { time: "10:15:25", device_id: "AGV02", device_type: "AGV", level: "INFO", message: "미션 #12 완료 · ST-03 도착" },
  { time: "10:14:10", device_id: "ARM01", device_type: "ARM", level: "INFO", message: "홈 포지션 복귀 완료" },
  { time: "10:13:52", device_id: "HMI01", device_type: "HMI", level: "INFO", message: "오퍼레이터 로그인(김**)" },
  { time: "10:12:18", device_id: "PLC01", device_type: "PLC", level: "INFO", message: "라인 기동 시퀀스 시작" }
];

const missionLogs = [
  { mission_id: "AGV-12", device_id: "AGV01", status: "RUNNING", step: "MOVE_TO_ST-03",  created_at: "10:20:30" },
  { mission_id: "AGV-11", device_id: "AGV02", status: "DONE",    step: "COMPLETED",      created_at: "10:18:05" },
  { mission_id: "ARM-05", device_id: "ARM01", status: "DONE",    step: "PLACE_DONE",     created_at: "10:19:10" },
  { mission_id: "ARM-06", device_id: "ARM02", status: "ERROR",   step: "PICK_RETRY",     created_at: "10:17:02" },
  { mission_id: "SYS-BOOT", device_id: "PLC01", status: "DONE",  step: "SEQUENCE_OK",    created_at: "10:12:00" }
];

const classifyStats = [
  { category: "Zone A", count: 24 },
  { category: "Zone B", count: 18 },
  { category: "Zone C", count: 12 },
  { category: "Reject", count: 3 },
];

const successRateLogs = [
  { label: "10:00", rate: 82 },
  { label: "10:10", rate: 85 },
  { label: "10:20", rate: 80 },
  { label: "10:30", rate: 88 },
  { label: "10:40", rate: 90 },
  { label: "10:50", rate: 92 },
];

// -------------------- Chart 초기화 --------------------
function initCharts() {
  const classifyCanvas = document.getElementById("classifyChart");
  const successCanvas  = document.getElementById("successChart");

  if (!classifyCanvas || !successCanvas) {
    // 다른 템플릿에서 dashboard.js를 불러도 에러 안 나게 방어
    return;
  }

  const classifyCtx = classifyCanvas.getContext("2d");
  const successCtx  = successCanvas.getContext("2d");

  new Chart(classifyCtx, {
    type: "bar",
    data: {
      labels: classifyStats.map((c) => c.category),
      datasets: [
        {
          data: classifyStats.map((c) => c.count),
          borderWidth: 1,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      responsive: false,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: "#9ca3af", font: { size: 10 } },
          grid: { color: "rgba(148,163,184,0.25)" },
        },
        x: {
          ticks: { color: "#9ca3af", font: { size: 10 } },
          grid: { display: false },
        },
      },
    },
  });

  new Chart(successCtx, {
    type: "line",
    data: {
      labels: successRateLogs.map((s) => s.label),
      datasets: [
        {
          data: successRateLogs.map((s) => s.rate),
          borderWidth: 1,
          tension: 0.3,
          fill: false,
        },
      ],
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `성공률: ${ctx.parsed.y}%`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: "#9ca3af", font: { size: 10 } },
          grid: { color: "rgba(148,163,184,0.25)" },
        },
        x: {
          ticks: { color: "#9ca3af", font: { size: 10 } },
          grid: { display: false },
        },
      },
    },
  });
}

// -------------------- 미션 렌더링 --------------------
function renderMissions() {
  const missionList = document.getElementById("mission-list");
  if (!missionList) return;

  missionLogs.forEach(m => {
    const item = document.createElement("div");
    item.className = "mission-item";

    const main = document.createElement("div");
    main.className = "mission-main";

    const id = document.createElement("div");
    id.className = "mission-id";
    id.textContent = `${m.device_id} · ${m.mission_id}`;

    const meta = document.createElement("div");
    meta.className = "mission-meta";
    meta.textContent = `단계: ${m.step} / 시작: ${m.created_at}`;

    main.appendChild(id);
    main.appendChild(meta);

    const st = document.createElement("div");
    st.className =
      "status-pill " +
      (m.status === "RUNNING"
        ? "status-running"
        : m.status === "DONE"
        ? "status-done"
        : "status-error");
    st.textContent = m.status;

    item.appendChild(main);
    item.appendChild(st);
    missionList.appendChild(item);
  });
}

// -------------------- 이벤트 렌더링 --------------------
function createEventRow(e) {
  const row = document.createElement("div");
  row.className = "log-row";

  const colTime = document.createElement("span");
  colTime.textContent = e.time;

  const colDevice = document.createElement("span");
  colDevice.textContent = e.device_id;

  const colMsg = document.createElement("span");

  const tag = document.createElement("span");
  tag.className = "log-tag";
  tag.textContent = e.device_type;

  const level = document.createElement("span");
  level.className =
    "log-level " +
    (e.level === "ERR"
      ? "lvl-err"
      : e.level === "WARN"
      ? "lvl-warn"
      : "lvl-info");
  level.textContent = e.level;

  const text = document.createElement("span");
  text.textContent = "  " + e.message;

  colMsg.appendChild(tag);
  colMsg.appendChild(level);
  colMsg.appendChild(text);

  row.appendChild(colTime);
  row.appendChild(colDevice);
  row.appendChild(colMsg);
  return row;
}

function renderEvents() {
  const eventsTable = document.getElementById("events-table");
  if (!eventsTable) return;

  eventLogs.forEach(e => {
    eventsTable.appendChild(createEventRow(e));
  });
}

// -------------------- 제어 로그(API) --------------------
function createControlRow(c) {
  const row = document.createElement("div");
  row.className = "log-row";

  // 1) 시간
  const colTime = document.createElement("span");
  const timeStr = c.created_at ? c.created_at.slice(11, 19) : "";
  colTime.textContent = timeStr;

  // 2) 대상 (장비 이름 우선, 없으면 ID)
  const colTarget = document.createElement("span");
  let deviceLabel = c.equipment_id || "-";
  if (c.equipment && c.equipment.equipment_name) {
    deviceLabel = c.equipment.equipment_name;
  }
  colTarget.textContent = deviceLabel;

  // 3) 출처 / 대상구분 (WEB / AMR 형태)
  const colSrcType = document.createElement("span");
  const source = c.source || "-";          // WEB / API / SCRIPT
  const ttype  = c.target_type || "";      // AMR / ARM / PLC / SYSTEM
  colSrcType.textContent = ttype ? `${source} / ${ttype}` : source;

  // 4) 결과 뱃지 (SUCCESS / FAIL / TIMEOUT)
  const colResult = document.createElement("span");
  const resultSpan = document.createElement("span");
  const result = c.result_status || "SUCCESS";
  resultSpan.className =
    "log-level " +
    (result === "SUCCESS"
      ? "lvl-info"
      : result === "FAIL"
      ? "lvl-err"
      : "lvl-warn");
  resultSpan.textContent = result;
  colResult.appendChild(resultSpan);

  // 5) 내용 (명령 + operator + payload + result_message)
  const colDetail = document.createElement("span");

  const detailParts = [];

  if (c.action_type) {
    detailParts.push(c.action_type);              // ex) amr_go_move, ROBOT_HOME...
  }
  if (c.request_payload) {
    detailParts.push(c.request_payload);          // JSON 문자열
  }
  if (c.result_message) {
    detailParts.push(c.result_message);           // 에러/설명 메시지
  }

  colDetail.textContent = detailParts.join(" · ");

  // 5개 컬럼 순서대로 추가
  row.appendChild(colTime);    // 시간
  row.appendChild(colTarget);  // 대상
  row.appendChild(colSrcType); // 출처 / 대상구분
  row.appendChild(colResult);  // 결과
  row.appendChild(colDetail);  // 내용

  return row;
}

async function loadControlLogs() {
  const controlTable = document.getElementById("control-table");
  if (!controlTable) return;

  while (controlTable.children.length > 1) {
    controlTable.removeChild(controlTable.lastChild);
  }

  try {
    const res = await fetch("/api/v1/control-logs?limit=10");
    if (!res.ok) {
      console.error("failed to fetch control-logs", res.status);
      return;
    }
    const data = await res.json();
    const items = data.items || [];

    items.forEach(c => {
      controlTable.appendChild(createControlRow(c));
    });
  } catch (err) {
    console.error("error loading control-logs", err);
  }
}
