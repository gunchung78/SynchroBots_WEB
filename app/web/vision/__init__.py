# app/web/vision/__init__.py

from flask import Blueprint

vision_bp = Blueprint("vision", __name__)

from . import routes