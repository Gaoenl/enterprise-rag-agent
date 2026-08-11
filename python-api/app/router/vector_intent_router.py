"""向量快路径意图路由。

将每个意图/域的代表句向量化后缓存，查询时与全部代表句做余弦相似度，返回最高分对应的 (意图, 域, 得分, 命中代表句)。
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.clients.embedding_client import EmbeddingClient
from app.config import get_settings
from app.schemas.routing_schema import L0Intent, IntentDomain


@dataclass
class VectorMatch:
    """向量路由匹配结果。"""

    intent: L0Intent
    domain: IntentDomain
    score: float
    matched_example: str

class VectorIntentRouter:
    """基于代表句 embedding 的语义匹配路由器。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._embedding_client = EmbeddingClient()
        # 每条代表句单独向量化，查询时取最大相似度。
        self._entries: list[tuple[L0Intent, IntentDomain, list[float], str]] = []
        self._build_entries()
    def _build_entries(self) -> None:
        examples = self._load_examples()
        for intent_name, domains in examples.items():
            intent = L0Intent(intent_name)
            for domain_name, sentences in domains.items():
                domain = IntentDomain(domain_name)
                for sentence in sentences:
                    vector = self._embedding_client.embed_query(
                        sentence,
                        model=None,
                        dimension=None,
                    )
                    self._entries.append(
                        (intent, domain, vector, sentence)
                    )
    def _load_examples(self) -> dict:
        path = Path(self._settings.intent_examples_file)
        if not path.is_absolute():
            python_api_root = Path(__file__).resolve().parents[1]
            path = python_api_root / path
        with open(path, encoding="utf-8") as file:
            return json.load(file)

    def match(self, query: str) -> VectorMatch:
        """返回与查询最相似的代表句匹配结果。"""
        query_vector = self._embedding_client.embed_query(
            query,
            model=None,
            dimension=None,
        )
        best: VectorMatch | None = None
        for intent, domain, vector, sentence in self._entries:
            score = self._cosine(query_vector, vector)
            if best is None or score > best.score:
                best = VectorMatch(
                    intent=intent,
                    domain=domain,
                    score=score,
                    matched_example=sentence,
                )

        return best

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """计算两个向量的余弦相似度，维度不一致返回 0。"""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
