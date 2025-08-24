from flask import Blueprint
bp = Blueprint('main', __name__)
from app.main import routes
from app.main import chat
from app.main import firebase
from app.main import pair