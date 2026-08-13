package com.example.rag.trace.context;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * RAG 节点标记注解。
 *
 * <p>后续可以配合 AOP 使用，自动记录检索、重排、生成、工具调用等节点耗时。</p>
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RagTraceNode {

    /**
     * 节点名称；为空时可使用方法名。
     */
    String name() default "";

    /**
     * 节点类型，例如 RETRIEVE、RERANK、GENERATE、TOOL。
     */
    String type() default "METHOD";
}
