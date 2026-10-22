package org.dromara.web.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 容器健康检查端点。
 *
 * <p>只返回固定字符串，不暴露组件状态、版本或依赖信息；由 compose healthcheck 调用。
 * 该路径已在 {@code security.excludes} 中放行，不经过 Sa-Token 鉴权。</p>
 */
@RestController
public class HealthController {

    /**
     * 轻量存活探针。
     *
     * @return 固定 "ok"
     */
    @GetMapping("/healthz")
    public String healthz() {
        return "ok";
    }
}
