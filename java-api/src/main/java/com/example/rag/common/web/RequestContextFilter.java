package com.example.rag.common.web;

import com.example.rag.common.context.LoginUser;
import com.example.rag.common.context.RequestContext;
import com.example.rag.common.context.UserContext;
import com.example.rag.trace.context.RagTraceContext;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * 请求上下文过滤器。
 *
 * <p>每个 HTTP 请求进入系统时，生成或透传 requestId，并从请求头读取临时用户信息。</p>
 */
@Component("ragRequestContextFilter")
@Slf4j
public class RequestContextFilter extends OncePerRequestFilter {

    /**
     * 请求链路 ID 请求头。调用方传入则透传，否则自动生成。
     */
    public static final String REQUEST_ID_HEADER = "X-Request-Id";

    /**
     * 初始化请求上下文，执行后续过滤器链，并在 finally 中清理 ThreadLocal。
     */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String requestId = firstNotBlank(request.getHeader(REQUEST_ID_HEADER), UUID.randomUUID().toString());
        try {
            RequestContext.setRequestId(requestId);
            RagTraceContext.setTraceId(requestId);
            // 使用 Spring Security 认证结果建立用户上下文。
            setupUserContextFromSecurity();
            response.setHeader(REQUEST_ID_HEADER, requestId);
            filterChain.doFilter(request, response);
        } catch (Exception ex) {
            log.error("Request filter failed, requestId={}", requestId, ex);
            throw ex;
        } finally {
            UserContext.clear();
            RequestContext.clear();
            RagTraceContext.clear();
        }
    }

    /**
     * 从请求头构建登录用户上下文；当前没有接认证系统，所以只做轻量模拟。
     */
    private void setupUserContextFromSecurity() {
        // 获取 Spring Security 当前认证对象。
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        /*
         * 登录接口、健康检查等公开接口可能没有 Authentication。
         */
        if (
                authentication == null
                        || !authentication.isAuthenticated()
        ) {
            return;
        }
        /*
         * Resource Server JWT 认证成功后，
         * principal 默认是 Jwt 对象。
         */
        if (!(authentication.getPrincipal() instanceof Jwt jwt)) {
            return;
        }
        // sub 对应用户 ID。
        String userId = jwt.getSubject();

        // 从自定义 Claims 中读取租户和用户信息。
        String tenantId =
                jwt.getClaimAsString("tenantId");

        String username =
                jwt.getClaimAsString("username");

        String role =
                jwt.getClaimAsString("role");
        // 建立项目已有的 LoginUser。
        UserContext.set(
                new LoginUser(
                        userId,
                        username,
                        tenantId,
                        role
                )
        );
    }

    /**
     * 返回第一个非空字符串，否则使用默认值。
     */
    private String firstNotBlank(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
}
