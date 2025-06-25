# app/config.py
import json
import os

class ConfigManager:

    def __init__(self, path):
        self.path = path
        self.defaults = {
            'auto_start_logging': True
        }

    def load(self):
        try:
            with open(self.path, 'r') as f:
                config = json.load(f)
                # デフォルト値にないキーを補完
                for key, value in self.defaults.items():
                    config.setdefault(key, value)
                return config
        except (FileNotFoundError, json.JSONDecodeError):
            return self.defaults.copy()

    def save(self, config):

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(config, f, indent=4)
