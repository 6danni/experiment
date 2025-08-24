import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config(object):
    # Basic setup (don't touch these unless you know what you are doing)
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
    APP_STATIC = os.path.join(APP_ROOT, 'static')
    LOCAL = True
    DEBUG = True
    LANGUAGES = ['en', 'es']
    DEV_URL = 'http://localhost'

    # Secret Keys + Firebase Auth
    SECRET_KEY = os.environ.get(
        'SECRET_KEY') or 'this_secret-key-is-so-secretive'
    FIREBASE_SECRET_PATH = './secret/secret.json'

    # Experiment Variables
    N_DATA_CONDS = 18                       # how many different combinations of data manipulations?
    N_TRIALS = N_DATA_CONDS + 1             # how many trials?
    DATA_PATH = './app/main/stimdata2.csv'  # where is the data?
    REWARD = 2.00                           # base reward
    PAYOFF5 = 0.25                          # payoff per trial where absolute error < 5%
    MAX_BONUS = PAYOFF5 * N_TRIALS          # maximum bonus allowed

    # Tags for data processing    
    RUN = "e2"                              # which experiment?
    # BATCH = 0                               # used to approve bonuses (turned this into url param)
    
    # Allow repeat participation? (True: open writing to db; False: no writing to db after submit and no repeat participation per workerId)
    TESTING = False
    REPEAT_USERS = ['dev','alex','jessica','matt', 'yifan', 'A2OGNC09X2CHTN', 'A38B5QC57UTM1H'] 
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_PROMPT_ID='pmpt_68a792c45f448190bf767ed4133e253f0aedd092065c9099'
    OPENAI_PROMPT_VERSION=1
    OPENAI_MODEL='gpt-4.1-mini'
