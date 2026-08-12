package com.example.rag.chat.client;

import com.example.rag.chat.entity.ChatMessage;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.RemoteException;
import com.example.rag.embedding.config.EmbeddingClientProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * PythonConversationClient
 * 
 * @author gel
 * @date 2026/8/12
 * @description 
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class PythonConversationClient {
    private final EmbeddingClientProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    public String summarize(List<ChatMessage> messages, String oldSummary) throws Exception {
        List<Map<String, String>> payloadMessages = messages.stream()
                .map(message -> Map.of(
                        "role", String.valueOf(message.getRole()),
                        "content", message.getContent() == null ? "" : message.getContent()))
                .toList();
        Map<String, Object> body = Map.of(
                "messages", payloadMessages,
                "old_summary", oldSummary == null ? "" : oldSummary);
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(properties.getPythonBaseUrl() + "/api/conversations/summarize"))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        objectMapper.writeValueAsString(body), StandardCharsets.UTF_8))
                .build();
        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteException(BaseErrorCode.REMOTE_ERROR, "会话摘要接口调用失败");
        }
        JsonNode root = objectMapper.readTree(response.body());
        return root.path("data").path("summary").asText("");

    }
}