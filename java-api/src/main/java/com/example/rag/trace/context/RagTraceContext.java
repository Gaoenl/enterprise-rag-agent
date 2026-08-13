package com.example.rag.trace.context;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * RAG 链路追踪上下文。
 *
 * <p>保存一次 RAG 执行中的 traceId、taskId 和节点栈，后续可被 AOP 或业务编排代码使用。</p>
 */
public final class RagTraceContext {

    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> TASK_ID = new ThreadLocal<>();
    private static final ThreadLocal<Deque<String>> NODE_STACK = new ThreadLocal<>();

    private RagTraceContext() {
    }

    /**
     * 读取当前链路 ID。
     */
    public static String traceId() {
        return TRACE_ID.get();
    }

    /**
     * 设置当前链路 ID。
     */
    public static void setTraceId(String traceId) {
        TRACE_ID.set(traceId);
    }

    /**
     * 读取当前任务 ID，通常对应一次异步入库或问答任务。
     */
    public static String taskId() {
        return TASK_ID.get();
    }

    /**
     * 设置当前任务 ID。
     */
    public static void setTaskId(String taskId) {
        TASK_ID.set(taskId);
    }

    /**
     * 返回当前节点栈深度。
     */
    public static int depth() {
        Deque<String> stack = NODE_STACK.get();
        return stack == null ? 0 : stack.size();
    }

    /**
     * 返回当前正在执行的节点 ID。
     */
    public static String currentNodeId() {
        Deque<String> stack = NODE_STACK.get();
        return stack == null ? null : stack.peek();
    }

    /**
     * 节点开始执行时入栈。
     */
    public static void pushNode(String nodeId) {
        Deque<String> stack = NODE_STACK.get();
        if (stack == null) {
            stack = new ArrayDeque<>();
            NODE_STACK.set(stack);
        }
        stack.push(nodeId);
    }

    /**
     * 节点执行结束时出栈。
     */
    public static void popNode() {
        Deque<String> stack = NODE_STACK.get();
        if (stack == null || stack.isEmpty()) {
            return;
        }
        stack.pop();
        if (stack.isEmpty()) {
            NODE_STACK.remove();
        }
    }

    /**
     * 清理当前线程的 RAG 链路上下文。
     */
    public static void clear() {
        TRACE_ID.remove();
        TASK_ID.remove();
        NODE_STACK.remove();
    }
}
