package com.example.rag.evaluation.client.dto;

import com.example.rag.evaluation.dto.RetrievalDebugResponse;
import lombok.Data;

/**
 * Python 检索调试接口的统一响应。
 */
@Data
public class PythonRetrievalDebugResponse {

    /** Python 业务是否执行成功。 */
    private Boolean success;

    /** Python 业务响应码。 */
    private String code;

    /** Python 响应消息。 */
    private String message;

    /** 检索调试数据。 */
    private RetrievalDebugResponse data;
}