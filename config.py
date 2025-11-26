# config.py

import os


class Config:
    # -----------------------------------
    # 기본 설정
    # -----------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # -----------------------------------
    # 데이터베이스(MariaDB) 설정
    # -----------------------------------
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "1234")
    DB_HOST = os.getenv("DB_HOST", "172.30.1.29")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "SynchroBots")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # -----------------------------------
    # 필요 시 옵션 확장
    # -----------------------------------
    JSON_AS_ASCII = False  # 한글 JSON 처리용
