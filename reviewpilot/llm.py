"""LLM provider 适配(provider 中立)。

经 litellm 调用,**按模型前缀让 litellm 自动选 provider 原生 key**
(deepseek/* → DEEPSEEK_API_KEY,openai/* → OPENAI_API_KEY,anthropic/* → ANTHROPIC_API_KEY),
不再硬绑 DeepSeek。模型解析优先级:显式 override > 阶段 env(RP_MODEL_<STAGE>)> RP_MODEL > 默认。
"""

import os
import warnings

# 进程级精准过滤 litellm 内部那条 pydantic 序列化告警(跨线程/延迟序列化也能盖住),
# 只针对这一条,不误伤用户代码的真实 warning。
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=r".*Pydantic serializer warnings.*",
)

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"


def resolve_model(stage: str | None = None, override: str | None = None) -> str:
    if override:
        return override
    if stage:
        staged = os.environ.get(f"RP_MODEL_{stage.upper()}")
        if staged:
            return staged
    return os.environ.get("RP_MODEL", DEFAULT_MODEL)


def chat(
    messages: list[dict],
    model: str | None = None,
    stage: str | None = None,
    timeout: float = 60.0,
) -> str:
    import warnings
    import litellm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        resp = litellm.completion(
            model=resolve_model(stage, model),
            messages=messages,
            temperature=0,
            timeout=timeout,
        )
    return resp.choices[0].message.content


def complete(prompt: str, model: str | None = None, stage: str | None = None) -> str:
    return chat([{"role": "user", "content": prompt}], model=model, stage=stage)


def chat_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    stage: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """带工具(function-calling)的一步对话。返回 {content, calls, assistant_msg}:
    - calls: [{id, name, args(dict)}] 模型本步要调的工具(已解析参数)
    - assistant_msg: 供把本步回填进 messages 继续多轮(含 API 格式的 tool_calls)
    与 litellm 细节解耦,便于注入测试。"""
    import json
    import warnings
    import litellm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        resp = litellm.completion(
            model=resolve_model(stage, model),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            timeout=timeout,
        )
    msg = resp.choices[0].message
    raw_calls = msg.tool_calls or []
    calls = []
    for tc in raw_calls:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        calls.append({"id": tc.id, "name": tc.function.name, "args": args})
    assistant_msg = {"role": "assistant", "content": msg.content or ""}
    if raw_calls:
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in raw_calls
        ]
    return {
        "content": msg.content or "",
        "calls": calls,
        "assistant_msg": assistant_msg,
    }
