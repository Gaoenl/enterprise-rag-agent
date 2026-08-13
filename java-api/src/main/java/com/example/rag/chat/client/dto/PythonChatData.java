package com.example.rag.chat.client.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * Python Chat API 返回的数据。
 */
@Data
public class PythonChatData {

    /**
     * 用户输入的原始问题。
     */
    private String question;

    /**
     * 结合历史改写后的独立问题。
     */
    private String standaloneQuery;

    /**
     * 模型最终回答。
     */
    private String answer;

    /**
     * 实际使用的模型。
     */
    private String model;

    /**
     * 回答模式：basic、rag 或 clarify。
     */
    private String mode;

    /**
     * 路由识别出的意图。
     */
    private String intent;

    /**
     * 本次请求是否进入 RAG 流程。
     */
    private Boolean needRag;

    /**
     * 本次实际检索的知识库 ID。
     */
    private Long knowledgeBaseId;

    /**
     * 路由或知识库选择原因。
     */
    private String routeReason;
    /**
     * 本次 RAG Trace ID。
     */
    private Long traceId;

    /**
     * 回答状态：GENERAL、ANSWERED、NO_EVIDENCE 等。
     */
    private String answerStatus;

    /**
     * 回答实际使用的引用编号。
     */
    private List<Integer> usedCitationIndexes;

    /**
     * 模型生成但不存在的引用编号。
     */
    private List<Integer> invalidCitationIndexes;

    /**
     * 本次 LLM Token 用量。
     */
    private PythonTokenUsage tokenUsage;

    /**
     * Python 返回的完整 Trace。
     */
    private PythonRagTraceData trace;
    /**
     * 本次回答引用的文档分片。
     */
    private List<Map<String, Object>> citations;

    /** 本轮完整路由决策，Java 持久化到会话表供下轮继承。 */
    private Map<String, Object> route;

}
