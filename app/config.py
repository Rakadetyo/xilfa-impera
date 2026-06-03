import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    APP_NAME = "Impera"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
