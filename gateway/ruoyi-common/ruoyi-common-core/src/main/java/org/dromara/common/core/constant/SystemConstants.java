package org.dromara.common.core.constant;

/**
 * 系统常量信息
 *
 * @author Lion Li
 */
public interface SystemConstants {

    /**
     * 正常状态
     */
    String NORMAL = "0";

    /**
     * 异常状态
     */
    String DISABLE = "1";

    /**
     * 是
     */
    String YES = "Y";

    /**
     * 否
     */
    String NO = "N";

    /**
     * 菜单类型（目录）
     */
    String TYPE_DIR = "M";

    /**
     * 菜单类型（菜单）
     */
    String TYPE_MENU = "C";

    /**
     * 菜单类型（按钮）
     */
    String TYPE_BUTTON = "F";

    /**
     * Layout组件标识
     */
    String LAYOUT = "Layout";

    /**
     * ParentView组件标识
     */
    String PARENT_VIEW = "ParentView";

    /**
     * InnerLink组件标识
     */
    String INNER_LINK = "InnerLink";

    /**
     * 超级管理员用户ID
     */
    Long SUPER_ADMIN_USER_ID = 1761100000000000001L;

    /**
     * 超级管理员角色ID
     */
    Long SUPER_ADMIN_ROLE_ID = 1761300000000000001L;

    /**
     * 超级管理员角色 roleKey
     */
    String SUPER_ADMIN_ROLE_KEY = "superadmin";

    /**
     * 根部门祖级列表
     */
    String ROOT_DEPT_ANCESTORS = "0";

    /**
     * 默认部门 ID
     */
    Long DEFAULT_DEPT_ID = 1761000000000000100L;

    /**
     * 排除敏感属性字段（请求参数日志、操作日志与脱敏输出共用）。
     *
     * <p>匹配规则为 JSON 属性名精确匹配（区分大小写），调用方应使用常见的小驼峰写法。
     * 在原有口令字段基础上补充令牌、凭据与密钥类字段，避免登录/刷新令牌、
     * 内部签名凭据或第三方密钥被写入运行日志和操作日志。</p>
     */
    String[] EXCLUDE_PROPERTIES = {
        "password", "oldPassword", "newPassword", "confirmPassword",
        "token", "accessToken", "refreshToken", "authorization",
        "secret", "clientSecret", "apiKey", "apiSecret"
    };


}
