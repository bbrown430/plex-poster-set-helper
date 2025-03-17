# config.py
from pydantic_settings import BaseSettings
from pydantic import validator
import json
import os

class Settings(BaseSettings):
    base_url: str = ""
    token: str = ""
    tv_library: list = []
    movie_library: list = []
    mediux_filters: list = []

    model_config = {
        "env_file": ".env"
    }

    def __init__(self, **data):
        super().__init__(**data)
        if os.path.exists("config.json"):
            with open("config.json") as f:
                config_data = json.load(f)
                self.base_url = config_data.get("base_url", self.base_url)
                self.token = config_data.get("token", self.token)
                self.tv_library = config_data.get("tv_library", self.tv_library)
                self.movie_library = config_data.get("movie_library", self.movie_library)
                self.mediux_filters = config_data.get("mediux_filters", self.mediux_filters)