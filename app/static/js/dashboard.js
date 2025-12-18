let classifyChartInstance = null;
let visionMixedChartInstance = null;

let lastControlJson = null;
let lastMissionJson = null;
let lastAmrJson = null;
let lastVisionMixedJson = null;

document.addEventListener("DOMContentLoaded", () => {
  initDashboardStream();

  // 맵 배경 1회 로딩
  refreshAgvMap();

  // 차트 초기화 + 우측 혼합차트 데이터 로드
  initCharts();

  // 첫 화면에서 바로 데이터 한 번 로드(사용자 체감 개선)
  loadAmrStates();
  loadAmrSummary();
  loadControlLogs();
  loadMissionLogs();
  loadVisionMixedChart();
  loadAnomalyModuleChart();  
});

function initDashboardStream() {
  const es = new EventSource("/api/v1/dashboard/stream");

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const { type } = data;

      if (type === "hello") return;

      if (type === "tick") {
        loadAmrStates();
        loadAmrSummary();    
        loadControlLogs();
        loadMissionLogs();
        loadVisionMixedChart();
        loadAnomalyModuleChart();   
        return;
      }

      console.warn("[SSE] unknown type:", type, data);
    } catch (err) {
      console.error("[SSE] parse error", err, event.data);
    }
  };

  es.onerror = (err) => {
    console.error("[SSE] error", err);
  };
}

// -------------------- Chart 초기화 --------------------

function initCharts() {
  const classifyCanvas = document.getElementById("classifyChart");
  const successCanvas  = document.getElementById("successChart");
  if (!classifyCanvas || !successCanvas) return;

  const classifyCtx = classifyCanvas.getContext("2d");
  const successCtx  = successCanvas.getContext("2d");

  // ✅ 좌측 차트: Mock 제거 → 빈 차트(다음 단계에서 API 연결)
  // ✅ 좌측 차트: module_type별 PASS/REJECT 그룹 Bar
  if (classifyChartInstance) {
    classifyChartInstance.destroy();
    classifyChartInstance = null;
  }

  classifyChartInstance = new Chart(classifyCtx, {
    type: "bar",
    data: {
      labels: [],
      datasets: [
        {
          label: "PASS",
          data: [],
          borderWidth: 1,
          categoryPercentage: 0.7,
          barPercentage: 1,
          maxBarThickness: 24,
        },
        {
          label: "REJECT",
          data: [],
          borderWidth: 1,
          categoryPercentage: 0.7,
          barPercentage: 1,
          maxBarThickness: 24,
        },
      ],
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false }, // 공간 확보 (원하면 true)
        tooltip: {
          callbacks: {
            title: (items) => {
              const i = items?.[0]?.dataIndex ?? 0;
              const label = classifyChartInstance?.data?.labels?.[i] ?? "";
              const totals = window.__anomalyModuleTotals || [];
              const total = totals[i] ?? 0;
              return `${label} · 총 ${total}건`;
            },
            label: (ctx) => {
              const label = ctx.dataset.label || "";
              const v = ctx.parsed.y ?? 0;
              return `${label}: ${v}건`;
            },
          },
        },
      },
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

  // ✅ 기존 우측 혼합차트 인스턴스 제거
  if (visionMixedChartInstance) {
    visionMixedChartInstance.destroy();
    visionMixedChartInstance = null;
  }

  // ✅ tooltip title totals 캐시
  window.__visionMixedTotals = [];

  // ✅ 우측 혼합차트
  visionMixedChartInstance = new Chart(successCtx, {
    data: {
      labels: [],
      datasets: [
        {
          type: "bar",
          label: "평균 신뢰도",
          data: [],
          yAxisID: "y",
          borderWidth: 1,
          categoryPercentage: 0.65,
          barPercentage: 0.55,
          maxBarThickness: 28,
        },
        {
          type: "line",
          label: "PASS 비율",
          data: [],
          yAxisID: "y",
          tension: 0.25,
          fill: false,
          borderWidth: 3,
          pointRadius: 3,
          pointHoverRadius: 5,
        },
        {
          type: "line",
          label: "REJECT 비율",
          data: [],
          yAxisID: "y",
          tension: 0.25,
          fill: false,
          borderWidth: 3,
          pointRadius: 3,
          pointHoverRadius: 5,
        },
      ],
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => {
              const idx = items?.[0]?.dataIndex ?? 0;
              const totals = window.__visionMixedTotals || [];
              const total = totals[idx] ?? 0;
              return `총 ${total}건`;
            },
            label: (ctx) => {
              const label = ctx.dataset.label || "";
              const v = ctx.parsed.y ?? 0;

              if (ctx.dataset.type === "line") {
                return `${label}: ${Math.round(v * 100)}%`;
              }
              return `${label}: ${(v * 100).toFixed(1)}%`;
            },
          },
        },
      },
      scales: {
        y: {
          position: "left",
          beginAtZero: true,
          // ✅ max 제거 → suggestedMax가 실제로 적용되도록
          suggestedMax: 1,
          ticks: {
            color: "#9ca3af",
            font: { size: 10 },
            callback: (v) => `${Math.round(v * 100)}%`,
          },
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

let lastAnomalyModuleJson = null;

async function loadAnomalyModuleChart() {
  if (!classifyChartInstance) return;

  try {
    const res = await fetch("/api/v1/dashboard/vision_anomaly_modules");
    if (!res.ok) {
      console.error("failed to fetch vision_anomaly_modules", res.status);
      return;
    }

    const data = await res.json();
    const chart = data.chart || {};

    // 변경 없으면 스킵
    const newJson = JSON.stringify(chart);
    if (newJson === lastAnomalyModuleJson) return;
    lastAnomalyModuleJson = newJson;

    const labels = chart.labels || [];
    const passCounts = chart.pass_counts || [];
    const rejectCounts = chart.reject_counts || [];
    const totals = chart.totals || [];

    // tooltip title에서 사용
    window.__anomalyModuleTotals = totals;

    // 차트 갱신
    classifyChartInstance.data.labels = labels;
    classifyChartInstance.data.datasets[0].data = passCounts;   // PASS
    classifyChartInstance.data.datasets[1].data = rejectCounts; // REJECT

    classifyChartInstance.update();

    // (선택) 캡션에 요약 표시하고 싶으면
    const titleEl = document.getElementById("classifyChartTitle");
    if (titleEl && data.meta) {
      titleEl.textContent =
        `물류 분류 - 모듈별 PASS/REJECT 건수 (총 ${data.meta.total ?? 0}건)`;
    }

  } catch (err) {
    console.error("error loading anomaly module chart", err);
  }
}

async function loadVisionMixedChart() {
  if (!visionMixedChartInstance) return;

  try {
    const res = await fetch("/api/v1/dashboard/vision_mixed?limit=5");
    if (!res.ok) return console.error("failed to fetch vision_mixed", res.status);

    const data = await res.json();
    const chart = data.chart || {};

    const newJson = JSON.stringify(chart);
    if (newJson === lastVisionMixedJson) return;
    lastVisionMixedJson = newJson;

    const labels     = chart.labels || [];
    const avgConf    = chart.avg_confidence || [];
    const passRate   = chart.pass_rate || [];
    const rejectRate = chart.reject_rate || [];

    window.__visionMixedTotals = chart.counts?.total || [];

    visionMixedChartInstance.data.labels = labels;
    visionMixedChartInstance.data.datasets[0].data = avgConf;
    visionMixedChartInstance.data.datasets[1].data = passRate;
    visionMixedChartInstance.data.datasets[2].data = rejectRate;

    visionMixedChartInstance.update();
  } catch (err) {
    console.error("error loading vision_mixed chart", err);
  }
}

// -------------------- 제어 로그(API) --------------------

function createControlRow(c) {
  const row = document.createElement("div");
  row.className = "log-row";

  const colTime = document.createElement("span");
  colTime.textContent = c.created_at ? c.created_at.slice(5, 19) : "";

  const colTarget = document.createElement("span");
  colTarget.textContent = (c.equipment?.equipment_name) ? c.equipment.equipment_name : (c.equipment_id || "-");

  const colSrcType = document.createElement("span");
  const source = c.source || "-";
  const ttype  = c.target_type || "";
  colSrcType.textContent = ttype ? `${source} / ${ttype}` : source;

  const colResult = document.createElement("span");
  const resultSpan = document.createElement("span");
  const result = c.result_status || "SUCCESS";
  resultSpan.className =
    "log-level " +
    (result === "SUCCESS" ? "lvl-info" : result === "FAIL" ? "lvl-err" : "lvl-warn");
  resultSpan.textContent = result;
  colResult.appendChild(resultSpan);

  const colDetail = document.createElement("span");
  const detailParts = [];
  if (c.action_type) detailParts.push(c.action_type);
  if (c.request_payload) detailParts.push(c.request_payload);
  if (c.result_message) detailParts.push(c.result_message);
  colDetail.textContent = detailParts.join(" · ");

  row.appendChild(colTime);
  row.appendChild(colTarget);
  row.appendChild(colSrcType);
  row.appendChild(colResult);
  row.appendChild(colDetail);

  return row;
}

async function loadControlLogs() {
  const controlTable = document.getElementById("control-table");
  if (!controlTable) return;

  try {
    const res = await fetch("/api/v1/dashboard/control_logs?limit=10");
    if (!res.ok) return console.error("failed to fetch control-logs", res.status);

    const data = await res.json();
    const items = data.items || [];

    const newJson = JSON.stringify(items);
    if (newJson === lastControlJson) return;
    lastControlJson = newJson;

    while (controlTable.children.length > 1) {
      controlTable.removeChild(controlTable.lastChild);
    }

    const frag = document.createDocumentFragment();
    items.forEach(c => frag.appendChild(createControlRow(c)));
    controlTable.appendChild(frag);
  } catch (err) {
    console.error("error loading control-logs", err);
  }
}

// -------------------- 미션 로그(API) --------------------

function createMissionItem(m) {
  const status = m.status || "INFO";

  const item = document.createElement("div");
  item.className = "mission-item";

  const main = document.createElement("div");
  main.className = "mission-main";

  const id = document.createElement("div");
  id.className = "mission-id";
  id.textContent = (m.equipment?.equipment_name) ? `${m.equipment.equipment_name} · ${m.equipment_id}` : (m.equipment_id || "-");

  const meta = document.createElement("div");
  meta.className = "mission-meta";

  if(status == "DONE")
    meta.textContent = `작업완료 / 완료: ${(m.created_at ? m.created_at.slice(0, 19) : "")}`;
  else
     meta.textContent = `단계: ${m.description || "-"} / 시작: ${(m.created_at ? m.created_at.slice(0, 19) : "")}`;
  main.appendChild(id);
  main.appendChild(meta);

  const st = document.createElement("div");
  
  st.className =
    "status-pill " +
    (status === "RUNNING" ? "status-running" : status === "DONE" ? "status-done" : "status-error");
  st.textContent = status;

  item.appendChild(main);
  item.appendChild(st);

  return item;
}

async function loadMissionLogs() {
  const missionList = document.getElementById("mission-list");
  if (!missionList) return;

  try {
    const res = await fetch("/api/v1/dashboard/mission_logs?limit=10");
    if (!res.ok) return console.error("failed to fetch mission_logs", res.status);

    const data = await res.json();
    const items = data.items || [];

    const newJson = JSON.stringify(items);
    if (newJson === lastMissionJson) return;
    lastMissionJson = newJson;

    missionList.replaceChildren();
    const frag = document.createDocumentFragment();
    items.forEach(m => frag.appendChild(createMissionItem(m)));
    missionList.appendChild(frag);
  } catch (err) {
    console.error("error loading mission_logs", err);
  }
}

// ================== AGV 맵 관련 ==================

let MAP_META = null;

function refreshAgvMap() {
  const el = document.getElementById("agv-map-bg");
  if (!el) return;
  el.style.backgroundImage = `url("/api/v1/dashboard/map-image?t=${Date.now()}")`;
}

async function loadMapMeta() {
  try {
    const res = await fetch("/api/v1/dashboard/map-meta");
    if (!res.ok) return console.error("failed to fetch map-meta", res.status);
    MAP_META = await res.json();
  } catch (err) {
    console.error("error loading map-meta", err);
  }
}

let lastAmrSummaryJson = null;

async function loadAmrSummary() {
  const elMain = document.getElementById("chip-amr-main");
  const elLocation = document.getElementById("chip-amr-location");
  const elTarget = document.getElementById("chip-amr-target");
  const elAction = document.getElementById("chip-amr-action");
  if (!elMain || !elTarget || !elAction) return;

  try {
    const res = await fetch("/api/v1/dashboard/amr_summary");
    if (!res.ok) return console.error("failed to fetch amr_summary", res.status);

    const data = await res.json();
    const items = data.items || [];

    const newJson = JSON.stringify(items);
    if (newJson === lastAmrSummaryJson) return;
    lastAmrSummaryJson = newJson;

    const amr = items[0];
    if (!amr) return;

    const name = amr.equipment_name || amr.equipment_id || "AMR";
    const status = (amr.status || "-").toUpperCase();

    const misiion_status = amr.misiion_status || "-";
    const target = amr.target_station || "-";

    let location = "-";
    if(misiion_status == "DONE") 
      location = amr.source_station || "-";
    else
      location = amr.source_station || "-";

    elMain.textContent = `${name} · ${status}`;
    elTarget.textContent = `목적지: ${target}`;
    elLocation.textContent = `현위치: ${location}`;


    const ACTION_LABEL = {
      UNLOADING: "하역",
      LOADING: "적재",
      MOVE: "이동중",
      HOEM: "HOME이동",
      ERROR: "오류발생"
    };

    let actionLabel = "-"
    if(misiion_status == "DONE")
      actionLabel = "미션완료";
    else 
      actionLabel = ACTION_LABEL[amr.action_type] || amr.action_type || "정지";


    elAction.textContent = `동작: ${actionLabel}`; 

  } catch (err) {
    console.error("error loading amr_summary", err);
  }
}

async function loadAmrStates() {
  if (!MAP_META) await loadMapMeta();

  try {
    const res = await fetch("/api/v1/dashboard/amr_states");
    if (!res.ok) return console.error("failed to fetch amr_states", res.status);

    const data = await res.json();
    const items = data.items || [];

    const newJson = JSON.stringify(items);
    if (newJson === lastAmrJson) return;
    lastAmrJson = newJson;

    updateAgvStatus(items);
    drawAmrMarkers(items);
  } catch (err) {
    console.error("error loading amr_states", err);
  }
}

function updateAgvStatus(states) {
  const list = document.getElementById("agv-status-list");
  if (!list) return;

  list.replaceChildren();

  const frag = document.createDocumentFragment();

  states.forEach((s) => {
    const item = document.createElement("div");
    item.className = "status-item";

    const labelWrap = document.createElement("div");
    labelWrap.className = "status-label";

    let name = s.equipment?.equipment_name ? s.equipment.equipment_name : (s.equipment_id || "-");

    const stateCode = (s.state_code || "").toUpperCase();
    let dotClass = "green";
    if (stateCode === "IDLE" || stateCode === "WAIT") dotClass = "yellow";
    if (stateCode === "ERR" || stateCode === "ERROR" || stateCode === "ALARM") dotClass = "red";

    const dot = document.createElement("span");
    dot.className = `dot ${dotClass}`;

    const nameSpan = document.createElement("span");
    nameSpan.textContent = `${name} 상태`;

    labelWrap.appendChild(dot);
    labelWrap.appendChild(nameSpan);

    const value = document.createElement("div");
    value.className = "status-value";

    const detailParts = [];
    if (stateCode === "MOVE" || stateCode === "RUN") detailParts.push("정상 주행");
    else if (stateCode === "IDLE" || stateCode === "WAIT") detailParts.push("대기");
    else if (stateCode === "ERR" || stateCode === "ERROR" || stateCode === "ALARM") detailParts.push("오류 / 알람");
    else if (stateCode) detailParts.push(stateCode);

    if (typeof s.battery_pct === "number") detailParts.push(`배터리 ${s.battery_pct.toFixed(0)}%`);
    if (typeof s.speed === "number") detailParts.push(`속도 ${s.speed.toFixed(2)} m/s`);

    value.textContent = detailParts.join(" · ");

    item.appendChild(labelWrap);
    item.appendChild(value);
    frag.appendChild(item);
  });

  list.appendChild(frag);
}

function drawAmrMarkers(states) {
  const meta = MAP_META;
  if (!meta) return;

  const wrap = document.querySelector(".agv-path");
  if (!wrap) return;

  const displayW = wrap.clientWidth;
  const displayH = wrap.clientHeight;

  const origin_x   = parseFloat(meta.origin_x);
  const origin_y   = parseFloat(meta.origin_y);
  const resolution = parseFloat(meta.resolution);
  const img_height = parseFloat(meta.img_height);
  const crop_x_min = parseFloat(meta.crop_x_min);
  const crop_y_min = parseFloat(meta.crop_y_min);
  const crop_w     = parseFloat(meta.crop_w);
  const crop_h     = parseFloat(meta.crop_h);
  if (!resolution || !crop_w || !crop_h) return;

  wrap.replaceChildren();

  const DEG = 160;
  const theta = (DEG * Math.PI) / 180;
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);

  const PIVOT_X = -0.6;
  const PIVOT_Y = -3;

  const SWAP_XY   = true;
  const INVERT_X  = false;
  const INVERT_Y  = true;

  states.forEach((s, idx) => {
    if (typeof s.pos_x !== "number" || typeof s.pos_y !== "number") return;

    let worldX, worldY;
    if (SWAP_XY) {
      worldX = s.pos_y;
      worldY = s.pos_x;
    } else {
      worldX = s.pos_x;
      worldY = s.pos_y;
    }
    if (INVERT_X) worldX = -worldX;
    if (INVERT_Y) worldY = -worldY;

    const wx = worldX - PIVOT_X;
    const wy = worldY - PIVOT_Y;
    const rx = wx * cosT - wy * sinT + PIVOT_X;
    const ry = wx * sinT + wy * cosT + PIVOT_Y;

    const px       = (rx - origin_x) / resolution;
    const py_world = (ry - origin_y) / resolution;
    const py       = img_height - py_world;

    const px_crop = px - crop_x_min;
    const py_crop = py - crop_y_min;

    const px_crop_clamped = Math.min(Math.max(px_crop, 0), crop_w);
    const py_crop_clamped = Math.min(Math.max(py_crop, 0), crop_h);

    const relX = px_crop_clamped / crop_w;
    const relY = py_crop_clamped / crop_h;

    const screenX = relX * displayW;
    const screenY = relY * displayH;

    const node = document.createElement("div");
    node.className = "agv-node";

    const jitterX = (idx - (states.length - 1) / 2) * 14;

    node.style.left = `${screenX + jitterX}px`;
    node.style.top  = `${screenY}px`;

    const label = document.createElement("div");
    label.className = "agv-label";
    label.textContent = s.equipment?.equipment_name ? s.equipment.equipment_name : (s.equipment_id || "");

    node.appendChild(label);
    wrap.appendChild(node);
  });

  drawFixedPins();  
  drawGoalZones();  
}


// ✅ 고정 핀 좌표(0~1 비율)만 바꿔서 보정하면 됨
const FIXED_PINS = [
  // relX, relY는 agv-path 박스 기준 (0~1)
  { key: "ARM", cls: "arm", relX: 0.36, relY: 0.72 },
];

function drawFixedPins() {
  const wrap = document.querySelector(".agv-path");
  if (!wrap) return;

  const w = wrap.clientWidth;
  const h = wrap.clientHeight;

  // 기존 핀 제거
  wrap.querySelectorAll(".fixed-pin").forEach(el => el.remove());

  FIXED_PINS.forEach(p => {
    const pin = document.createElement("div");
    pin.className = `fixed-pin ${p.cls}`;

    const x = p.relX * w;
    const y = p.relY * h;

    pin.style.left = `${x}px`;
    pin.style.top  = `${y}px`;

    const label = document.createElement("div");
    label.className = "fixed-pin-label";
    label.textContent = p.key;

    pin.appendChild(label);
    wrap.appendChild(pin);
  });
}

// ✅ Goal 영역(0~1 비율) 3개 - 숫자만 바꿔서 보정
const GOAL_ZONES = [
  // relX/Y: 좌상단 기준, relW/H: 폭/높이 (모두 0~1)
  { key: "ST_ESP32", cls: "st1", relX: 0.05, relY: 0.08, relW: 0.12, relH: 0.12 },
  { key: "ST_L298N", cls: "st2", relX: 0.45, relY: 0.08, relW: 0.12, relH: 0.12 },
  { key: "ST_MB102", cls: "st3", relX: 0.80, relY: 0.16, relW: 0.12, relH: 0.12 },
  { key: "PLC", cls: "st4", relX: 0.40, relY: 0.70, relW: 0.14, relH: 0.10 },
];

function drawGoalZones() {
  const wrap = document.querySelector(".agv-path");
  if (!wrap) return;

  const w = wrap.clientWidth;
  const h = wrap.clientHeight;

  // 기존 goal-zone 제거
  wrap.querySelectorAll(".goal-zone").forEach(el => el.remove());

  GOAL_ZONES.forEach(z => {
    const el = document.createElement("div");
    el.className = `goal-zone ${z.cls}`;

    el.style.left = `${z.relX * w}px`;
    el.style.top = `${z.relY * h}px`;
    el.style.width = `${z.relW * w}px`;
    el.style.height = `${z.relH * h}px`;

    const label = document.createElement("div");
    label.className = "goal-zone-label";
    label.textContent = z.key;

    el.appendChild(label);
    wrap.appendChild(el);
  });
}