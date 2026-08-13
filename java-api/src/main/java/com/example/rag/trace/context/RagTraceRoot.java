package com.example.rag.trace.context;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 一次 RAG 链路追踪的根对象。
 *
 * <p>当前先用轻量对象保存 traceId、taskId、开始时间和节点列表，后续可映射到 `rag_trace` 表。</p>
 */
public class RagTraceRoot {

    private final String traceId;
    private final String taskId;
    private final Instant startTime;
    private final List<String> nodes = new ArrayList<>();

    /**
     * 创建一次链路追踪根对象。
     */
    public RagTraceRoot(String traceId, String taskId) {
        this.traceId = traceId;
        this.taskId = taskId;
        this.startTime = Instant.now();
    }

    /**
     * 返回链路 ID。执行
     */
    public String getTraceId() {
        return traceId;
    }

    /**
     * 返回任务 ID。
     */
    public String getTaskId() {
        return taskId;
    }

    /**
     * 返回链路开始时间。
     */
    public Instant getStartTime() {
        return startTime;
    }

    /**
     * 返回已记录的节点列表。
     */
    public List<String> getNodes() {
        return nodes;
    }

    /**
     * 追加一个节点记录。
     */
    public void addNode(String node) {
        nodes.add(node);
    }
}
