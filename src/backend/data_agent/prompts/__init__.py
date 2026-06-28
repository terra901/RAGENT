"""所有 LLM prompt 集中点。system 模板从 templates/*.md 加载，user 模板与组装代码在各 .py 里。"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=None)
def load_system_prompt(name: str) -> str:
    """读取 `prompts/templates/<name>.md` 作为 system prompt 字符串。

    缓存到进程退出；编辑模板后需重启进程才会生效。
    末尾的换行被剥除，保持与原内联字符串一致的行为。
    """
    path = files(__package__).joinpath("templates", f"{name}.md")
    return path.read_text(encoding="utf-8").rstrip("\n")
