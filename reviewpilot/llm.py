"""LLM provider 适配(provider 中立)。

经 litellm 调用,**按模型前缀让 litellm 自动选 provider 原生 key**
(deepseek/* → DEEPSEEK_API_KEY,openai/* → OPENAI_API_KEY,anthropic/* → ANTHROPIC_API_KEY),
不再硬绑 DeepSeek。模型解析优先级:显式 override > 阶段 env(RP_MODEL_<STAGE>)> RP_MODEL > 默认。
"""
import os

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"


def resolve_model(stage: str | None = None, override: str | None = None) -> str:
    if override:
        return override
    if stage:
        staged = os.environ.get(f"RP_MODEL_{stage.upper()}")
        if staged:
            return staged
    return os.environ.get("RP_MODEL", DEFAULT_MODEL)


def chat(messages: list[dict], model: str | None = None, stage: str | None = None) -> str:
    import warnings
    import litellm
    with warnings.catch_warnings():  # 静音 litellm 内部的 pydantic 序列化 UserWarning
        warnings.simplefilter("ignore")
        resp = litellm.completion(
            model=resolve_model(stage, model),
            messages=messages,
            temperature=0,
        )
    return resp.choices[0].message.content


def complete(prompt: str, model: str | None = None, stage: str | None = None) -> str:
    return chat([{"role": "user", "content": prompt}], model=model, stage=stage)
