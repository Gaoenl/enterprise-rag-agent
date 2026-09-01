"""阿里云 qwen3-rerank HTTP 客户端。"""

import logging

import httpx

from app.config import get_settings
from app.rag.schemas.rerank_schema import RerankResponse, RerankResultItem


logger = logging.getLogger(__name__)
class RerankClient:
    """负责调用真实的文本排序模型。"""
    def __init__(self)->None:
        """读取 Rerank API 配置。"""
        self._settings = get_settings()
    def rerank(self,
               query:str,
               documents:list[str],
               top_n: int)->list[RerankResultItem]:
        """调用 qwen3-rerank 对候选文档重新排序。"""
        if not query.strip():
            raise ValueError("rerank query must not be blank")

        if not documents:
            return []

        if not self._settings.rerank_base_url:
            raise ValueError("RERANK_BASE_URL must not be blank")

        if not self._settings.rerank_api_key:
            raise ValueError("RERANK_API_KEY must not be blank")

            # top_n 不能超过候选文档总数。
        actual_top_n = min(top_n, len(documents))
        request_body={
            "model":self._settings.rerank_model,
            "documents":documents,
            "query":query,
            "top_n":actual_top_n,
            "instruct":(
                "Given an enterprise knowledge-base question, "
                "rank passages by whether they provide direct evidence "
                "for answering the question."
            ),
        }
        headers = {
            "Authorization": f"Bearer {self._settings.rerank_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(
                    timeout=self._settings.rerank_timeout_seconds
            ) as client:
                response=client.post(
                    self._settings.rerank_base_url,
                    headers=headers,
                    json=request_body,
                )
                # 非 2xx 状态会抛出 HTTPStatusError。
                response.raise_for_status()
                # 使用 Pydantic 校验外部接口返回结构。
                rerank_response = RerankResponse.model_validate(
                    response.json()
                )
            return rerank_response.results
        except httpx.HTTPStatusError as exception:
            logger.error(
                "Rerank API returned error, status=%s, body=%s",
                exception.response.status_code,
                exception.response.text[:1000],
            )
            raise
        except httpx.RequestError:
            logger.exception("Call Rerank API failed")
            raise
        except Exception:
            logger.exception("Parse Rerank API response failed")
            raise
