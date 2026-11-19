import json
import os

DEFAULTS = {"debug": False, "timeout": 30, "region": "eu-west-1"}


def load_config(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {**DEFAULTS, **data}


def api_key():
    key = os.environ.get("SHOP_API_KEY")
    if not key:
        raise RuntimeError("SHOP_API_KEY is not set")
    return key


def db_url():
    return os.environ.get("SHOP_DB_URL", "sqlite:///shop.db")


def get_timeout(cfg):
    return int(cfg.get("timeout", DEFAULTS["timeout"]))
