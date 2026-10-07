import pytest

from app.config import Settings
from app.realtime_factory import azure_realtime_url, build_model_config, build_run_config


def make_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "REALTIME_PROVIDER",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_REALTIME_DEPLOYMENT",
        "OPENAI_API_KEY",
        "OPENAI_REALTIME_MODEL",
        "REALTIME_VOICE",
        "AGENT_MODE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_azure_url_and_headers() -> None:
    s = make_settings(
        azure_openai_endpoint="https://my-res.openai.azure.com/",
        azure_openai_api_key="secret",
        azure_realtime_deployment="gpt-realtime-prod",
    )
    cfg = build_model_config(s)
    assert cfg["url"] == "wss://my-res.openai.azure.com/openai/v1/realtime?model=gpt-realtime-prod"
    assert cfg["headers"] == {"api-key": "secret"}
    assert "api_key" not in cfg
    settings = cfg["initial_model_settings"]
    assert settings["model_name"] == "gpt-realtime-prod"
    turn = settings["audio"]["input"]["turn_detection"]
    assert turn["type"] == "semantic_vad" and turn["interrupt_response"] is True
    assert settings["audio"]["output"] == {"format": "pcm16", "voice": "ash", "speed": 1.15}
    assert build_run_config(s)["tracing_disabled"] is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://my-res.openai.azure.com",
        "https://my-res.openai.azure.com/openai/v1/",
        "my-res.openai.azure.com",
        "wss://my-res.openai.azure.com",
    ],
)
def test_azure_url_normalization(endpoint: str) -> None:
    s = make_settings(azure_openai_endpoint=endpoint, azure_realtime_deployment="dep")
    url = azure_realtime_url(s)
    assert url == "wss://my-res.openai.azure.com/openai/v1/realtime?model=dep"
    assert "openai/realtime?api-version" not in url


def test_openai_fallback_config() -> None:
    s = make_settings(provider="openai", openai_api_key="sk-test")
    cfg = build_model_config(s)
    assert cfg["api_key"] == "sk-test"
    assert "url" not in cfg and "headers" not in cfg
    assert cfg["initial_model_settings"]["model_name"] == "gpt-realtime-2.1"


def test_env_vars_select_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALTIME_PROVIDER", "openai")
    monkeypatch.setenv("REALTIME_VOICE", "marin")
    monkeypatch.setenv("AGENT_MODE", "single")
    monkeypatch.setenv("AZURE_OPENAI_REALTIME_DEPLOYMENT", "my-dep")
    s = make_settings()
    assert s.provider == "openai"
    assert s.voice == "marin"
    assert s.agent_mode == "single"
    assert s.azure_realtime_deployment == "my-dep"


def test_missing_credentials() -> None:
    assert make_settings().missing_credentials() == [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
    ]
    assert make_settings(provider="openai").missing_credentials() == ["OPENAI_API_KEY"]
    ok = make_settings(azure_openai_endpoint="https://x", azure_openai_api_key="k")
    assert ok.missing_credentials() == []
