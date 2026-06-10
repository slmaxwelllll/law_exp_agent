"""提示词模块 —— 从 .md 文件加载各阶段 system prompt"""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def _read_prompt(filename: str) -> str:
    """读取 prompts 目录下的 .md 文件内容"""
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


STAGE_KW_DOMAIN_PROMPT = _read_prompt("stage_kw_domain.md")
STAGE_2_A_SYSTEM_PROMPT = _read_prompt("stage2_A_prompt.md")
STAGE_2_B_SYSTEM_PROMPT = _read_prompt("stage2_B_prompt.md")
STAGE3_CLUSTER_PROMPT = _read_prompt("stage3_cluster_prompt.md")
STAGE3_INDUCE_PROMPT = _read_prompt("stage3_induce_prompt.md")
