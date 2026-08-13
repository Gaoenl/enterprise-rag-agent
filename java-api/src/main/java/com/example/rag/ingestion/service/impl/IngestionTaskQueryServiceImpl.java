package com.example.rag.ingestion.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.rag.common.api.PageResult;
import com.example.rag.common.enums.IngestionTaskStatus;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.BusinessException;
import com.example.rag.common.error.DatabaseException;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.ingestion.dto.IngestionTaskConverter;
import com.example.rag.ingestion.dto.*;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.entity.IngestionTaskStep;
import com.example.rag.ingestion.mapper.IngestionTaskMapper;
import com.example.rag.ingestion.mapper.IngestionTaskStepMapper;
import com.example.rag.ingestion.service.IngestionTaskQueryService;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.knowledge.entity.KnowledgeBase;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.mapper.KnowledgeBaseMapper;
import com.example.rag.knowledge.mapper.KnowledgeDocumentMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * 入库任务查询服务实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class IngestionTaskQueryServiceImpl
        implements IngestionTaskQueryService {

    private static final String DOCUMENT_INGEST =
            "DOCUMENT_INGEST";
    /**
     * 当前项目的业务统计时区。
     */
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Shanghai");

    private final IngestionTaskMapper taskMapper;

    private final CurrentUserProvider currentUserProvider;
    /** 原有任务业务服务，用于任务查询和租户校验。 */
    private final IngestionTaskService taskService;

    /** 任务步骤 Mapper。 */
    private final IngestionTaskStepMapper stepMapper;

    /** 知识库历史引用查询 Mapper。 */
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    /** 文档历史引用查询 Mapper。 */
    private final KnowledgeDocumentMapper documentMapper;

    /** 任务响应转换器。 */
    private final IngestionTaskConverter taskConverter;

    @Override
    public PageResult<IngestionTaskListResponse> pageTasks(
            IngestionTaskQueryRequest request
    ) {
        // 校验请求对象。
        validateRequest(request);

        // 清理字符串首尾空白。
        normalizeRequest(request);

        // 校验状态和任务类型。
        validateStatus(request.getStatus());
        validateTaskType(request.getTaskType());
        validateTimeRange(request);

        // 租户 ID 只能从登录上下文获取。
        Long tenantId =
                currentUserProvider.requireTenantId();

        // 关键词是纯数字时，同时尝试匹配任务 ID。
        Long keywordTaskId =
                parseTaskId(request.getKeyword());

        Page<IngestionTaskListResponse> page =
                new Page<>(
                        request.normalizedPageNo(),
                        request.normalizedPageSize()
                );

        /*
         * 查询存在知识库、文档、LATERAL 等关联，
         * 关闭 MyBatis-Plus 的 JOIN 自动优化，避免 COUNT SQL 被错误裁剪。
         */
        page.setOptimizeCountSql(false);

        try {
            IPage<IngestionTaskListResponse> result =
                    taskMapper.selectTaskPage(
                            page,
                            tenantId,
                            request,
                            keywordTaskId
                    );

            return PageResult.from(result);
        } catch (DataAccessException exception) {
            log.error(
                    "分页查询入库任务数据库异常, tenantId={}, request={}",
                    tenantId,
                    request,
                    exception
            );

            throw new DatabaseException(
                    "分页查询入库任务失败",
                    exception
            );
        }
    }
    @Override
    public IngestionTaskDetailResponse getTaskDetail(
            Long taskId
    ) {
        // 查询任务，同时完成任务 ID 和租户权限校验。
        IngestionTask task =
                taskService.getTask(taskId);

        return buildTaskDetail(task);
    }

    @Override
    public List<IngestionTaskStepResponse> listTaskSteps(
            Long taskId
    ) {
        // 先校验任务存在并属于当前租户。
        taskService.getTask(taskId);

        try {
            // 按步骤创建顺序查询。
            List<IngestionTaskStep> steps =
                    selectTaskSteps(taskId);

            // 返回专用 Response，不再暴露数据库实体。
            return taskConverter.toStepResponses(steps);
        } catch (DataAccessException exception) {
            log.error(
                    "查询入库任务步骤数据库异常, taskId={}",
                    taskId,
                    exception
            );

            throw new DatabaseException(
                    "查询入库任务步骤失败",
                    exception
            );
        }
    }
    @Override
    public IngestionTaskDetailResponse
    getLatestTaskByDocumentId(Long documentId) {
        // 现有方法已经包含租户隔离和不存在校验。
        IngestionTask task =
                taskService.getLatestTaskByDocumentId(
                        documentId
                );

        // 复用详情组装逻辑，避免重复代码。
        return buildTaskDetail(task);
    }
    @Override
    public IngestionTaskStatisticsResponse statistics(
            IngestionTaskStatisticsQuery request
    ) {
        // Spring 未传参数时也保证请求对象可用。
        IngestionTaskStatisticsQuery actualRequest =
                request == null
                        ? new IngestionTaskStatisticsQuery()
                        : request;

        // 校验知识库 ID。
        validateStatisticsRequest(actualRequest);

        // 当前租户只能从登录上下文获取。
        Long tenantId =
                currentUserProvider.requireTenantId();

        /*
         * 将北京时间当天零点转换成 Instant，
         * 避免服务器部署在 UTC 时“今日”统计发生偏差。
         */
        Instant todayStart =
                LocalDate.now(BUSINESS_ZONE)
                        .atStartOfDay(BUSINESS_ZONE)
                        .toInstant();

        try {
            // 一条 SQL 完成所有统计。
            IngestionTaskStatisticsResponse response =
                    taskMapper.selectTaskStatistics(
                            tenantId,
                            actualRequest,
                            todayStart
                    );

            if (response == null) {
                return emptyStatistics();
            }

            // 成功率由 Java 计算，避免 SQL 中出现复杂除零逻辑。
            response.setSuccessRate(
                    calculateSuccessRate(
                            response.getSuccessCount(),
                            response.getFailedCount()
                    )
            );

            return response;
        } catch (DataAccessException exception) {
            log.error(
                    "统计入库任务数据库异常, tenantId={}, request={}",
                    tenantId,
                    actualRequest,
                    exception
            );

            throw new DatabaseException(
                    "统计入库任务失败",
                    exception
            );
        }
    }


    /**
     * 查询任务步骤实体。
     */
    private List<IngestionTaskStep> selectTaskSteps(
            Long taskId
    ) {
        return stepMapper.selectList(
                new LambdaQueryWrapper<IngestionTaskStep>()
                        .eq(
                                IngestionTaskStep::getTaskId,
                                taskId
                        )
                        .orderByAsc(
                                IngestionTaskStep::getId
                        )
        );
    }
    /**
     * 根据已经校验过的任务组装详情响应。
     */
    private IngestionTaskDetailResponse buildTaskDetail(
            IngestionTask task
    ) {
        try {
            // 查询知识库，包括已经软删除的知识库。
            KnowledgeBase knowledgeBase =
                    knowledgeBaseMapper.selectTaskReference(
                            task.getKnowledgeBaseId(),
                            task.getTenantId()
                    );

            // 查询文档，包括已经软删除的文档。
            KnowledgeDocument document =
                    documentMapper.selectTaskReference(
                            task.getDocumentId(),
                            task.getTenantId()
                    );

            // 查询任务的全部处理步骤。
            List<IngestionTaskStep> steps =
                    selectTaskSteps(task.getId());

            // 统一转换成接口详情响应。
            return taskConverter.toDetailResponse(
                    task,
                    knowledgeBase,
                    document,
                    steps
            );
        } catch (DataAccessException exception) {
            log.error(
                    "查询入库任务详情数据库异常, taskId={}, tenantId={}",
                    task.getId(),
                    task.getTenantId(),
                    exception
            );

            throw new DatabaseException(
                    "查询入库任务详情失败",
                    exception
            );
        }
    }

    /**
     * 校验查询请求。
     */
    private void validateRequest(
            IngestionTaskQueryRequest request
    ) {
        if (request == null) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "任务查询参数不能为空"
            );
        }

        validatePositiveId(
                request.getKnowledgeBaseId(),
                "知识库 ID 必须大于 0"
        );

        validatePositiveId(
                request.getDocumentId(),
                "文档 ID 必须大于 0"
        );

        validatePositiveId(
                request.getCreatedBy(),
                "创建人 ID 必须大于 0"
        );
    }

    /**
     * 校验可选 ID。
     */
    private void validatePositiveId(
            Long id,
            String message
    ) {
        if (id != null && id <= 0) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    message
            );
        }
    }

    /**
     * 标准化查询字符串。
     */
    private void normalizeRequest(
            IngestionTaskQueryRequest request
    ) {
        request.setKeyword(trimToNull(
                request.getKeyword()
        ));

        request.setStatus(upperToNull(
                request.getStatus()
        ));

        request.setTaskType(upperToNull(
                request.getTaskType()
        ));
    }

    /**
     * 校验任务状态。
     */
    private void validateStatus(String status) {
        if (status == null) {
            return;
        }

        boolean supported =
                Arrays.stream(
                                IngestionTaskStatus.values()
                        )
                        .anyMatch(value ->
                                value.getCode().equals(status)
                        );

        if (!supported) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "不支持的任务状态：" + status
            );
        }
    }

    /**
     * 校验任务类型。
     */
    private void validateTaskType(String taskType) {
        if (taskType == null) {
            return;
        }

        if (!DOCUMENT_INGEST.equals(taskType)) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "不支持的任务类型：" + taskType
            );
        }
    }

    /**
     * 校验时间范围。
     */
    private void validateTimeRange(
            IngestionTaskQueryRequest request
    ) {
        if (request.getCreatedAtStart() == null
                || request.getCreatedAtEnd() == null) {
            return;
        }

        if (request.getCreatedAtStart()
                .isAfter(request.getCreatedAtEnd())) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "开始时间不能晚于结束时间"
            );
        }
    }
    /**
     * 校验任务统计请求。
     */
    private void validateStatisticsRequest(
            IngestionTaskStatisticsQuery request
    ) {
        if (request.getKnowledgeBaseId() != null
                && request.getKnowledgeBaseId() <= 0) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "知识库 ID 必须大于 0"
            );
        }

        if (request.getCreatedAtStart() != null
                && request.getCreatedAtEnd() != null
                && request.getCreatedAtStart()
                .isAfter(request.getCreatedAtEnd())) {
            throw new BusinessException(
                    BaseErrorCode.BAD_REQUEST,
                    "开始时间不能晚于结束时间"
            );
        }
    }

    /**
     * 计算成功率，保留两位小数。
     */
    private Double calculateSuccessRate(
            Long successCount,
            Long failedCount
    ) {
        long success =
                successCount == null ? 0 : successCount;

        long failed =
                failedCount == null ? 0 : failedCount;

        long finishedCount = success + failed;

        if (finishedCount == 0) {
            return 0D;
        }

        double rate =
                success * 100D / finishedCount;

        return Math.round(rate * 100D) / 100D;
    }

    /**
     * 返回空统计结果。
     */
    private IngestionTaskStatisticsResponse emptyStatistics() {
        return IngestionTaskStatisticsResponse.builder()
                .totalCount(0L)
                .pendingCount(0L)
                .runningCount(0L)
                .successCount(0L)
                .failedCount(0L)
                .successRate(0D)
                .averageDurationMillis(0L)
                .todayCreatedCount(0L)
                .todaySuccessCount(0L)
                .todayFailedCount(0L)
                .build();
    }

    /**
     * 尝试将关键词转换为任务 ID。
     */
    private Long parseTaskId(String keyword) {
        if (keyword == null) {
            return null;
        }

        try {
            long value = Long.parseLong(keyword);
            return value > 0 ? value : null;
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private String trimToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }

        return value.trim();
    }

    private String upperToNull(String value) {
        String normalized = trimToNull(value);

        return normalized == null
                ? null
                : normalized.toUpperCase(Locale.ROOT);
    }
}