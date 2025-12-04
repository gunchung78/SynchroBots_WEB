# app/api/v1/vision_api.py

from flask import Blueprint, request, jsonify

from app import db

vision_api_bp = Blueprint("vision_api", __name__)