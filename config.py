import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_sakecha_key_is_here' # MAKE THIS LONG AND RANDOM
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://postgres:SKN04J%b@localhost/sakecha_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False