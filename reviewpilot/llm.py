import os


def deepseek_llm(prompt: str, model: str | None = None) -> str:
    return deepseek_chat([{"role": "user", "content": prompt}], model=model)


def deepseek_chat(messages: list[dict], model: str | None = None) -> str:
    import litellm
    model = model or os.environ.get("RP_MODEL", "deepseek/deepseek-v4-flash")
    resp = litellm.completion(
        model=model,
        messages=messages,
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    )
    return resp.choices[0].message.content
