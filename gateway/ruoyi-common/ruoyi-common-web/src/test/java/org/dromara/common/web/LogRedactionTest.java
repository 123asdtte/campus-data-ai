package org.dromara.common.web;

import org.dromara.common.core.constant.SystemConstants;
import org.dromara.common.json.utils.JsonFieldRemover;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 请求参数日志脱敏回归测试。
 *
 * <p>背景：网关的 {@code PlusWebInvokeTimeInterceptor} 与操作日志切面共用
 * {@link SystemConstants#EXCLUDE_PROPERTIES} 作为敏感字段名单。只要有人在重构中
 * 移除名单项，令牌或密钥就会重新出现在日志里，因此用单元测试把“必须排除哪些字段”
 * 以及“嵌套结构也能被清理”固定下来。</p>
 */
@Tag("dev")
@DisplayName("请求参数日志敏感字段脱敏")
class LogRedactionTest {

    /**
     * 必须被排除的字段名。
     *
     * <p>与 {@code SystemConstants.EXCLUDE_PROPERTIES} 保持一致；新增敏感字段时，
     * 应同时补充本清单，避免测试与实际名单脱节。</p>
     */
    private static final Set<String> REQUIRED_EXCLUDES = Set.of(
        "password", "oldPassword", "newPassword", "confirmPassword",
        "token", "accessToken", "refreshToken", "authorization",
        "secret", "clientSecret", "apiKey", "apiSecret"
    );

    /**
     * 验证敏感字段名单包含全部必需项。
     *
     * <p>失败意味着日志脱敏名单被删减，属于安全回归。</p>
     */
    @Test
    @DisplayName("敏感字段名单覆盖口令、令牌与密钥")
    void excludePropertiesCoverSensitiveNames() {
        List<String> configured = List.of(SystemConstants.EXCLUDE_PROPERTIES);
        for (String required : REQUIRED_EXCLUDES) {
            assertTrue(configured.contains(required), "缺少敏感字段排除项: " + required);
        }
    }

    /**
     * 验证嵌套对象与数组中的敏感字段都会被递归清理。
     *
     * <p>真实登录请求可能是 {@code {"user":{"password":"..."},"token":"..."}}，
     * 或包含对象数组；仅清理顶层字段不足以防止泄露。</p>
     */
    @Test
    @DisplayName("嵌套结构与数组中的敏感字段被递归清理")
    void removeFieldsStripsNestedSensitiveFields() {
        String raw = """
            {
              "username": "demo",
              "password": "top-secret-password",
              "token": "top-secret-token",
              "nested": {
                "accessToken": "nested-access-token",
                "apiKey": "nested-api-key",
                "keep": "visible-value"
              },
              "items": [
                {"authorization": "nested-authorization", "name": "first"},
                {"refreshToken": "nested-refresh-token", "name": "second"}
              ]
            }
            """;

        // 单元测试不启动 Spring 容器，直接构造 JsonMapper；被测逻辑本身不依赖容器
        JsonMapper jsonMapper = JsonMapper.builder().build();
        JsonNode root = jsonMapper.readTree(raw);
        JsonFieldRemover.removeFields(root, SystemConstants.EXCLUDE_PROPERTIES);
        String sanitized = root.toString();

        // 敏感值必须全部消失
        for (String secret : List.of(
            "top-secret-password", "top-secret-token", "nested-access-token",
            "nested-api-key", "nested-authorization", "nested-refresh-token")) {
            assertFalse(sanitized.contains(secret), "日志仍包含敏感值: " + secret);
        }

        // 非敏感字段必须保留，避免脱敏误删业务信息
        assertTrue(sanitized.contains("\"username\":\"demo\""), "普通字段 username 被误删");
        assertTrue(sanitized.contains("\"keep\":\"visible-value\""), "普通字段 keep 被误删");
        assertEquals(2, root.get("items").size(), "数组元素不应被移除");
    }
}
