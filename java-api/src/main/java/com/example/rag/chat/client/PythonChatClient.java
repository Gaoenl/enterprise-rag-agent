package com.example.rag.chat.client;

import com.example.rag.chat.client.dto.PythonChatData;
import com.example.rag.chat.client.dto.PythonChatRequest;
import com.example.rag.chat.client.dto.PythonChatResponse;
import com.example.rag.chat.client.sse.PythonChatStreamSession;
import com.example.rag.chat.client.sse.PythonSseEvent;
import com.example.rag.chat.client.sse.PythonSseEventParser;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.RemoteException;
import com.example.rag.embedding.config.EmbeddingClientProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.function.Consumer;

/**
 * PythonChatClient
 * Python Chat 服务客户端。
 * @author gel
 * @date 2026/7/27
 * @description 
 */
@Slf4j
@Component
public class PythonChatClient {
    private final EmbeddingClientProperties properties;
    private final ObjectMapper objectMapper;
    private final PythonSseEventParser sseEventParser;
    private final HttpClient httpClient;

    public PythonChatClient(EmbeddingClientProperties properties, ObjectMapper objectMapper,
                            PythonSseEventParser sseEventParser) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.sseEventParser = sseEventParser;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(properties.getTimeoutSeconds()))
                .build();
    }

    public PythonChatData chat(PythonChatRequest requestBody) {
        try{
            String json=objectMapper.writeValueAsString(requestBody);
            String url = properties.getPythonBaseUrl() + "/api/chat/completions";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(properties.getTimeoutSeconds()))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString()); if (response.statusCode() < 200 || response.statusCode() >= 300) {
                log.error("调用 Python Chat 服务失败, status={}, body={}", response.statusCode(), response.body());
                throw new RemoteException(BaseErrorCode.REMOTE_ERROR, "调用 Python Chat 服务失败");
            }
            PythonChatResponse chatResponse= objectMapper.readValue(response.body(), PythonChatResponse.class);
            if (!Boolean.TRUE.equals(chatResponse.getSuccess())) {
                log.error("Python Chat 服务返回失败, response={}", response.body());
                throw new RemoteException(BaseErrorCode.REMOTE_ERROR, "Python Chat 服务返回失败");

            }
            return chatResponse.getData();

        } catch (RemoteException ex) {
            throw ex;
        } catch (Exception ex) {
            log.error("调用 Python Chat 服务异常", ex);
            throw new RemoteException(BaseErrorCode.REMOTE_ERROR, "调用 Python Chat 服务异常", ex);
        }
    }
    /**
     * 调用 Python 流式聊天接口。
     *
     * <p>该方法是阻塞方法，会一直读取到 Python 响应流结束。
     * 后续 ChatService 应在线程池中调用，不能直接占用
     * Spring MVC 请求线程。</p>
     *
     * @param requestBody Python Chat 请求
     * @param eventConsumer SSE 事件消费者
     */
    public void streamChat(
            PythonChatRequest requestBody,
            Consumer<PythonSseEvent> eventConsumer,
            PythonChatStreamSession streamSession
    ) {
        try {
            // 将 Python 请求对象序列化成 JSON。
            String json = objectMapper.writeValueAsString(
                    requestBody
            );

            // 构建 Python 流式聊天接口地址。
            String url = properties.getPythonBaseUrl()
                    + "/api/chat/stream";

            // 构建 HTTP POST 请求。
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .version(HttpClient.Version.HTTP_1_1)

                    // SSE 连接不能使用普通短请求超时时间。
                    // 此处设置为模型允许的最大生成时间。
                    .timeout(
                            Duration.ofMinutes(5)
                    )

                    .header(
                            "Content-Type",
                            "application/json"
                    )
                    .header(
                            "Accept",
                            "text/event-stream"
                    )
                    .header(
                            "Cache-Control",
                            "no-cache"
                    )
                    .POST(
                            HttpRequest.BodyPublishers.ofString(
                                    json,
                                    StandardCharsets.UTF_8
                            )
                    )
                    .build();
            HttpResponse<InputStream> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream()
            );
            // 非 2xx 响应不能进入 SSE 解析流程。
            if (
                    response.statusCode() < 200
                            || response.statusCode() >= 300
            ) {
                String responseBody;

                try (InputStream body = response.body()) {
                    responseBody = new String(
                            body.readAllBytes(),
                            StandardCharsets.UTF_8
                    );
                }

                log.error(
                        "调用 Python 流式 Chat 服务失败, "
                                + "status={}, body={}",
                        response.statusCode(),
                        responseBody
                );

                throw new RemoteException(
                        BaseErrorCode.REMOTE_ERROR,
                        "调用 Python 流式 Chat 服务失败"
                );
            }
            // 取得 Python 响应流。
            InputStream responseStream = response.body();
            // 将响应流绑定到可取消会话。
            streamSession.bind(responseStream);
            // 如果绑定时已经取消，则立即结束。
            if (streamSession.isCancelled()) {
                return;
            }

            try {
                // 持续解析 Python SSE。
                sseEventParser.parse(
                        responseStream,
                        event -> {
                            // Java SSE 关闭后不再处理 Python 事件。
                            if (streamSession.isCancelled()) {
                                return;
                            }

                            eventConsumer.accept(event);
                        }
                );
            } finally {
                // 无论正常结束还是异常，都关闭下游流。
                streamSession.close();
            }

        } catch (RemoteException exception) {
            throw exception;
        } catch (InterruptedException exception) {
            // 恢复线程中断状态，不能直接吞掉中断信号。
            Thread.currentThread().interrupt();

            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "调用 Python 流式 Chat 服务被中断",
                    exception
            );
        } catch (Exception exception) {
            log.error(
                    "调用 Python 流式 Chat 服务异常",
                    exception
            );

            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "调用 Python 流式 Chat 服务异常",
                    exception
            );
        }
    }


}
