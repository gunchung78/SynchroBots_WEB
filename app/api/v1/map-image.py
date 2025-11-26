from flask import Blueprint, send_file
from PIL import Image
import io

api_dashboard_bp = Blueprint("api_dashboard", __name__)

from flask import send_file
from PIL import Image
import io
import os

MAP_DIR = "data/maps"

@api_dashboard_bp.route("/map-image")
def map_image():
    path = os.path.join(MAP_DIR, "map.pgm")
    img = Image.open(path)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png")
