from typing import Iterable, Set
from urllib.parse import urlsplit


class UrlListSimilarity:
    """用于对比两个 URL/路径列表的相似度（0~1）。"""

    @staticmethod
    def _normalize(urls: Iterable[str]) -> Set[str]:
        """去掉重复、空白，并做 URL 归一化（保留 path，去掉 query 和 fragment）。"""
        normed = set()
        for u in urls:
            if not u:
                continue
            u = u.strip()
            # 只保留路径部分：/path/xxx
            path = urlsplit(u).path  # 'http://x/a?b' -> '/a'
            # 可选：统一大小写、去掉末尾斜杠
            # path = path.rstrip('/') or '/'
            normed.add(path)
        return normed

    @classmethod
    def jaccard(cls, urls1: Iterable[str], urls2: Iterable[str]) -> float:
        """
        计算 Jaccard 相似度:
        |A ∩ B| / |A ∪ B|，返回 0~1 之间的浮点数。
        """
        s1 = cls._normalize(urls1)
        s2 = cls._normalize(urls2)
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        inter = len(s1 & s2)
        union = len(s1 | s2)
        return inter / union
