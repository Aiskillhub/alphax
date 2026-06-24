"""AlphaX Taste — 给 AI 装上品味

来自 taste-skill + stop-slop 的思路，不加 Node 依赖。
改 prompt 就能去除 AI 味，输出有品味的内容。
"""

# ── 禁止的 AI 套话 ──

BANNED_WORDS = [
    "revolutionary", "game-changer", "unleash", "supercharge",
    "unlock your potential", "transform your workflow", "next level",
    "cutting-edge", "state-of-the-art", "innovative solution",
    "seamless", "robust", "scalable", "best-in-class",
    "leveraging cutting-edge", "unprecedented", "paradigm shift",
    "值得一提的是", "在当今", "不得不说", "极大地",
    "definitely", "truly", "certainly", "indeed", "very", "extremely",
]

# ── 品味命名指南 ──

TASTE_NAMING_PROMPT = """产品命名规则：
- 不要 "Smart X — Get Organized Instantly" 这种模板名
- 要像人真会用的名字：短、有性格、好记
- 好的例子：番茄钟、灵感捕手、比价狗、文案狗
- 坏的例子：Smart Task Organizer、One-Click Data Analyzer Pro"""

# ── 品味设计指南 ──

TASTE_DESIGN_PROMPT = """UI 设计规则：
- 不要紫色渐变（人人都在用）
- 不要太空主题（过时了）
- 暗色可以，但要有品牌色，不只用 #6366f1
- 字体层级清晰，不是所有字一样大
- 留白 > 填满
- 交互有反馈，不是死点"""

# ── 品味文案指南 ──

TASTE_COPY_PROMPT = """产品描述规则：
- 不说"革命性的"、"强大的"、"一键式"
- 直接说这个产品能干什么
- 用短句。不超过 15 个字。
- 像跟朋友推荐，不像广告
- 例子：不好："这个革命性的工具能极大提升你的工作效率"
       好："25 分钟专注，5 分钟休息。就这些。" """


def clean_slop(text: str) -> str:
    """去掉 AI 味套话。"""
    cleaned = text
    for word in BANNED_WORDS:
        cleaned = cleaned.replace(word, "")
        cleaned = cleaned.replace(word.title(), "")
    # 压缩多余空格
    import re
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()


def taste_score(text: str) -> float:
    """评分：这段文字有多少 AI 味（0=人写的，100=典型AI）。"""
    score = 0
    text_lower = text.lower()
    for word in BANNED_WORDS:
        if word.lower() in text_lower:
            score += 5
    return min(100, score)
