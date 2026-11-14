import os

import uvicorn

from app.config import load_env

load_env()
uvicorn.run("app.main:app", host=os.environ["APP_HOST"], port=int(os.environ["APP_PORT"]))
