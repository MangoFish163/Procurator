import pytest
from app.core.security import verify_token, resolve_role
from app.core.config import config

def test_single_token_fallback(mocker):
    # 模拟单 Token 配置
    mock_config = {
        "API_TOKEN": "single-token",
        "API_ROLE": "admin",
        "API_TOKENS": None
    }
    mocker.patch.object(config, "get", side_effect=lambda k, default=None: mock_config.get(k, default))
    
    assert verify_token("single-token") is True
    assert verify_token("wrong-token") is False
    assert resolve_role("single-token") == "admin"

def test_multi_token_json(mocker):
    # 模拟多 Token JSON 配置
    tokens_map = {"tk1": "ops", "tk2": "dev"}
    import json
    mock_config = {
        "API_TOKENS": json.dumps(tokens_map),
        "API_ROLE": "public"
    }
    mocker.patch.object(config, "get", side_effect=lambda k, default=None: mock_config.get(k, default))
    
    assert verify_token("tk1") is True
    assert resolve_role("tk1") == "ops"
    assert verify_token("tk2") is True
    assert resolve_role("tk2") == "dev"
    assert verify_token("tk3") is False

def test_multi_token_list(mocker):
    # 模拟逗号分隔的 Token 列表
    mock_config = {
        "API_TOKENS": "tk_a, tk_b",
        "API_ROLE": "trusted"
    }
    mocker.patch.object(config, "get", side_effect=lambda k, default=None: mock_config.get(k, default))
    
    assert verify_token("tk_a") is True
    assert resolve_role("tk_a") == "trusted"
    assert verify_token("tk_b") is True
    assert resolve_role("tk_b") == "trusted"
