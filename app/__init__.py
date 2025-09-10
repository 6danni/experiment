# from app import models

import logging
import os
from flask import Flask, request, current_app, json
# from flask_sqlalchemy import SQLAlchemy
# from flask_migrate import Migrate
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from config import Config
import firebase_admin
from firebase_admin import credentials, db as rtdb
from dotenv import load_dotenv


# db = SQLAlchemy()
# migrate = Migrate()
bootstrap = Bootstrap()
moment = Moment()


def create_app(config_class=Config):
    # app = Flask(__name__)
    load_dotenv() 
    app = Flask(__name__, static_url_path='')
    app.config.from_object(config_class)

    # db.init_app(app)
    bootstrap.init_app(app)
    moment.init_app(app)
    print(os.path.dirname(os.path.abspath(__file__)))
    
    # cred_json = os.environ["FIREBASE_SERVICE_ACCOUNT"]
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    db_url = os.environ.get("FIREBASE_DB_URL")

    # init firebase (if not already initialized)
    if (not len(firebase_admin._apps)):
        # cred = credentials.Certificate(Config.FIREBASE_SECRET_PATH)
        cred = credentials.Certificate(json.loads(cred_json))
        if not cred:
            cred = credentials.Certificate(cred_json)
        # cred = credentials.Certificate('./secret.json')
        # cred = credentials.Certificate(Config.FIREBASE_SECRET)
        firebase_app = firebase_admin.initialize_app(cred, {
            # 'databaseURL': 'https://causal-support-interface-default-rtdb.firebaseio.com'
            'databaseURL': 'https://experiment-78b43-default-rtdb.firebaseio.com/'
            # 'databaseURL': "https://causal-support-default-rtdb.firebaseio.com"
        })
    # else:
    #     firebase_app = firebase_admin.get_app()

    # @app.route('/<path:path>')
    # def send_files(path):
    #     return send_from_directory('static', path)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    print(firebase_app)

    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    

    return app
