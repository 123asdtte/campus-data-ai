package org.dromara.common.json.utils;

import cn.hutool.core.util.ArrayUtil;
import org.dromara.common.core.utils.StringUtils;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * JSON 字段清理工具。
 *
 * <p>与 {@link JsonUtils} 不同，本类不依赖 Spring 容器，可直接在单元测试中调用。
 * 供请求参数日志、操作日志等脱敏场景共用。</p>
 */
public final class JsonFieldRemover {

    /**
     * 工具类禁止实例化。
     */
    private JsonFieldRemover() {
    }

    /**
     * 从 JSON 树中递归移除指定字段。
     *
     * <p>对象节点按字段名精确匹配删除；数组节点会继续遍历其子节点，
     * 因此嵌套对象与对象数组中的同名敏感字段都会被清理。</p>
     *
     * @param node       JSON 节点（可为对象、数组或标量）
     * @param fieldNames 需要移除的字段名，空值会被忽略
     * @return 原 JSON 节点，便于链式调用
     */
    public static JsonNode removeFields(JsonNode node, String... fieldNames) {
        if (node == null || ArrayUtil.isEmpty(fieldNames)) {
            return node;
        }
        if (node.isObject()) {
            ObjectNode objectNode = (ObjectNode) node;
            for (String fieldName : fieldNames) {
                if (StringUtils.isNotBlank(fieldName)) {
                    objectNode.remove(fieldName);
                }
            }
        }
        // 递归处理子节点：覆盖嵌套对象与数组元素
        for (JsonNode child : node) {
            removeFields(child, fieldNames);
        }
        return node;
    }
}
