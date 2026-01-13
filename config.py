import os

class Config:
    SECRET_KEY = "supersegreto"
    SQLALCHEMY_DATABASE_URI = "sqlite:///orario_scolastico.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
