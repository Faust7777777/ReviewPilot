from reviewpilot.llm import resolve_model, DEFAULT_MODEL


def test_resolve_model_default(monkeypatch):
    monkeypatch.delenv("RP_MODEL", raising=False)
    monkeypatch.delenv("RP_MODEL_CHAT", raising=False)
    assert resolve_model() == DEFAULT_MODEL


def test_resolve_model_env_and_stage_and_override(monkeypatch):
    monkeypatch.setenv("RP_MODEL", "openai/gpt-x")
    assert resolve_model() == "openai/gpt-x"
    assert resolve_model("analyze") == "openai/gpt-x"          # 无阶段 env 时回落 RP_MODEL
    monkeypatch.setenv("RP_MODEL_CHAT", "anthropic/claude-x")
    assert resolve_model("chat") == "anthropic/claude-x"       # 阶段 env 优先
    assert resolve_model("chat", override="z/y") == "z/y"      # 显式 override 最高
