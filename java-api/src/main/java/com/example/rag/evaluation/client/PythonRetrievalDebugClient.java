package com.example.rag.evaluation.client;

import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.RemoteException;
import com.example.rag.embedding.config.EmbeddingClientProperties;
import com.example.rag.evaluation.client.dto.PythonRetrievalDebugRequest;
import com.example.rag.evaluation.client.dto.PythonRetrievalDebugResponse;
import com.example.rag.evaluation.dto.RetrievalConfigResponse;
import com.example.rag.evaluation.dto.RetrievalDebugResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * PythonRetrievalDebugClient
 * 
 * @author gel
 * @date 2026/8/4
 * @description 
 */
@Slf4j
@Component
public class PythonRetrievalDebugClient {
    /** Python API 地址和超时配置。 */
    private final EmbeddingClientProperties properties;

    /** Java 对象和 JSON 之间的转换器。 */
    private final ObjectMapper objectMapper;

    /** 复用的 JDK HTTP 客户端。 */
    private final HttpClient httpClient;

    public PythonRetrievalDebugClient(
            EmbeddingClientProperties properties,
            ObjectMapper objectMapper
    ) {
        this.properties = properties;
        this.objectMapper = objectMapper;

        // HttpClient 应当复用，不能每个请求重新创建。
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(
                        Duration.ofSeconds(
                                properties.getTimeoutSeconds()
                        )
                )
                .build();
    }
    /**
     * 调用 Python 检索调试接口。
     *
     * @param requestBody 已补充租户、用户和 requestId 的内部请求
     * @return Python 返回的检索调试数据
     */
    public RetrievalDebugResponse debug(
            PythonRetrievalDebugRequest requestBody
    ){
        try {
            // 将 Java 内部请求序列化为 JSON
            String requestJson =
                    objectMapper.writeValueAsString(
                            requestBody
                    );
            // 拼接 Python 检索调试接口地址。
            String url =
                    properties.getPythonBaseUrl()
                            + "/api/retrieval/debug";
            // 检索过程可能包含 Rewrite、Embedding 和 Rerank，
            // 因此需要比普通数据库请求更长的读取超时。
            HttpRequest httpRequest =
                    HttpRequest.newBuilder()
                            .uri(URI.create(url))
                            .version(
                                    HttpClient.Version.HTTP_1_1
                            )
                            .timeout(
                                    Duration.ofSeconds(
                                            properties
                                                    .getTimeoutSeconds()
                                    )
                            )
                            .header(
                                    "Content-Type",
                                    "application/json"
                            )
                            .header(
                                    "Accept",
                                    "application/json"
                            )
                            .POST(
                                    HttpRequest.BodyPublishers
                                            .ofString(
                                                    requestJson,
                                                    StandardCharsets.UTF_8
                                            )
                            )
                            .build();
            // 阻塞等待 Python 完成检索调试。
            HttpResponse<String> httpResponse =
                    httpClient.send(
                            httpRequest,
                            HttpResponse.BodyHandlers
                                    .ofString(
                                            StandardCharsets.UTF_8
                                    )
                    );
            // 非 2xx 响应不能继续解析为正常业务结果。
            if (
                    httpResponse.statusCode() < 200
                            || httpResponse.statusCode() >= 300
            ) {
                log.error(
                        "调用 Python 检索调试接口失败, "
                                + "status={}, body={}",
                        httpResponse.statusCode(),
                        abbreviate(httpResponse.body())
                );

                throw new RemoteException(
                        BaseErrorCode.REMOTE_ERROR,
                        "Python 检索调试服务调用失败"
                );
            }

            // 解析 Python 的统一响应。
            PythonRetrievalDebugResponse response =
                    objectMapper.readValue(
                            httpResponse.body(),
                            PythonRetrievalDebugResponse.class
                    );

            // HTTP 成功不等于 Python 业务成功。
            if (
                    response == null
                            || !Boolean.TRUE.equals(
                            response.getSuccess()
                    )
                            || response.getData() == null
            ) {
                log.error(
                        "Python 检索调试服务返回业务失败, "
                                + "body={}",
                        abbreviate(httpResponse.body())
                );

                throw new RemoteException(
                        BaseErrorCode.REMOTE_ERROR,
                        response == null
                                ? "Python 检索调试服务响应为空"
                                : response.getMessage()
                );
            }

            return response.getData();

        } catch (RemoteException exception) {
            // 已经转换过的远程异常直接向上抛出。
            throw exception;
        } catch (InterruptedException  exception) {
            // 恢复线程中断标记，避免中断信号被吞掉。
            Thread.currentThread().interrupt();

            log.error(
                    "调用 Python 检索调试接口被中断",
                    exception
            );

            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python 检索调试服务调用被中断",
                    exception
            );
        } catch (Exception  exception) {
            log.error(
                    "调用 Python 检索调试接口异常",
                    exception
            );

            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python 检索调试服务调用异常",
                    exception
            );
        }

    }
    /**
     * 截断远程响应日志。
     *
     * <p>检索结果包含大量分片正文，不能完整写入日志。</p>
     */
    private String abbreviate(String value) {
        if (value == null) {
            return null;
        }

        int maxLength = 2000;

        return value.length() <= maxLength
                ? value
                : value.substring(0, maxLength)
                + "...[truncated]";
        }

    /**
     * 获取 Python 检索调试默认配置。
     *
     * @return 前端初始化表单用的检索参数
     */
    public RetrievalConfigResponse getConfig() {
        try {
            String url = properties.getPythonBaseUrl()
                    + "/api/retrieval/config";

            HttpRequest httpRequest = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(
                            properties.getTimeoutSeconds()
                    ))
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> httpResponse = httpClient.send(
                    httpRequest,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8
                    )
            );

            if (
                    httpResponse.statusCode() < 200
                            || httpResponse.statusCode() >= 300
            ) {
                log.error(
                        "调用 Python 检索配置接口失败, "
                                + "status={}, body={}",
                        httpResponse.statusCode(),
                        abbreviate(httpResponse.body())
                );

                throw new RemoteException(
                        BaseErrorCode.REMOTE_ERROR,
                        "Python 检索配置接口调用失败"
                );
            }

            JsonNode root = objectMapper.readTree(
                    httpResponse.body()
            );
            JsonNode data = root.path("data");

            if (data.isMissingNode() || data.isNull()) {
                throw new RemoteException(
                        BaseErrorCode.REMOTE_ERROR,
                        "Python 检索配置接口返回为空"
                );
            }

            return objectMapper.treeToValue(
                    data,
                    RetrievalConfigResponse.class
            );
        } catch (RemoteException exception) {
            throw exception;
        } catch (Exception exception) {
            log.error("调用 Python 检索配置接口异常", exception);
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python 检索配置接口调用异常",
                    exception
            );
        }
    }
}
