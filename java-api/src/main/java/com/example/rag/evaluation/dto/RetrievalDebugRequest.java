package com.example.rag.evaluation.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 前端提交的检索调试请求。
 *
 * <p>该对象不能包含 tenantId 和 userId，
 * 两个字段必须由 Java 从 JWT 中获取。</p>
 */
@Data
public class RetrievalDebugRequest {

    /** 需要检索的知识库 ID；不传则在当前租户全部知识库范围内检索。 */
    private Long knowledgeBaseId;

    /** 需要测试的用户问题。 */
    @NotBlank(message = "检索问题不能为空")
    @Size(max = 4000, message = "检索问题不能超过 4000 个字符")
    private String question;

    /** 检索模式，默认使用混合检索。 */
    @NotNull(message = "检索模式不能为空")
    private RetrievalMode mode = RetrievalMode.HYBRID;

    /** 是否调用模型改写检索问题。 */
    private Boolean enableRewrite = true;

    /** 是否执行 Rerank。 */
    private Boolean enableRerank = true;

    /** 向量检索召回数量。 */
    @Min(value = 1, message = "vectorTopK 不能小于 1")
    @Max(value = 100, message = "vectorTopK 不能大于 100")
    private Integer vectorTopK;

    /** 关键词检索召回数量。 */
    @Min(value = 1, message = "keywordTopK 不能小于 1")
    @Max(value = 100, message = "keywordTopK 不能大于 100")
    private Integer keywordTopK;

    /** RRF 融合后保留的候选数量。 */
    @Min(value = 1, message = "fusionTopK 不能小于 1")
    @Max(value = 100, message = "fusionTopK 不能大于 100")
    private Integer fusionTopK;

    /** 最终进入上下文打包的候选数量。 */
    @Min(value = 1, message = "finalTopK 不能小于 1")
    @Max(value = 50, message = "finalTopK 不能大于 50")
    private Integer finalTopK;

    /** RRF 排名平滑参数。 */
    @Min(value = 1, message = "rrfK 不能小于 1")
    @Max(value = 1000, message = "rrfK 不能大于 1000")
    private Integer rrfK;

    /** 向量召回结果在 Weighted RRF 中的权重；不传时使用 Python 默认配置。 */
    @DecimalMin(value = "0.0", message = "vectorWeight 不能小于 0")
    @DecimalMax(value = "10.0", message = "vectorWeight 不能大于 10")
    private Double vectorWeight;

    /** 关键词召回结果在 Weighted RRF 中的权重；不传时使用 Python 默认配置。 */
    @DecimalMin(value = "0.0", message = "keywordWeight 不能小于 0")
    @DecimalMax(value = "10.0", message = "keywordWeight 不能大于 10")
    private Double keywordWeight;
}
