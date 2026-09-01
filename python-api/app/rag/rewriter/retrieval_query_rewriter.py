"""将独立问题改写为更适合知识库检索的查询。"""
import logging
import re

from langchain_core.prompts import ChatPromptTemplate

from app.rag.retriever.keyword_extractor import KeywordExtractor
from app.rag.schemas.routing_schema import RetrievalQuery

logger = logging.getLogger(__name__)
class RetrievalQueryRewriter:
    """面向向量检索的查询改写器。"""

    def __init__(self, chat_model,keyword_extractor: KeywordExtractor,) -> None:
        self._keyword_extractor = keyword_extractor
        """接收统一创建的 LangChain ChatModel。"""
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
        你是企业知识库 RAG 系统的查询预处理器。

        你的唯一任务是把用户问题转换为混合检索参数。
        只返回结构化结果，不回答用户问题，不解释处理过程。

        ## 一、semantic_query

        用于向量检索。

        要求：

        1. 完整保留原问题的核心语义；
        2. 只允许规范空格、大小写、标点和轻微语序；
        3. 不得添加原问题不存在的背景、条件或事实；
        4. 不得添加“查询知识库”“查找资料”“相关文档”等检索动作词。

        ## 二、keywords

        用于 ILIKE、BM25 等关键词检索。

        必须按照以下步骤生成：

        1. 识别问题中的实体、专有名词、技术术语、业务术语、
           属性、编号、错误码、配置项、类名、接口名和文件名；
        2. 删除疑问词、助词、连接词、礼貌词和检索动作词；
        3. 将复合问句拆分为可以独立匹配的原子关键词；
        4. 对关键词去重；
        5. 返回 1～6 个关键词。

        ### 关键词拆分规则

        - “A中的B”必须拆分为“A”和“B”；
        - “A的B”在 A、B 都能独立表达有效概念时，拆分为“A”和“B”；
        - 不得把包含疑问结构的完整句子或长短语作为关键词；
        - 每个关键词必须能够单独出现在知识库文档中；
        - 优先保留专有名词和技术术语；
        - 若只有一个有效关键词，只返回一个；
        - 不得为了满足数量要求生成无意义关键词；
        - 不得同义改写或添加原问题中没有出现的词。

        ### 必须删除的内容

        包括但不限于：

        “什么”“是什么”“有什么”“如何”“怎么”“怎样”
        “为什么”“是否”“能否”“请问”
        “的”“中的”“是”
        “查询”“查找”“搜索”“知识库”“资料”“文档”“相关”。

        删除上述内容后，不能把删除前的完整问句保留为关键词。

        ### 错误与正确示例

        用户问题：
        LangChain中的Agent是什么？

        错误关键词：
        ["LangChain中的Agent是什么"]

        错误关键词：
        ["LangChain Agent是什么"]

        正确关键词：
        ["LangChain", "Agent"]

        用户问题：
        Spring中的Bean是如何创建的？

        错误关键词：
        ["Spring中的Bean是如何创建的"]

        正确关键词：
        ["Spring", "Bean", "创建"]

        用户问题：
        MyBatis的resultMap有什么作用？

        错误关键词：
        ["MyBatis的resultMap有什么作用"]

        正确关键词：
        ["MyBatis", "resultMap", "作用"]

        用户问题：
        错误码E2001如何处理？

        正确关键词：
        ["E2001", "错误码", "处理"]

        用户问题：
        查询张三提交的采购审批流程

        正确关键词：
        ["张三", "采购审批", "流程"]

        ## 三、alternative_queries

        用于多查询召回（Multi-Query Retrieval）：

        1. 当用户问题存在多个理解角度或可拆分的子主题时，
           生成 2～3 个覆盖不同角度的独立检索查询；
        2. 角度示例：按“过程 / 时长 / 结果 / 政策 / 条件”拆分；
        3. 每个子查询必须是可独立检索的问题或短语，
           不得包含“查询 / 检索 / 知识库”等动作词；
        4. 保持原文用语，不做同义改写；
        5. 单主题问题返回空列表 []。

        示例：
        用户问题：退款需要多久
        alternative_queries：
        ["退款审核需要多久", "退款到账需要几天", "退款政策是什么"]

        用户问题：你好
        alternative_queries：[]

        ## 四、synonym_keywords

        为 keywords 中的每个关键词生成 1～2 个真实同义/近义变体，
        用于扩大关键词检索覆盖面：

        1. 必须与原文语义等价，允许领域习惯说法
           （如「差旅」→「出差」、「报销」→「费用报销」）；
        2. 不得生成泛化到无关语义的词；
        3. 与 keywords 内容去重，总数不超过 6 个；
        4. 单义、无常见变体的关键词可以不给变体；
        5. 无法给出任何同义词时返回空列表 []。

        示例：
        用户问题：差旅费能报多少
        keywords：["差旅", "报销"]
        synonym_keywords：["出差", "费用报销", "费用"]

        用户问题：你好
        synonym_keywords：[]

        最终只返回符合结构定义的数据。
        """,
                ),
                (
                    "human",
                    "用户问题：{query}",
                ),
            ]
        )
        # 要求模型按照 RetrievalQuery 结构返回数据。
        structured_model = chat_model.with_structured_output(RetrievalQuery)
        self._chain = self._prompt|structured_model

    def rewrite(self, query: str) -> RetrievalQuery:
        """生成混合检索参数。"""
        normalized_query = query.strip()
        try:
            # 调用模型生成结构化检索查询。
            result  = self._chain.invoke({"query": normalized_query})
            # 清理模型返回的重复关键词和空关键词。
            # 使用统一提取器清理模型返回的关键词。
            # 使用统一提取器清理模型返回的关键词。
            keywords = self._keyword_extractor.normalize(
                result.keywords
            )
            # 模型没有生成有效关键词时，降级使用 jieba。
            if not keywords:
                keywords = self._keyword_extractor.extract(
                    normalized_query
                )
            # 模型生成的关键词同义变体；为空时用本地词典兜底。
            synonym_keywords = self._keyword_extractor.normalize(
                result.synonym_keywords
            )
            if not synonym_keywords:
                synonym_keywords = (
                    self._keyword_extractor.expand_synonyms(
                        keywords
                    )
                )
            return RetrievalQuery(
                semantic_query=result.semantic_query.strip() or normalized_query,
                keywords=keywords,
                synonym_keywords=synonym_keywords,
                alternative_queries=result.alternative_queries)
        except Exception:
            # 模型调用失败时使用简单规则提取关键词。
            keywords = self._keyword_extractor.extract(
                normalized_query
            )
            return RetrievalQuery(
                semantic_query=normalized_query,
                keywords=keywords,
                synonym_keywords=(
                    self._keyword_extractor.expand_synonyms(
                        keywords
                    )
                ),
                alternative_queries=[],
            )
