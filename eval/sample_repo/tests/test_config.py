import json

import pytest
from shop.config import api_key, get_timeout, load_config


def test_load_config(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"timeout": 5}))
    assert load_config(p)["timeout"] == 5
    assert load_config(p)["region"] == "eu-west-1"


def test_api_key_missing(monkeypatch):
    monkeypatch.delenv("SHOP_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        api_key()


def test_get_timeout():
    assert get_timeout({}) == 30
