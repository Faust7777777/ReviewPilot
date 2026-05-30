import os


def deepseek_llm(prompt: str, model: str | None = None) -> str:
    import litellm
    model = model or os.environ.get("RP_MODEL", "deepseek/deepseek-v4-flash")
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    )
    return resp.choices[0].message.content
