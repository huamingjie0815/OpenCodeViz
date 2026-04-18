from codeviz.runtime_config import extractor_mode, fallback_mode


def test_runtime_modes_prefer_env_over_config(monkeypatch) -> None:
    monkeypatch.setenv("CODEVIZ_EXTRACTOR_MODE", "ast")
    monkeypatch.setenv("CODEVIZ_FALLBACK_MODE", "off")

    assert extractor_mode({"extractorMode": "llm"}) == "ast"
    assert fallback_mode({"fallbackMode": "always"}) == "off"


def test_runtime_modes_default_to_hybrid_and_auto(monkeypatch) -> None:
    monkeypatch.delenv("CODEVIZ_EXTRACTOR_MODE", raising=False)
    monkeypatch.delenv("CODEVIZ_FALLBACK_MODE", raising=False)

    assert extractor_mode({}) == "hybrid"
    assert fallback_mode({}) == "auto"
