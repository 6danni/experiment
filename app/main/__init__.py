from flask import Blueprint
bp = Blueprint('main', __name__)
from app.main import routes
from app.main import chat
from app.main import firebase, metrics
from app.main import pair
from app.main import assignments, catalog, comparison, demographics