"""Builds the realtime model config (Azure OpenAI or OpenAI) and the RealtimeRunner."""

from agents.realtime import (
    RealtimeAgent,
    RealtimeModelConfig,
    RealtimeRunConfig,
    RealtimeRunner,
    RealtimeSessionModelSettings,
)

from app.config import Settings


def azure_realtime_url(s: Settings) -> str:
    """GA endpoint: wss://<resource>.openai.azure.com/openai/v1/realtime?model=<deployment>."""
    endpoint = s.azure_openai_endpoint.strip().rstrip("/")
    if endpoint.startswith("https://"):
        ws_base = "wss://" + endpoint.removeprefix("https://")
    elif endpoint.startswith("http://"):
        ws_base = "ws://" + endpoint.removeprefix("http://")
    elif endpoint.startswith(("wss://", "ws://")):
        ws_base = endpoint
    else:
        ws_base = f"wss://{endpoint}"
    # Users sometimes paste the full ".../openai/v1" base URL from the portal.
    for suffix in ("/openai/v1", "/openai"):
        if ws_base.endswith(suffix):
            ws_base = ws_base.removesuffix(suffix)
            break
    return f"{ws_base}/openai/v1/realtime?model={s.azure_realtime_deployment}"


def build_model_settings(s: Settings) -> RealtimeSessionModelSettings:
    settings: RealtimeSessionModelSettings = {
        "audio": {
            "input": {
                "format": "pcm16",
                "transcription": {"model": s.transcribe_model},
                "turn_detection": {
                    "type": "semantic_vad",
                    "interrupt_response": True,
                    "eagerness": s.vad_eagerness,
                },
            },
            "output": {"format": "pcm16", "voice": s.voice, "speed": s.voice_speed},
        },
        "tool_choice": "auto",
    }
    return settings


def build_model_config(s: Settings) -> RealtimeModelConfig:
    settings = build_model_settings(s)
    if s.provider == "azure":
        return {
            "url": azure_realtime_url(s),
            "headers": {"api-key": s.azure_openai_api_key},
            # The SDK echoes model_name in session.update; on Azure that must be the deployment.
            # Server-side tracing is an OpenAI-platform feature, so it is turned off for Azure.
            "initial_model_settings": {
                **settings,
                "model_name": s.azure_realtime_deployment,
                "tracing": None,
            },
        }
    return {
        "api_key": s.openai_api_key,
        "initial_model_settings": {**settings, "model_name": s.openai_realtime_model},
    }


def build_run_config(s: Settings) -> RealtimeRunConfig:
    return {
        # Check the guardrail every ~60 characters of transcript so dosing advice is cut early.
        "guardrails_settings": {"debounce_text_length": 60},
        "tracing_disabled": s.provider == "azure",
    }


def build_runner(starting_agent: RealtimeAgent, s: Settings) -> RealtimeRunner:
    return RealtimeRunner(starting_agent, config=build_run_config(s))
