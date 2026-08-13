package com.example.rag.chat.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.example.rag.common.config.database.JsonbTypeHandler;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@TableName(value = "chat_conversation", autoResultMap = true)
public class ChatConversation {

    @TableId
    private Long id;

    private Long tenantId;

    private Long userId;

    private Long knowledgeBaseId;

    private String title;

    private String channel;
    /** 会话摘要（压缩后）。 */
    private String summary;

    /** 上次压缩到的消息 ID（用于触发边界与并发乐观锁）。 */
    private Long lastSummaryMessageId;

    /** 上一轮意图路由决策（JSONB），供多轮追问继承。 */
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String lastRoute;

    @TableField(typeHandler = JsonbTypeHandler.class)
    private String metadata;

    @TableField(fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;

    @TableField(value = "deleted", fill = FieldFill.INSERT)
    @TableLogic(value = "false", delval = "true")
    private Boolean deleted;
}
