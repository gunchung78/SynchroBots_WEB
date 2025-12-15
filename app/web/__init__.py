from flask import Blueprint

web_bp = Blueprint("web_bp", __name__)

from . import routes  # noqa: F401  (라우트 등록 위해 import)