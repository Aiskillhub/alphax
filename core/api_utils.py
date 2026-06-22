"""API 调用工具：重试、超时、错误处理"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from functools import wraps
from typing import Callable


def retry_api(max_retries: int = 3, base_delay: float = 1.0):
    """API 调用重试装饰器，指数退避"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except urllib.error.HTTPError as e:
                    last_error = e
                    if e.code in (429, 503):
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    raise
                except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2 ** attempt))
                        continue
                    raise
            raise last_error  # type: ignore[misc]
        return wrapper
    return decorator


def call_deepseek(
    prompt: str,
    api_key: str,
    base_url: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 500,
    timeout: int = 30,
) -> str:
    """调用 DeepSeek Chat API，返回文本内容"""
    data = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    @retry_api(max_retries=3, base_delay=1.0)
    def _call():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]

    return _call()


def extract_json(text: str) -> str:
    """从 LLM 回复中提取 JSON 字符串"""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()
