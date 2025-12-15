// static/js/vision_logs.js
// ======================
//   공통 상태 변수
// ======================
let VISION_ITEMS = [];
let VISION_SELECTED_ROW = null;

let VISION_PAGE = 1;          // 현재 페이지 (1-base)
const VISION_LIMIT = 8;       // 페이지당 행 수
let VISION_TOTAL = 0;         // 전체 건수 (API total 기준)

let visionAnomalyChart = null; // anomaly_score 라인차트 인스턴스
let visionConfidenceChart = null; // ✅ confidence 막대차트

// ======================
//   이미지 URL 헬퍼
// ======================
function resolveImageUrl(item) {
  if (!item) return "";

  const path = item.image_path || "";
  const name = item.image_name || "";

  if (!name) return "";

  const params = new URLSearchParams();
  if (path) params.set("path", path);
  params.set("name", name);

  return `/api/v1/vision/logs_image?${params.toString()}`;
}

// ======================
//   PASS / REJECT Pill
// ======================
function createDecisionPill(decision) {
  const span = document.createElement("span");
  span.className = "decision-pill";
  const d = (decision || "UNKNOWN").toUpperCase();

  if (d === "PASS") {
    span.classList.add("decision-pass");
    span.textContent = "PASS";
  } else if (d === "REJECT") {
    span.classList.add("decision-reject");
    span.textContent = "REJECT";
  } else {
    span.classList.add("decision-unknown");
    span.textContent = "UNKNOWN";
  }
  return span;
}

// ======================
//   상세 패널 갱신
// ======================
function updateDetailPanel(item) {
  const idPill     = document.getElementById("detail-id-pill");
  const img        = document.getElementById("vision-image");
  const placeholder = document.getElementById("vision-image-placeholder");

  const vEq      = document.getElementById("detail-equipment");
  const vMode    = document.getElementById("detail-mode");
  const vModule  = document.getElementById("detail-module");
  const vDecision= document.getElementById("detail-decision");
  const vAnFlag  = document.getElementById("detail-anomaly-flag");
  const vConf    = document.getElementById("detail-confidence");
  const vScore   = document.getElementById("detail-anomaly-score");
  const vPick    = document.getElementById("detail-pick-coord");
  const vFile    = document.getElementById("detail-file");
  const vCreated = document.getElementById("detail-created-at");

  // ID
  idPill.textContent =
    item && item.log_camera_id ? `log_id: ${item.log_camera_id}` : "log_id: -";

  // 이미지
  const url = item ? resolveImageUrl(item) : "";
  if (url) {
    img.src = url;
    img.style.display = "block";
    placeholder.style.display = "none";
  } else {
    img.src = "";
    img.style.display = "none";
    placeholder.style.display = "flex";
  }

  // 텍스트 필드들
  if (item && item.equipment) {
    vEq.textContent =
      item.equipment.equipment_name ||
      item.equipment.equipment_id ||
      "-";
  } else {
    vEq.textContent = "-";
  }

  vMode.textContent   = (item && item.mode) || "-";
  vModule.textContent = (item && item.module_type) || "-";

  const d = item && item.decision ? item.decision.toUpperCase() : "UNKNOWN";
  if (d === "PASS") {
    vDecision.textContent = "PASS (통과)";
    vDecision.className = "meta-value flag-normal";
  } else if (d === "REJECT") {
    vDecision.textContent = "REJECT (배출)";
    vDecision.className = "meta-value flag-defect";
  } else {
    vDecision.textContent = "UNKNOWN";
    vDecision.className = "meta-value";
  }

  // anomaly_flag: 1=정상, 0=불량, null=미실행   (DB 코멘트 기준)
  if (!item || item.anomaly_flag === null || item.anomaly_flag === undefined) {
    vAnFlag.textContent = "미실행 / N/A";
    vAnFlag.className = "meta-value";
  } else if (item.anomaly_flag === 1 || item.anomaly_flag === true) {
    vAnFlag.textContent = "불량 (1)";
    vAnFlag.className = "meta-value flag-defect";
  } else {
    vAnFlag.textContent = "정상 (0)";
    vAnFlag.className = "meta-value flag-normal";
  }

  if (item && typeof item.classification_confidence === "number") {
    vConf.textContent = `${(item.classification_confidence * 100).toFixed(
      2
    )} %`;
  } else {
    vConf.textContent = "-";
  }

  if (item && typeof item.anomaly_score === "number") {
    vScore.textContent = item.anomaly_score.toFixed(4);
  } else {
    vScore.textContent = "-";
  }

  if (item && item.pick_coord != null) {
    vPick.textContent = String(item.pick_coord);
  } else {
    vPick.textContent = "-";
  }

  const fileLabel = item
    ? item.image_name || "(저장된 파일 정보 없음)"
    : "-";
  vFile.textContent = fileLabel;

  vCreated.textContent = (item && item.created_at) || "-";
}

// ======================
//   목록 Row 생성
// ======================
function createVisionRow(item) {
  const row = document.createElement("div");
  row.className = "log-row vision-log-row"; // grid 레이아웃은 dashboard.css .log-row 사용

  // 1. 시간
  const colTime = document.createElement("span");
  const t = item.created_at || "";
  colTime.textContent = t ? t.slice(5, 19) : "";  // "2025-12-15 16:00:00" -> "12-15 16:00:00"

  // 2. 장비 (이름 > ID)
  const colEquip = document.createElement("span");
  let equipLabel = item.equipment_id || "-";
  if (item.equipment && item.equipment.equipment_name) {
    equipLabel = item.equipment.equipment_name;
  }
  colEquip.textContent = equipLabel;

  // 3. 모드
  const colMode = document.createElement("span");
  colMode.textContent = item.mode || "-";

  // 4. 판정 Pill
  const colDecision = document.createElement("span");
  colDecision.appendChild(createDecisionPill(item.decision));

  // 5. 모듈/스코어
  const colDetail = document.createElement("span");
  const parts = [];
  if (item.module_type) {
    parts.push(item.module_type);
  }
  // score는 ANOMALY에서만 표시 (JOINT_DETECTION은 0.0000 더미라 제외)
  if (item.mode === "ANOMALY" && typeof item.anomaly_score === "number") {
    parts.push(`score ${item.anomaly_score.toFixed(4)}`);
  }
  if (typeof item.classification_confidence === "number") {
    parts.push(`conf ${item.classification_confidence.toFixed(4)}`);
  }
  colDetail.textContent = parts.join(" · ");

  // 조립
  row.appendChild(colTime);
  row.appendChild(colEquip);
  row.appendChild(colMode);
  row.appendChild(colDecision);
  row.appendChild(colDetail);

  // 클릭 시 선택
  row.addEventListener("click", () => {
    selectVisionRow(item, row);
  });

  return row;
}

// ======================
//   행 선택
// ======================
function selectVisionRow(item, rowEl) {
  if (VISION_SELECTED_ROW) {
    VISION_SELECTED_ROW.classList.remove("is-selected");
  }
  VISION_SELECTED_ROW = rowEl;
  rowEl.classList.add("is-selected");

  updateDetailPanel(item);
}

// ======================
//   목록 로딩 (페이지네이션 포함)
// ======================
async function loadVisionLogs(pageOverride) {
  const bodyEl      = document.getElementById("vision-log-body");
  const countEl     = document.getElementById("vision-log-count");
  const pageLabelEl = document.getElementById("vision-page-label");
  const prevBtn     = document.getElementById("vision-page-prev");
  const nextBtn     = document.getElementById("vision-page-next");
  if (!bodyEl) return;

  // 페이지 값 결정
  if (typeof pageOverride === "number" && pageOverride >= 1) {
    VISION_PAGE = pageOverride;
  }
  const currentPage = VISION_PAGE;

  const modeSel = document.getElementById("vision-filter-mode");
  const decSel  = document.getElementById("vision-filter-decision");

  const mode     = modeSel ? modeSel.value : "";
  const decision = decSel  ? decSel.value  : "";

  const params = new URLSearchParams();
  if (mode)     params.set("mode", mode);
  if (decision) params.set("decision", decision);
  params.set("limit",  String(VISION_LIMIT));
  params.set("offset", String((currentPage - 1) * VISION_LIMIT));

  try {
    const res = await fetch(`/api/v1/vision/logs?${params.toString()}`);
    if (!res.ok) {
      console.error("failed to fetch vision logs", res.status);
      return;
    }

    const data  = await res.json();
    const items = data.items || [];
    VISION_ITEMS = items;

    // total이 없으면 items.length 사용
    if (typeof data.total === "number") {
      VISION_TOTAL = data.total;
    } else if (typeof data.count === "number") {
      VISION_TOTAL = data.count;
    } else {
      VISION_TOTAL = items.length;
    }

    // ===== 테이블 채우기 =====
    while (bodyEl.firstChild) {
      bodyEl.removeChild(bodyEl.firstChild);
    }
    VISION_SELECTED_ROW = null;

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "vision-log-empty";
      empty.textContent = "표시할 로그가 없습니다.";
      bodyEl.appendChild(empty);
      updateDetailPanel(null);
    } else {
      const frag = document.createDocumentFragment();
      items.forEach((item) => {
        frag.appendChild(createVisionRow(item));
      });
      bodyEl.appendChild(frag);

      // 첫 행 자동 선택
      const firstRow = bodyEl.querySelector(".vision-log-row");
      if (firstRow) {
        selectVisionRow(items[0], firstRow);
      }
    }

    // ===== 카운트 / 페이지 정보 =====
    if (countEl) {
      countEl.textContent = `총 ${VISION_TOTAL}건`;
    }
    const totalPages = Math.max(1, Math.ceil(VISION_TOTAL / VISION_LIMIT));
    if (pageLabelEl) {
      pageLabelEl.textContent = `${currentPage} / ${totalPages}`;
    }

    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;

  } catch (err) {
    console.error("error loading vision logs", err);
  }
}

// ======================
//   Vision 통계/차트 업데이트
//   (API: { stats: {...}, chart: {...} })
// ======================


// anomaly_score 라인 차트 갱신
function renderVisionAnomalyChart(chartData) {
  const canvas = document.getElementById("visionAnomalyChart");
  if (!canvas) return;

  const labels      = chartData.labels || [];
  const passScores  = chartData.pass_scores || [];
  const rejectScores= chartData.reject_scores || [];
  const threshold   = typeof chartData.threshold === "number" ? chartData.threshold : null;

  const totalCounts = chartData.total_counts || [];
  const passCounts  = chartData.pass_counts || [];
  const rejectCounts= chartData.reject_counts || [];

  // y축 스케일 계산 (score 값 + threshold 포함해서 적당한 범위)
  const allVals = []
    .concat(passScores.filter(v => typeof v === "number"))
    .concat(rejectScores.filter(v => typeof v === "number"));

  let maxVal = allVals.length ? Math.max(...allVals) : 0.1;
  if (threshold != null) {
    maxVal = Math.max(maxVal, threshold);
  }
  const yMax = maxVal * 1.2;   // 살짝 여유

  // 이전 차트 있으면 파괴
  if (visionAnomalyChart) {
    visionAnomalyChart.destroy();
    visionAnomalyChart = null;
  }

  const ctx = canvas.getContext("2d");

  const datasets = [
    {
      label: "PASS",
      data: passScores,
      borderColor: "rgba(56, 189, 248, 1)",          // 파랑
      backgroundColor: "rgba(56, 189, 248, 0.2)",
      tension: 0.2,
      spanGaps: true,
      pointRadius: 3,
    },
    {
      label: "REJECT",
      data: rejectScores,
      borderColor: "rgba(248, 113, 113, 1)",        // 빨강
      backgroundColor: "rgba(248, 113, 113, 0.2)",
      tension: 0.2,
      spanGaps: true,
      pointRadius: 3,
    },
  ];

  // threshold 라인 추가 (옵션)
  if (threshold != null) {
    datasets.push({
      label: "threshold",
      data: labels.map(() => threshold),
      borderColor: "rgba(234, 179, 8, 1)",          // 노랑
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
    });
  }

  visionAnomalyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,   // ✅ 부모 높이에 맞춰
      plugins: {
        legend: {
          labels: { color: "#e5e7eb", font: { size: 11 } },
        },
        tooltip: {
          mode: "nearest",
          intersect: true, // ✅ 선 위에서만 반응(원하면 false)
          callbacks: {
            // ✅ 날짜 대신 "해당 선의 카운트"만
            title: (items) => {
              if (!items || !items.length) return "";
              const it = items[0];
              const idx = it.dataIndex;
              const dsLabel = (it.dataset.label || "").toUpperCase();

              if (dsLabel.includes("PASS")) {
                const c = passCounts[idx] ?? 0;
                return `PASS 총 ${c}건`;
              }
              if (dsLabel.includes("REJECT")) {
                const c = rejectCounts[idx] ?? 0;
                return `REJECT 총 ${c}건`;
              }
              if (dsLabel.includes("THRESHOLD")) {
                return "threshold";
              }
              return "";
            },

            // 값 표시(평균 score)
            label: (ctx) => {
              const v = ctx.raw;
              if (v == null) return `${ctx.dataset.label}: N/A`;
              return `${ctx.dataset.label}: ${Number(v).toFixed(3)}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#9ca3af",
            font: { size: 10 },
          },
          grid: {
            color: "rgba(31, 41, 55, 0.8)",
          },
        },
        y: {
          beginAtZero: true,
          suggestedMax: yMax,
          ticks: {
            color: "#9ca3af",
            font: { size: 10 },
          },
          grid: {
            color: "rgba(31, 41, 55, 0.8)",
          },
        },
      },
    },
  });
}

// stats + chart 한 번에 호출
async function loadVisionStats() {
  const params = new URLSearchParams();
  params.set("mode", "ANOMALY");

  try {
    const res = await fetch(`/api/v1/vision/stats?mode=ANOMALY&limit_days=5`)
    if (!res.ok) {
      console.error("failed to fetch vision stats", res.status);
      return;
    }

    const data = await res.json();
    const chartData = data.chart || {};

    // ----- 차트 렌더 -----
    renderVisionAnomalyChart(chartData);

  } catch (err) {
    console.error("error loading vision stats", err);
  }
}

// ======================
//  DOM 로드 후 이벤트 바인딩
// ======================
document.addEventListener("DOMContentLoaded", () => {
  const modeSel  = document.getElementById("vision-filter-mode");
  const decSel   = document.getElementById("vision-filter-decision");
  const prevBtn  = document.getElementById("vision-page-prev");
  const nextBtn  = document.getElementById("vision-page-next");

  // 로그 + 통계를 함께 다시 불러오는 헬퍼
  function reloadPage(page) {
    VISION_PAGE = page;
    loadVisionLogs(page);   // 목록
    loadVisionStats();      // 요약/차트
    loadVisionConfidenceStats(); // confidence 막대차트

  }

  // 필터 변경 시: 페이지 1로 리셋 + 로그/통계 재조회
  if (modeSel) {
    modeSel.addEventListener("change", () => {
      reloadPage(1);
    });
  }
  if (decSel) {
    decSel.addEventListener("change", () => {
      reloadPage(1);
    });
  }

  // 이전 페이지 버튼
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (VISION_PAGE > 1) {
        reloadPage(VISION_PAGE - 1);
      }
    });
  }

  // 다음 페이지 버튼
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(VISION_TOTAL / VISION_LIMIT));
      if (VISION_PAGE < totalPages) {
        reloadPage(VISION_PAGE + 1);
      }
    });
  }

  // 첫 로딩: 1페이지 + 통계
  reloadPage(1);
});


function renderVisionConfidenceChart(chartData) {
  const canvas = document.getElementById("visionFutureChart");
  if (!canvas) return;

  const labels = chartData.labels || [];
  const anomaly = chartData.anomaly_cls_avg || [];
  const jointCls = chartData.joint_cls_avg || [];

  const anomalyCounts = chartData.anomaly_counts || [];
  const jointCounts = chartData.joint_counts || [];

  if (visionConfidenceChart) {
    visionConfidenceChart.destroy();
    visionConfidenceChart = null;
  }

  const ctx = canvas.getContext("2d");

  visionConfidenceChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "ANOMALY", data: anomaly },
        { label: "JOINT (CLS)", data: jointCls },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#e5e7eb", font: { size: 11 } } },
        tooltip: {
          mode: "nearest",
          intersect: true, // ✅ 막대 위에서만 반응(원하면 false로)
          callbacks: {
            // ✅ 날짜 대신 "해당 막대의 카운트"만
            title: (items) => {
              if (!items || !items.length) return "";
              const it = items[0];
              const idx = it.dataIndex;
              const dsLabel = (it.dataset.label || "").toUpperCase();

              if (dsLabel.includes("ANOM")) {
                const c = anomalyCounts[idx] ?? 0;
                return `ANOMALY 총 ${c}건`;
              }
              if (dsLabel.includes("JOINT")) {
                const c = jointCounts[idx] ?? 0;
                return `JOINT 총 ${c}건`;
              }
              return "";
            },
            // ✅ 본문은 confidence만 (원하면 여기서도 카운트 같이 붙일 수 있음)
            label: (c) => {
              const v = c.raw;
              if (v == null) return `${c.dataset.label}: N/A`;
              return `${c.dataset.label}: ${(v * 100).toFixed(2)}%`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#9ca3af", font: { size: 10 } },
          grid: { color: "rgba(31, 41, 55, 0.8)" },
        },
        y: {
          beginAtZero: true,
          suggestedMax: 1.0,
          ticks: {
            color: "#9ca3af",
            font: { size: 10 },
            callback: (v) => `${Math.round(v * 100)}%`,
          },
          grid: { color: "rgba(31, 41, 55, 0.8)" },
        },
      },
    },
  });
}

async function loadVisionConfidenceStats() {
  const res = await fetch("/api/v1/vision/confidence_stats");
  if (!res.ok) {
    console.error("failed to fetch confidence stats", res.status);
    return;
  }
  const data = await res.json();
  renderVisionConfidenceChart((data && data.chart) || {});
}