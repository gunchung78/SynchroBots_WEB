function refreshAgvMap() {
  const el = document.getElementById("agv-map-bg");
  if (!el) return;

  const ts = Date.now();
  el.style.backgroundImage = `url("/api/v1/dashboard/map-image?t=${ts}")`;
}

document.addEventListener("DOMContentLoaded", async () => {
  initDashboardStream()
  // 맵 배경 / 메타 / AMR 상태
  refreshAgvMap();
  // await loadMapMeta();
  // await loadAmrStates();

  // 기존 기능들
  initCharts();
  // loadMissionLogs();
  // loadEvents();
  // loadControlLogs();

});

function initDashboardStream() {
  const es = new EventSource("/api/v1/dashboard/stream");

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const { type, payload } = data;

      if (type === "hello") {
        console.log("[SSE] connected:", payload);
        return;
      }

      if (type === "tick") {
        // 🔁 여기서 주기적으로 최신 데이터 재요청
        //    (필요한 것만 골라서 호출해도 됨)
        loadAmrStates();    // AGV 위치 재렌더
        loadEvents();       // 이벤트 로그 최신화
        loadControlLogs();  // 제어 로그 최신화
        loadMissionLogs();  // 미션 로그 최신화
        return;
      }

      console.warn("[SSE] unknown type:", type, data);
    } catch (err) {
      console.error("[SSE] parse error", err, event.data);
    }
  };

  es.onerror = (err) => {
    console.error("[SSE] error", err);
    // 브라우저가 자동 재연결 시도하니까 보통은 그냥 로그만
  };
}


// -------------------- Mock 데이터 --------------------
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


// -------------------- 이벤트 렌더링 --------------------
function createEventRow(e) {
  const row = document.createElement("div");
  row.className = "log-row";

  // 1) 시간
  const colTime = document.createElement("span");
  const timeStr = e.created_at ? e.created_at.slice(11, 19) : "";
  colTime.textContent = timeStr;

  // 2) 장비 (이름 우선, 없으면 ID)
  const colDevice = document.createElement("span");
  let label = e.equipment_id || "-";
  if (e.equipment && e.equipment.equipment_name) {
    label = e.equipment.equipment_name;
  }
  colDevice.textContent = label;

  // 3) TYPE (AGV / ARM / PLC / HMI)
  const colType = document.createElement("span");
  const typeSpan = document.createElement("span");
  typeSpan.className = "log-tag";          // 타입 칩 스타일 주고 싶으면 CSS에서 .log-tag 재사용
  typeSpan.textContent = e.equipment_type || "";
  colType.appendChild(typeSpan);

  // 4) LEVEL (INFO / WARN / ERR)
  const colLevel = document.createElement("span");
  const levelSpan = document.createElement("span");
  const level = e.level || "INFO";
  levelSpan.className =
    "log-level " +
    (level === "ERR"
      ? "lvl-err"
      : level === "WARN"
      ? "lvl-warn"
      : "lvl-info");
  levelSpan.textContent = level;
  colLevel.appendChild(levelSpan);

  // 5) 내용 (message)
  const colMsg = document.createElement("span");
  colMsg.textContent = e.message || "";

  // 순서대로 5개 컬럼 추가
  row.appendChild(colTime);   // 시간
  row.appendChild(colDevice); // 장비
  row.appendChild(colType);   // TYPE
  row.appendChild(colLevel);  // LEVEL
  row.appendChild(colMsg);    // 내용

  return row;
}
let lastEventsJson = null;

async function loadEvents() {
  const eventsTable = document.getElementById("events-table");
  if (!eventsTable) return;

  try {
    const res = await fetch("/api/v1/dashboard/events_logs?limit=10");
    if (!res.ok) {
      console.error("failed to fetch events", res.status);
      return;
    }
    const data = await res.json();
    const items = data.items || [];

    // 🔍 1) 직전 데이터와 완전 동일하면 DOM 갱신 스킵
    const newJson = JSON.stringify(items);
    if (newJson === lastEventsJson) {
      // console.log("[events] no change, skip render");
      return;
    }
    lastEventsJson = newJson;

    // 🔁 2) 바뀐 경우에만 DOM 다시 그림
    // 헤더를 제외하고 기존 행 제거
    while (eventsTable.children.length > 1) {
      eventsTable.removeChild(eventsTable.lastChild);
    }

    const frag = document.createDocumentFragment();
    items.forEach(ev => {
      frag.appendChild(createEventRow(ev));
    });
    eventsTable.appendChild(frag);

  } catch (err) {
    console.error("error loading events", err);
  }
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

let lastControlJson = null;
async function loadControlLogs() {
  const controlTable = document.getElementById("control-table");
  if (!controlTable) return;

  try {
    const res = await fetch("/api/v1/dashboard/control_logs?limit=10");
    if (!res.ok) {
      console.error("failed to fetch control-logs", res.status);
      return;
    }

    const data = await res.json();
    const items = data.items || [];

    // 🔍 1) 이전 데이터와 동일하면 렌더 스킵
    const newJson = JSON.stringify(items);
    if (newJson === lastControlJson) {
      // console.log("[control] no change, skip render");
      return;
    }
    lastControlJson = newJson;

    // 🔁 2) 변경된 경우에만 DOM 갱신
    // 헤더를 제외하고 기존 행 제거
    while (controlTable.children.length > 1) {
      controlTable.removeChild(controlTable.lastChild);
    }

    const frag = document.createDocumentFragment();
    items.forEach(c => {
      frag.appendChild(createControlRow(c));
    });
    controlTable.appendChild(frag);

  } catch (err) {
    console.error("error loading control-logs", err);
  }
}

// -------------------- 미션 렌더링 (API) --------------------

function createMissionItem(m) {
  const item = document.createElement("div");
  item.className = "mission-item";

  const main = document.createElement("div");
  main.className = "mission-main";

  // 장비 라벨: equipment_name · equipment_id
  const id = document.createElement("div");
  id.className = "mission-id";

  let equipmentLabel = m.equipment_id || "-";
  if (m.equipment && m.equipment.equipment_name) {
    equipmentLabel = `${m.equipment.equipment_name} · ${m.equipment_id}`;
  }
  id.textContent = equipmentLabel;

  // 단계 + 시작시간
  const meta = document.createElement("div");
  meta.className = "mission-meta";

  const stepText = m.description || "-";
  const timeStr = m.created_at ? m.created_at.slice(11, 19) : "";
  meta.textContent = `단계: ${stepText} / 시작: ${timeStr}`;

  main.appendChild(id);
  main.appendChild(meta);

  // 상태 뱃지
  const st = document.createElement("div");
  const status = m.status || "INFO";
  st.className =
    "status-pill " +
    (status === "RUNNING"
      ? "status-running"
      : status === "DONE"
      ? "status-done"
      : "status-error");
  st.textContent = status;

  item.appendChild(main);
  item.appendChild(st);

  return item;
}

// -------------------- 미션 로그 로딩 --------------------
let lastMissionJson = null;
async function loadMissionLogs() {
  const missionList = document.getElementById("mission-list");
  if (!missionList) return;

  try {
    const res = await fetch("/api/v1/dashboard/mission_logs?limit=5");
    if (!res.ok) {
      console.error("failed to fetch mission_logs", res.status);
      return;
    }

    const data = await res.json();
    const items = data.items || [];

    // 🔍 1) 이전 데이터와 동일하면 렌더 스킵
    const newJson = JSON.stringify(items);
    if (newJson === lastMissionJson) {
      // console.log("[mission] no change, skip render");
      return;
    }
    lastMissionJson = newJson;

    // 🔁 2) 변경된 경우에만 DOM 갱신
    while (missionList.firstChild) {
      missionList.removeChild(missionList.firstChild);
    }

    const frag = document.createDocumentFragment();
    items.forEach(m => {
      frag.appendChild(createMissionItem(m));
    });
    missionList.appendChild(frag);

  } catch (err) {
    console.error("error loading mission_logs", err);
  }
}

// ================== AGV 맵 관련 ==================

// 백엔드에서 내려주는 맵 메타데이터 캐싱
let MAP_META = null;

// 맵 이미지 새로고침 (배경)
function refreshAgvMap() {
  const el = document.getElementById("agv-map-bg");
  if (!el) return;

  const ts = Date.now();
  el.style.backgroundImage = `url("/api/v1/dashboard/map-image?t=${ts}")`;
}

// map-meta 로딩
async function loadMapMeta() {
  try {
    const res = await fetch("/api/v1/dashboard/map-meta");
    if (!res.ok) {
      console.error("failed to fetch map-meta", res.status);
      return;
    }
    MAP_META = await res.json();
    // console.log("MAP_META:", MAP_META);
  } catch (err) {
    console.error("error loading map-meta", err);
  }
}

let lastAmrJson = null;

// AMR 상태 로딩
async function loadAmrStates() {
  if (!MAP_META) {
    await loadMapMeta();
  }
  try {
    const res = await fetch("/api/v1/dashboard/amr_states");
    if (!res.ok) {
      console.error("failed to fetch amr_states", res.status);
      return;
    }

    const data = await res.json();
    const items = data.items || [];

    const newJson = JSON.stringify(items);
    if (newJson === lastAmrJson) {
      // console.log("[amr] no change, skip render");
      return;
    }
    lastAmrJson = newJson;

    // 🔋 상태 박스 갱신
    updateAgvStatus(items);

    drawAmrMarkers(items);
  } catch (err) {
    console.error("error loading amr_states", err);
  }
}

// AMR 상태 박스 렌더링
function updateAgvStatus(states) {
  const list = document.getElementById("agv-status-list");
  if (!list) return;

  // 일단 전부 지우고 다시 그림
  while (list.firstChild) {
    list.removeChild(list.firstChild);
  }

  const frag = document.createDocumentFragment();

  states.forEach((s) => {
    const item = document.createElement("div");
    item.className = "status-item";

    // ----- 왼쪽 라벨 영역 -----
    const labelWrap = document.createElement("div");
    labelWrap.className = "status-label";

    // 장비 이름 (있으면 이름, 없으면 ID)
    let name = s.equipment_id || "-";
    if (s.equipment && s.equipment.equipment_name) {
      name = s.equipment.equipment_name;
    }

    // 상태 코드에 따른 색상
    const stateCode = (s.state_code || "").toUpperCase();
    let dotClass = "green";   // 기본: 정상

    if (stateCode === "IDLE" || stateCode === "WAIT") {
      dotClass = "yellow";
    } else if (
      stateCode === "ERR" ||
      stateCode === "ERROR" ||
      stateCode === "ALARM"
    ) {
      dotClass = "red";
    }

    const dot = document.createElement("span");
    dot.className = `dot ${dotClass}`;

    const nameSpan = document.createElement("span");
    nameSpan.textContent = `${name} 상태`;

    labelWrap.appendChild(dot);
    labelWrap.appendChild(nameSpan);

    // ----- 오른쪽 값 영역 -----
    const value = document.createElement("div");
    value.className = "status-value";

    const detailParts = [];

    // 상태 코드 → 한글 설명 (필요하면 나중에 더 매핑)
    if (stateCode === "MOVE" || stateCode === "RUN") {
      detailParts.push("정상 주행");
    } else if (stateCode === "IDLE" || stateCode === "WAIT") {
      detailParts.push("대기");
    } else if (stateCode === "ERR" || stateCode === "ERROR" || stateCode === "ALARM") {
      detailParts.push("오류 / 알람");
    } else if (stateCode) {
      detailParts.push(stateCode);
    }

    if (typeof s.battery_pct === "number") {
      detailParts.push(`배터리 ${s.battery_pct.toFixed(0)}%`);
    }
    if (typeof s.speed === "number") {
      detailParts.push(`속도 ${s.speed.toFixed(2)} m/s`);
    }

    value.textContent = detailParts.join(" · ");

    // ----- 합치기 -----
    item.appendChild(labelWrap);
    item.appendChild(value);
    frag.appendChild(item);
  });

  list.appendChild(frag);
}

// AMR 마커 렌더링
function drawAmrMarkers(states) {
  const meta = MAP_META;
  if (!meta) return;

  const wrap = document.querySelector(".agv-path");
  if (!wrap) {
    console.warn("drawAmrMarkers: .agv-path not found");
    return;
  }

  const displayW = wrap.clientWidth;
  const displayH = wrap.clientHeight;

  const origin_x   = parseFloat(meta.origin_x);
  const origin_y   = parseFloat(meta.origin_y);
  const resolution = parseFloat(meta.resolution);
  const img_width  = parseFloat(meta.img_width);
  const img_height = parseFloat(meta.img_height);
  const crop_x_min = parseFloat(meta.crop_x_min);
  const crop_y_min = parseFloat(meta.crop_y_min);
  const crop_w     = parseFloat(meta.crop_w);
  const crop_h     = parseFloat(meta.crop_h);

  if (!resolution || !crop_w || !crop_h) {
    console.warn("drawAmrMarkers: invalid meta (resolution/crop_w/crop_h)");
    return;
  }

  // 기존 마커 제거
  while (wrap.firstChild) {
    wrap.removeChild(wrap.firstChild);
  }
  // drawAmrMarkers(states) 안에서, forEach 위쪽에 추가
  const DEG = 75;  // 일단 0으로 두고, 나중에 -5, +5 등으로 조절
  const theta = DEG * Math.PI / 180;
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);

  // 회전 기준점: 현재 AMR 위치들의 평균(중심)
  let avgX = 0;
  let avgY = 0;
  if (states.length > 0) {
    states.forEach((s) => {
      avgX += s.pos_x;
      avgY += s.pos_y;
    });
    avgX /= states.length;
    avgY /= states.length;
  }
  states.forEach((s, idx) => {
    // ===== 0) 월드 좌표에서 기준점(평균) 기준으로 이동 =====
    const wx = s.pos_x - avgX;
    const wy = s.pos_y - avgY;

    // ===== 1) 회전 보정 (기준점 기준 회전) =====
    const rx_local = wx * cosT - wy * sinT;
    const ry_local = wx * sinT + wy * cosT;

    // 다시 월드 좌표로 되돌리기
    const rx = rx_local + avgX;
    const ry = ry_local + avgY;

    // ===== 2) 회전된 좌표 → 이미지 픽셀 변환 =====
    const px = (rx - origin_x) / resolution;
    const py_world = (ry - origin_y) / resolution;

    const py = img_height - py_world; // y축 반전

    // ===== 3) crop 내부 좌표 =====
    const px_crop = px - crop_x_min;
    const py_crop = py - crop_y_min;

    let px_crop_clamped = px_crop;
    let py_crop_clamped = py_crop;

    if (px_crop_clamped < 0) px_crop_clamped = 0;
    if (px_crop_clamped > crop_w) px_crop_clamped = crop_w;
    if (py_crop_clamped < 0) py_crop_clamped = 0;
    if (py_crop_clamped > crop_h) py_crop_clamped = crop_h;

    const relX = px_crop_clamped / crop_w;
    const relY = py_crop_clamped / crop_h;

    const screenX = relX * displayW;
    const screenY = relY * displayH;

    // ===== 4) DOM 생성 + 겹침 방지 jitter =====
    const node = document.createElement("div");
    node.className = "agv-node";

    const jitterX = (idx - (states.length - 1) / 2) * 14;
    const jitterY = 0;

    node.style.left = `${screenX + jitterX}px`;
    node.style.top  = `${screenY + jitterY}px`;

    const label = document.createElement("div");
    label.className = "agv-label";

    let name = s.equipment_id;
    if (s.equipment && s.equipment.equipment_name) {
      name = s.equipment.equipment_name;
    }
    label.textContent = name;

    node.appendChild(label);
    wrap.appendChild(node);
  });
}