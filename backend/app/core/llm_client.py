import json

import httpx

from app.config import get_settings


class LLMClient:
    """大模型客户端。

    注意：不在 __init__ 里缓存 endpoint/api_key/model 等字段——早期实现会在进程启动时
    把配置"拍扁"存成实例属性，导致管理员在"系统设置"页修改了 LLM 配置后，除非重启进程
    否则完全不会生效（因为 llm_client 是模块级单例，只会被 import 一次）。现在每次调用都
    从 get_settings() 现读，保证系统设置页保存后立即对新请求生效，无需重启。
    """

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        settings = get_settings()
        headers = {"Content-Type": "application/json"}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            resp = await client.post(f"{settings.LLM_ENDPOINT}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2048):
        settings = get_settings()
        headers = {"Content-Type": "application/json"}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            async with client.stream("POST", f"{settings.LLM_ENDPOINT}/chat/completions", json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content


class EmbeddingClient:
    """向量模型客户端，同样每次调用现读配置，避免修改配置后需要重启才生效。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        settings = get_settings()
        from app.core.runtime_config import get_extra

        # 向量服务的鉴权密钥优先使用专门配置的 EMBEDDING_API_KEY，
        # 未配置时回退到 LLM_API_KEY（很多部署里 LLM 与 Embedding 共用同一个网关/密钥），
        # 修复了早期实现完全不发送鉴权头、导致需要鉴权的第三方 Embedding 服务必定 401 的问题。
        api_key = get_extra("EMBEDDING_API_KEY") or settings.LLM_API_KEY
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": settings.EMBEDDING_MODEL_NAME, "input": texts}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{settings.EMBEDDING_ENDPOINT}/embeddings", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]


llm_client = LLMClient()
embedding_client = EmbeddingClient()
