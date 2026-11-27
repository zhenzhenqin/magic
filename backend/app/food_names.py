import re
import unicodedata

ALIASES = {
    "牛角包": "可颂", "羊角面包": "可颂", "牛角面包": "可颂", "原味可颂": "可颂",
    "可颂(牛角面包)": "可颂", "可颂(牛角包)": "可颂", "可颂牛角面包": "可颂",
    "西红柿炒鸡蛋": "番茄炒蛋", "番茄炒鸡蛋": "番茄炒蛋",
}


def canonical(value: str) -> str:
    key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())
    return ALIASES.get(key, key)[:80]
