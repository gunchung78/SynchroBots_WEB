# app/api/v1/dashboard_api.py

from flask import Blueprint, jsonify, send_file, request, Response, stream_with_context
from sqlalchemy import text, desc, func, union_all, literal, and_
from app import db
import queue
import json, time

from app.models.dashboard import (
    ControlLog,
    EquipmentInfo,
    Map,
    AmrStateLog,
)


from PIL import Image
import numpy as np
import io
import os

dashboard_api_bp = Blueprint("dashboard_api", __name__)


# ====== 대시보드 SSE용 간단 브로드캐스터 ======

_dashboard_subscribers: set[queue.Queue] = set()

def publish_dashboard_event(event: dict):
    """
    대시보드로 푸시할 이벤트 공통 함수.
    예) publish_dashboard_event({"type": "amr_state", "payload": {...}})
    """
    dead_queues = []
    for q in list(_dashboard_subscribers):
        try:
            q.put_nowait(event)
        except Exception:
            # 꽉 찌거나 에러난 큐는 제거 후보
            dead_queues.append(q)

    for q in dead_queues:
        _dashboard_subscribers.discard(q)


@dashboard_api_bp.route("/stream", methods=["GET"])
def dashboard_stream():
    """
    대시보드용 SSE 타이머
    클라이언트: new EventSource('/api/v1/dashboard/stream')
    3~10초마다 'tick' 이벤트를 보내서 프론트가 각 API를 다시 호출하게 만듦
    """
    INTERVAL_SEC = 3  # 원하면 3~10 사이에서 조정

    def event_stream():
        # 최초 한 번 연결 확인용
        hello = {
            "type": "hello",
            "payload": {"msg": "dashboard stream connected"},
        }
        yield f"data: {json.dumps(hello, ensure_ascii=False)}\n\n"

        while True:
            tick = {
                "type": "tick",
                "payload": {"ts": time.time()},
            }
            yield f"data: {json.dumps(tick, ensure_ascii=False)}\n\n"
            time.sleep(INTERVAL_SEC)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
    )

# === MAP 공통 상수 ===

# 프로젝트 기준 경로
BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
MAP_DIR = os.path.join(BASE_DIR, "data", "maps")

# 캡처 기준 해상도 (네가 잡아둔 값)
BASE_W = 725
BASE_H = 683

# 확대 정도
ZOOM_FACTOR = 1.4

# 기준 ROI (원본 캡처에서 실제 맵 영역)
BASE_ROI = (260, 230, 500, 440)

# 🔧 나중에 map.yaml 보고 실제 값으로 바꾸면 됨
ORIGIN_X = -11.5      # 예시
ORIGIN_Y = -18      # 예시
RESOLUTION = 0.05     # 예: 1픽셀 = 0.05 m


def _load_active_map_image():
    """
    DB에서 active 맵 1건을 찾아서
    PGM 이미지를 로드하고 (PIL Image), 가로/세로 픽셀을 반환.
    """
    active_map = (
        Map.query
        .order_by(desc(Map.created_at))
        .first()
    )

    if not active_map:
        return None, None, None, "no active map found"

    filename = active_map.map_image or "map.pgm"
    pgm_path = os.path.join(MAP_DIR, filename)

    if not os.path.exists(pgm_path):
        return None, None, None, f"map file not found: {pgm_path}"

    img = Image.open(pgm_path).convert("L")
    w, h = img.size
    return img, w, h, None


def _compute_crop_rect(img_w, img_h):
    """
    원본 이미지 크기(img_w, img_h)를 기준으로
    BASE_ROI + ZOOM_FACTOR 를 적용한 실제 crop 영역을 계산.
    반환: (x_min, y_min, x_max, y_max)
    """
    base_x_min, base_y_min, base_x_max, base_y_max = BASE_ROI
    base_w = base_x_max - base_x_min
    base_h = base_y_max - base_y_min

    # 중심점
    cx = base_x_min + base_w / 2.0
    cy = base_y_min + base_h / 2.0

    # 확대: 폭/높이를 줄임
    zoomed_w = base_w / ZOOM_FACTOR
    zoomed_h = base_h / ZOOM_FACTOR

    zoom_x_min = cx - zoomed_w / 2.0
    zoom_x_max = cx + zoomed_w / 2.0
    zoom_y_min = cy - zoomed_h / 2.0
    zoom_y_max = cy + zoomed_h / 2.0

    # 실제 이미지 해상도에 맞게 스케일링
    scale_x = img_w / float(BASE_W)
    scale_y = img_h / float(BASE_H)

    x_min = int(zoom_x_min * scale_x)
    x_max = int(zoom_x_max * scale_x)
    y_min = int(zoom_y_min * scale_y)
    y_max = int(zoom_y_max * scale_y)

    # 이미지 범위 안으로 클램핑
    x_min = max(0, min(x_min, img_w - 1))
    x_max = max(0, min(x_max, img_w))
    y_min = max(0, min(y_min, img_h - 1))
    y_max = max(0, min(y_max, img_h))

    return x_min, y_min, x_max, y_max

@dashboard_api_bp.route("/map-image", methods=["GET"])
def map_image():
    img, w, h, err = _load_active_map_image()
    if err:
        return jsonify({"error": err}), 404

    mode = request.args.get("mode", "crop")

    # 1) 전체 원본 보기
    if mode == "raw":
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    # 2) crop 영역 계산
    x_min, y_min, x_max, y_max = _compute_crop_rect(w, h)

    if x_max - x_min < 10 or y_max - y_min < 10:
        # 안전장치: 뭔가 잘못되면 원본 리턴
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    cropped = img.crop((x_min, y_min, x_max, y_max))

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@dashboard_api_bp.route("/map-meta", methods=["GET"])
def get_map_meta():
    """
    프론트가 좌표 변환할 수 있도록
    맵/크롭 관련 메타데이터를 내려주는 API
    """
    img, w, h, err = _load_active_map_image()
    if err:
        return jsonify({"error": err}), 404

    x_min, y_min, x_max, y_max = _compute_crop_rect(w, h)

    crop_w = x_max - x_min
    crop_h = y_max - y_min

    return jsonify({
        "origin_x": ORIGIN_X,
        "origin_y": ORIGIN_Y,
        "resolution": RESOLUTION,   # meter → pixel 전환
        "img_width": w,
        "img_height": h,
        "crop_x_min": x_min,
        "crop_y_min": y_min,
        "crop_w": crop_w,
        "crop_h": crop_h,
    }), 200

# === Control Logs (제어 명령 로그) ===

def _get_limit(default=10, max_limit=100):
    try:
        limit = int(request.args.get("limit", default))
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, max_limit))


@dashboard_api_bp.route("/control_logs", methods=["GET"])
def get_control_logs():
    limit = _get_limit(default=10)

    logs = (
        ControlLog.query
        .order_by(desc(ControlLog.created_at))
        .limit(limit)
        .all()
    )

    return jsonify({
        "items": [log.to_dict() for log in logs]
    })


from sqlalchemy import text

@dashboard_api_bp.route("/mission_logs", methods=["GET"])
def get_mission_logs():
    """
    장비(equipment_id)별 가장 최신 1건(PLC + AMR/ARM) 반환

    GET /api/v1/dashboard/mission_logs?limit=5
    """
    try:
        limit = _get_limit(default=5, max_limit=50)

        sql = text("""
        SELECT
          r.equipment_id,
          r.equipment_type,
          r.action_type,
          r.status,
          r.description,
          r.created_at,
          ei.equipment_name
        FROM (
          /* =========================
             1) PLC : equipment_id별 최신 1건
             ========================= */
          SELECT
            mpl.equipment_id,
            'PLC' AS equipment_type,
            'IO' AS action_type,
            'RUNNING' AS status,
            mpl.description AS description,
            mpl.created_at AS created_at
          FROM mission_plc_logs mpl
          JOIN (
            SELECT equipment_id, MAX(created_at) AS max_created_at
            FROM mission_plc_logs
            GROUP BY equipment_id
          ) p_latest
            ON p_latest.equipment_id = mpl.equipment_id
           AND p_latest.max_created_at = mpl.created_at

          UNION ALL

          /* =========================
             2) AMR/ARM : (미션별 첫 세부로그) 중 equipment_id별 최신 1건
             ========================= */
          SELECT
            t.equipment_id,
            t.equipment_type,
            t.action_type,
            t.status,
            t.description,
            t.created_at
          FROM (
            /* ---- AMR: mission_id별 첫 세부로그 ---- */
            SELECT
              ml.equipment_id,
              'AMR' AS equipment_type,
              mal.action_type AS action_type,
              ml.status AS status,
              COALESCE(
                mal.description,
                CONCAT(COALESCE(mal.source_station, '-'), ' → ', COALESCE(mal.target_station, '-'))
              ) AS description,
              mal.created_at
            FROM mission_logs ml
            JOIN mission_amr_logs mal
              ON mal.mission_id = ml.mission_id
            WHERE mal.created_at = (
              SELECT MIN(mal2.created_at)
              FROM mission_amr_logs mal2
              WHERE mal2.mission_id = ml.mission_id
            )

            UNION ALL

            /* ---- ARM: mission_id별 첫 세부로그 ---- */
            SELECT
              ml.equipment_id,
              'ARM' AS equipment_type,
              CONCAT(mrl.action_type, '(', COALESCE(mrl.module_type, ''), ')') AS action_type,
              ml.status AS status,
              COALESCE(mrl.description, mrl.target_pose) AS description,
              mrl.created_at
            FROM mission_logs ml
            JOIN mission_robotarm_logs mrl
              ON mrl.mission_id = ml.mission_id
            WHERE mrl.created_at = (
              SELECT MIN(mrl2.created_at)
              FROM mission_robotarm_logs mrl2
              WHERE mrl2.mission_id = ml.mission_id
            )
          ) t
          JOIN (
            /* 동일 기준으로 equipment_id별 최신 1건 */
            SELECT
              equipment_id,
              MAX(created_at) AS max_created_at
            FROM (
              SELECT ml.equipment_id, mal.created_at
              FROM mission_logs ml
              JOIN mission_amr_logs mal ON mal.mission_id = ml.mission_id
              WHERE mal.created_at = (
                SELECT MIN(mal2.created_at)
                FROM mission_amr_logs mal2
                WHERE mal2.mission_id = ml.mission_id
              )

              UNION ALL

              SELECT ml.equipment_id, mrl.created_at
              FROM mission_logs ml
              JOIN mission_robotarm_logs mrl ON mrl.mission_id = ml.mission_id
              WHERE mrl.created_at = (
                SELECT MIN(mrl2.created_at)
                FROM mission_robotarm_logs mrl2
                WHERE mrl2.mission_id = ml.mission_id
              )
            ) x
            GROUP BY equipment_id
          ) latest
            ON latest.equipment_id = t.equipment_id
           AND latest.max_created_at = t.created_at
        ) r
        LEFT JOIN equipment_info ei
          ON ei.equipment_id = r.equipment_id
        ORDER BY r.created_at DESC
        LIMIT :limit
        """)

        rows = db.session.execute(sql, {"limit": limit}).mappings().all()

        items = []
        for row in rows:
            created_at = row["created_at"]
            created_str = (
                created_at.strftime("%Y-%m-%d %H:%M:%S")
                if created_at is not None else None
            )

            items.append({
                "equipment_id": row["equipment_id"],
                "equipment_type": row["equipment_type"],   # PLC / AMR / ARM
                "action_type": row["action_type"],         # PLC=IO, ARM=PLACE(...), AMR=...
                "status": row["status"],                   # RUNNING / WAITING / DONE / ERROR
                "description": row["description"],
                "created_at": created_str,
                "equipment": {
                    "equipment_id": row["equipment_id"],
                    "equipment_name": row["equipment_name"],
                } if row["equipment_name"] is not None else None,
            })

        return jsonify({"count": len(items), "items": items}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    
@dashboard_api_bp.route("/amr_states", methods=["GET"])
def get_latest_amr_states():
    """
    AGV(AMR) 상태 로그에서
    모든 equipment_id 별로 updated_at 기준 최신 1건씩만 조회.
    (특정 ID 조회 기능 제거됨)
    """

    try:
        # 1) equipment_id 별로 가장 최신 updated_at 을 구하는 서브쿼리
        subq = (
            db.session.query(
                AmrStateLog.equipment_id.label("eq_id"),
                func.max(AmrStateLog.updated_at).label("max_updated_at"),
            )
            .group_by(AmrStateLog.equipment_id)
            .subquery()
        )

        # 2) 서브쿼리와 조인하여 실제 최신 상태 row 가져오기
        q = (
            db.session.query(AmrStateLog)
            .join(
                subq,
                and_(
                    AmrStateLog.equipment_id == subq.c.eq_id,
                    AmrStateLog.updated_at == subq.c.max_updated_at,
                ),
            )
            .order_by(AmrStateLog.equipment_id.asc())
        )

        logs = q.all()

        items = []
        for log in logs:
            data = log.to_dict()

            # equipment_info 조인 결과 포함
            if log.equipment:
                data["equipment"] = log.equipment.to_dict()

            items.append(data)

        return jsonify({
            "items": items,
            "count": len(items)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@dashboard_api_bp.route("/amr_summary", methods=["GET"])
def get_amr_summary():
    """
    상단 chip-row용 AMR 요약:
    - equipment_info: equipment_name, status, location
    - 최근 미션 1건: target_station, action_type
    """
    try:
        sql = text("""
        SELECT
          e.equipment_id,
          e.equipment_name,
          e.status,
          e.location,
          mm.target_station,
          mm.action_type,
          mm.misiion_status
        FROM equipment_info e
        LEFT JOIN (
          SELECT
            m.equipment_id,
            am.target_station,
            am.action_type,
            m.status as misiion_status
          FROM mission_logs m
          JOIN mission_amr_logs am
            ON m.mission_id = am.mission_id
          ORDER BY am.created_at DESC
          LIMIT 1
        ) mm
          ON e.equipment_id = mm.equipment_id
        WHERE LOWER(e.equipment_id) LIKE 'amr%'
        ORDER BY e.equipment_id ASC
        """)

        rows = db.session.execute(sql).mappings().all()

        items = []
        for r in rows:
            items.append({
                "equipment_id": r["equipment_id"],
                "equipment_name": r["equipment_name"],
                "status": r["status"],              # 예: RUN / IDLE 등 (equipment_info 기준)
                "location": r["location"],          # 예: PICK-ST01
                "misiion_status" : r["misiion_status"],
                "target_station": r["target_station"],  # 예: ST-03
                "action_type": r["action_type"],        # 예: UNLOADING 등
            })

        return jsonify({"count": len(items), "items": items}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@dashboard_api_bp.route("/vision_mixed", methods=["GET"])
def get_dashboard_vision_mixed():
    """
    대시보드 우측 혼합차트용:
    - 최근 날짜 기준 5일 (데이터 있는 날짜)
    - Bar: classification_confidence 전체 평균(ANOMALY/JOINT 합산)
    - Line: PASS/REJECT 비율 (UNKNOWN 제외)
    """
    try:
        limit_days = _get_limit(default=5, max_limit=30)

        sql = text("""
        SELECT
          t.day AS day,

          t.avg_confidence AS avg_confidence,

          CASE
            WHEN (t.pass_cnt + t.reject_cnt) > 0
            THEN t.pass_cnt / (t.pass_cnt + t.reject_cnt)
            ELSE NULL
          END AS pass_rate,

          CASE
            WHEN (t.pass_cnt + t.reject_cnt) > 0
            THEN t.reject_cnt / (t.pass_cnt + t.reject_cnt)
            ELSE NULL
          END AS reject_rate,

          t.total_cnt AS total_cnt,
          t.pass_cnt  AS pass_cnt,
          t.reject_cnt AS reject_cnt

        FROM (
          SELECT
            d.day AS day,

            COUNT(*) AS total_cnt,
            SUM(mcl.decision = 'PASS')   AS pass_cnt,
            SUM(mcl.decision = 'REJECT') AS reject_cnt,

            AVG(mcl.classification_confidence) AS avg_confidence

          FROM (
            SELECT DATE(created_at) AS day
            FROM mission_camera_logs
            GROUP BY DATE(created_at)
            ORDER BY day DESC
            LIMIT :limit_days
          ) d
          JOIN mission_camera_logs mcl
            ON DATE(mcl.created_at) = d.day
          WHERE mcl.classification_confidence IS NOT NULL
          GROUP BY d.day
        ) t
        ORDER BY t.day ASC;
        """)

        rows = db.session.execute(sql, {"limit_days": limit_days}).mappings().all()

        labels = []
        avg_conf = []
        pass_rate = []
        reject_rate = []
        total_cnt = []
        pass_cnt = []
        reject_cnt = []

        for r in rows:
            # DATE()는 보통 date 객체로 내려옴
            d = r["day"].strftime("%Y-%m-%d") if r["day"] else None
            labels.append(d)

            avg_conf.append(float(r["avg_confidence"]) if r["avg_confidence"] is not None else None)
            pass_rate.append(float(r["pass_rate"]) if r["pass_rate"] is not None else None)
            reject_rate.append(float(r["reject_rate"]) if r["reject_rate"] is not None else None)

            total_cnt.append(int(r["total_cnt"] or 0))
            pass_cnt.append(int(r["pass_cnt"] or 0))
            reject_cnt.append(int(r["reject_cnt"] or 0))

        return jsonify({
            "chart": {
                "labels": labels,
                "avg_confidence": avg_conf,     # bar
                "pass_rate": pass_rate,         # line1
                "reject_rate": reject_rate,     # line2
                "counts": {
                    "total": total_cnt,
                    "pass": pass_cnt,
                    "reject": reject_cnt,
                }
            },
            "meta": {
                "window_type": "recent_days_with_data",
                "limit_days": limit_days,
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    

@dashboard_api_bp.route("/vision_anomaly_modules", methods=["GET"])
def get_dashboard_vision_anomaly_modules():
    """
    좌측 Bar 차트용 (A안):
    - 최근 '데이터가 존재하는 날짜' 기준 5일
    - mode='ANOMALY' AND module_type 기준으로 PASS/REJECT 건수 집계 (UNKNOWN 제외)
    - Chart.js 그룹 바(pass/reject 2개 막대)용 데이터 제공
    """
    try:
        LIMIT_DAYS = 5  # ✅ 하드코딩

        sql = text("""
        SELECT
          t.module_type AS module_type,
          SUM(t.decision = 'PASS')   AS pass_cnt,
          SUM(t.decision = 'REJECT') AS reject_cnt,
          COUNT(*) AS total_cnt
        FROM (
          SELECT DATE(created_at) AS day
          FROM mission_camera_logs
          WHERE mode = 'ANOMALY'
            AND module_type IS NOT NULL
            AND module_type <> ''
          GROUP BY DATE(created_at)
          ORDER BY day DESC
          LIMIT :limit_days
        ) d
        JOIN mission_camera_logs t
          ON DATE(t.created_at) = d.day
        WHERE t.mode = 'ANOMALY'
          AND t.module_type IS NOT NULL
          AND t.module_type <> ''
          AND t.decision IN ('PASS','REJECT')   -- ✅ UNKNOWN 제외
        GROUP BY t.module_type
        ORDER BY total_cnt DESC, pass_cnt DESC;
        """)

        rows = db.session.execute(sql, {"limit_days": LIMIT_DAYS}).mappings().all()

        labels = []
        pass_counts = []
        reject_counts = []
        totals = []

        total_all = 0
        pass_all = 0
        reject_all = 0

        for r in rows:
            mt = r["module_type"]
            p = int(r["pass_cnt"] or 0)
            ng = int(r["reject_cnt"] or 0)
            tot = int(r["total_cnt"] or 0)

            labels.append(mt)
            pass_counts.append(p)
            reject_counts.append(ng)
            totals.append(tot)

            total_all += tot
            pass_all += p
            reject_all += ng

        return jsonify({
            "chart": {
                "labels": labels,
                "pass_counts": pass_counts,
                "reject_counts": reject_counts,
                "totals": totals
            },
            "meta": {
                "limit_days": LIMIT_DAYS,
                "mode": "ANOMALY",
                "total": total_all,
                "pass_total": pass_all,
                "reject_total": reject_all
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500