package org.dromara.web.controller.internal;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.hutool.core.util.IdUtil;
import lombok.extern.slf4j.Slf4j;
import org.dromara.common.satoken.utils.LoginHelper;
import org.dromara.system.api.model.LoginUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriComponentsBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * 内部网关（PR-B 最小切片）：把已登录的 RuoYi 会话转换为内部签名请求。
 *
 * <p>canonical 共 14 段（与 import-api/app/internal_auth.py 逐字节一致）：
 * METHOD \n PATH \n QUERY \n TS \n NONCE \n PAYLOAD_SHA \n META \n
 * USER \n ROLE \n COLLEGE \n COLLEGES \n DEPT \n ADMIN \n PERMS
 *
 * <ul>
 *   <li>QUERY：键排序、percent-encoding 后的查询串（空串表示无参数）</li>
 *   <li>PAYLOAD_SHA：JSON 为 body 摘要；multipart 为文件内容摘要（PR-D 使用）</li>
 *   <li>META：multipart 中除 file 外的表单字段（PR-D 使用）；JSON 为空</li>
 *   <li>PERMS：字典序排序后空格连接</li>
 * </ul>
 *
 * <p>本阶段只接入学生域 3 个端点：列表、详情、更新。导入域在 PR-D 接入。
 */
@Slf4j
@RestController
@RequestMapping("/internal/proxy")
public class InternalProxyController {

    private static final String HMAC_ALGO = "HmacSHA256";
    private static final String SUPER_ADMIN_ROLE = "superadmin";
    private static final String UNRESERVED =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";

    /** 与 import-api 共享的 HMAC 密钥，仅存在于服务端环境变量。 */
    @Value("${internal.hmac-secret:}")
    private String hmacSecret;

    /** FastAPI 业务服务地址；容器内按服务名访问，不经过宿主 8010。 */
    @Value("${internal.importapi-base:http://import-api:8000}")
    private String importApiBase;

    // ------------------------------------------------------------------ 学生域

    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/students")
    public ResponseEntity<String> listStudents(@RequestParam(required = false) String keyword,
                                               @RequestParam(required = false) String college,
                                               @RequestParam(required = false) String class_name,
                                               @RequestParam(required = false) String status,
                                               @RequestParam(required = false) Boolean include_inactive,
                                               @RequestParam(required = false) Integer page,
                                               @RequestParam(required = false) Integer page_size) {
        Map<String, String> query = new LinkedHashMap<>();
        if (keyword != null && !keyword.isBlank()) {
            query.put("keyword", keyword);
        }
        if (college != null && !college.isBlank()) {
            query.put("college", college);
        }
        if (class_name != null && !class_name.isBlank()) {
            query.put("class_name", class_name);
        }
        if (status != null && !status.isBlank()) {
            query.put("status", status);
        }
        if (include_inactive != null) {
            query.put("include_inactive", String.valueOf(include_inactive));
        }
        if (page != null) {
            query.put("page", String.valueOf(page));
        }
        if (page_size != null) {
            query.put("page_size", String.valueOf(page_size));
        }
        return call(HttpMethod.GET, "/students", query, new byte[0]);
    }

    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/students/{studentNo}")
    public ResponseEntity<String> getStudent(@PathVariable("studentNo") String studentNo) {
        return call(HttpMethod.GET, "/students/" + studentNo, Map.of(), new byte[0]);
    }

    @SaCheckPermission(value = "student:write", orRole = SUPER_ADMIN_ROLE)
    @PutMapping("/students/{studentNo}")
    public ResponseEntity<String> updateStudent(@PathVariable("studentNo") String studentNo,
                                                @RequestBody Map<String, Object> payload) {
        byte[] body = Json.write(payload);
        return call(HttpMethod.PUT, "/students/" + studentNo, Map.of(), body);
    }

    /**
     * 按需字段导出 Excel（二进制透传，保留上游 Content-Type 与 Content-Disposition）。
     * Spring 精确匹配优先于 /students/{studentNo}，不会被参数路由抢占。
     */
    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/students/export")
    public ResponseEntity<byte[]> exportStudents(@RequestParam(required = false) String fields,
                                                 @RequestParam(required = false) String keyword,
                                                 @RequestParam(required = false) String college,
                                                 @RequestParam(required = false) String class_name,
                                                 @RequestParam(required = false) String status,
                                                 @RequestParam(required = false) Boolean include_inactive,
                                                 @RequestParam(required = false) Boolean split_by_college) {
        Map<String, String> query = new LinkedHashMap<>();
        if (fields != null && !fields.isBlank()) {
            query.put("fields", fields);
        }
        if (keyword != null && !keyword.isBlank()) {
            query.put("keyword", keyword);
        }
        if (college != null && !college.isBlank()) {
            query.put("college", college);
        }
        if (class_name != null && !class_name.isBlank()) {
            query.put("class_name", class_name);
        }
        if (status != null && !status.isBlank()) {
            query.put("status", status);
        }
        if (include_inactive != null) {
            query.put("include_inactive", String.valueOf(include_inactive));
        }
        if (split_by_college != null) {
            query.put("split_by_college", String.valueOf(split_by_college));
        }
        return callBinary(HttpMethod.GET, "/students/export", query, new byte[0]);
    }

    /** 单个学生的字段级编辑审计（operation_logs）。 */
    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/students/{studentNo}/audit")
    public ResponseEntity<String> getStudentAudit(@PathVariable("studentNo") String studentNo,
                                                  @RequestParam(required = false) Integer limit) {
        Map<String, String> query = new LinkedHashMap<>();
        if (limit != null) {
            query.put("limit", String.valueOf(limit));
        }
        return call(HttpMethod.GET, "/students/" + studentNo + "/audit", query, new byte[0]);
    }

    // ------------------------------------------------------------------ 聚合（PR-D）

    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/meta/filters")
    public ResponseEntity<String> getFilters() {
        return call(HttpMethod.GET, "/meta/filters", Map.of(), new byte[0]);
    }

    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/stats/overview")
    public ResponseEntity<String> getOverview() {
        return call(HttpMethod.GET, "/stats/overview", Map.of(), new byte[0]);
    }

    /** 数据质量看板：完整率/缺失/重名/各学院明细。 */
    @SaCheckPermission(value = "student:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/meta/data-quality")
    public ResponseEntity<String> getDataQuality() {
        return call(HttpMethod.GET, "/meta/data-quality", Map.of(), new byte[0]);
    }

    // ------------------------------------------------------------------ 操作审计（管理员视角）

    /** 全局字段级编辑留痕，支持关键词/操作人/动作/时间区间筛选。 */
    @SaCheckPermission(value = "monitor:operlog:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/audit-logs")
    public ResponseEntity<String> listAuditLogs(@RequestParam(required = false) String keyword,
                                                @RequestParam(required = false) String actor,
                                                @RequestParam(required = false) String action,
                                                @RequestParam(required = false) String from_date,
                                                @RequestParam(required = false) String until_date,
                                                @RequestParam(required = false) Integer page,
                                                @RequestParam(required = false) Integer page_size) {
        Map<String, String> query = new LinkedHashMap<>();
        if (keyword != null && !keyword.isBlank()) {
            query.put("keyword", keyword);
        }
        if (actor != null && !actor.isBlank()) {
            query.put("actor", actor);
        }
        if (action != null && !action.isBlank()) {
            query.put("action", action);
        }
        if (from_date != null && !from_date.isBlank()) {
            query.put("from_date", from_date);
        }
        if (until_date != null && !until_date.isBlank()) {
            query.put("until_date", until_date);
        }
        if (page != null) {
            query.put("page", String.valueOf(page));
        }
        if (page_size != null) {
            query.put("page_size", String.valueOf(page_size));
        }
        return call(HttpMethod.GET, "/audit-logs", query, new byte[0]);
    }

    /** 操作人维度统计：各操作人的增/改/删次数（与列表共用筛选条件）。 */
    @SaCheckPermission(value = "monitor:operlog:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/audit-logs/summary")
    public ResponseEntity<String> getAuditSummary(@RequestParam(required = false) String actor,
                                                  @RequestParam(required = false) String action,
                                                  @RequestParam(required = false) String from_date,
                                                  @RequestParam(required = false) String until_date) {
        Map<String, String> query = new LinkedHashMap<>();
        if (actor != null && !actor.isBlank()) {
            query.put("actor", actor);
        }
        if (action != null && !action.isBlank()) {
            query.put("action", action);
        }
        if (from_date != null && !from_date.isBlank()) {
            query.put("from_date", from_date);
        }
        if (until_date != null && !until_date.isBlank()) {
            query.put("until_date", until_date);
        }
        return call(HttpMethod.GET, "/audit-logs/summary", query, new byte[0]);
    }

    // ------------------------------------------------------------------ 导入域（PR-D）

    /**
     * multipart 上传：签名覆盖文件内容 SHA-256 与除 file 外的全部表单字段。
     * 网关收到浏览器上传后整体读入内存再转发；大文件内存峰值由 PR-E 压测。
     */
    @SaCheckPermission(value = "import:batch:upload", orRole = SUPER_ADMIN_ROLE)
    @PostMapping(value = "/imports/preview", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<String> previewImport(
        @RequestParam("file") MultipartFile file,
        @RequestParam("target_type") String targetType,
        @RequestParam(value = "sheet_name", required = false) String sheetName,
        @RequestParam(value = "header_row", required = false) Integer headerRow,
        @RequestParam(value = "mapping", required = false) String mapping) {
        try {
            byte[] data = file.getBytes();
            // 非文件字段：与 Python 端 form.multi_items() 排除 file 后按键排序拼接一致
            Map<String, String> metaFields = new TreeMap<>();
            metaFields.put("target_type", targetType);
            if (sheetName != null && !sheetName.isBlank()) {
                metaFields.put("sheet_name", sheetName);
            }
            if (headerRow != null) {
                metaFields.put("header_row", String.valueOf(headerRow));
            }
            if (mapping != null && !mapping.isBlank()) {
                metaFields.put("mapping", mapping);
            }

            String signPath = "/imports/preview";
            HttpHeaders headers = internalHeaders(HttpMethod.POST, signPath, "",
                sha256(data), normalize(metaFields));

            MultipartBodyBuilder builder = new MultipartBodyBuilder();
            String originalName = file.getOriginalFilename() == null ? "upload.xlsx" : file.getOriginalFilename();
            builder.part("file", new ByteArrayResource(data) {
                @Override
                public String getFilename() {
                    return originalName;
                }
            });
            metaFields.forEach(builder::part);

            String response = RestClient.create()
                .post()
                .uri(importApiBase + signPath)
                .headers(h -> h.addAll(headers))
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(builder.build())
                .retrieve()
                .body(String.class);
            return ResponseEntity.ok(response);
        } catch (RestClientResponseException ex) {
            return upstreamError(ex);
        } catch (Exception ex) {
            return unreachable("POST", "/imports/preview", ex);
        }
    }

    @SaCheckPermission(value = "import:batch:upload", orRole = SUPER_ADMIN_ROLE)
    @PostMapping("/imports/preview-base64")
    public ResponseEntity<String> previewImportBase64(@RequestBody Map<String, Object> payload) {
        return call(HttpMethod.POST, "/imports/preview-base64", Map.of(), Json.write(payload));
    }

    @SaCheckPermission(value = "import:batch:remap", orRole = SUPER_ADMIN_ROLE)
    @PostMapping("/imports/{batchId}/remap")
    public ResponseEntity<String> remapImport(@PathVariable("batchId") Long batchId,
                                              @RequestBody Map<String, Object> payload) {
        return call(HttpMethod.POST, "/imports/" + batchId + "/remap", Map.of(), Json.write(payload));
    }

    @SaCheckPermission(value = "import:batch:validate", orRole = SUPER_ADMIN_ROLE)
    @PostMapping("/imports/{batchId}/validate")
    public ResponseEntity<String> validateImport(@PathVariable("batchId") Long batchId) {
        return call(HttpMethod.POST, "/imports/" + batchId + "/validate", Map.of(), new byte[0]);
    }

    @SaCheckPermission(value = "import:batch:commit", orRole = SUPER_ADMIN_ROLE)
    @PostMapping("/imports/{batchId}/commit")
    public ResponseEntity<String> commitImport(@PathVariable("batchId") Long batchId) {
        return call(HttpMethod.POST, "/imports/" + batchId + "/commit", Map.of(), new byte[0]);
    }

    @SaCheckPermission(value = "import:batch:detail", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/imports/{batchId}")
    public ResponseEntity<String> getImport(@PathVariable("batchId") Long batchId) {
        return call(HttpMethod.GET, "/imports/" + batchId, Map.of(), new byte[0]);
    }

    @SaCheckPermission(value = "import:batch:list", orRole = SUPER_ADMIN_ROLE)
    @GetMapping("/imports")
    public ResponseEntity<String> listImports(@RequestParam(value = "limit", required = false) Integer limit) {
        Map<String, String> query = new LinkedHashMap<>();
        if (limit != null) {
            query.put("limit", String.valueOf(limit));
        }
        return call(HttpMethod.GET, "/imports", query, new byte[0]);
    }

    // ------------------------------------------------------------------ 内部

    /**
     * 构造可信身份、签名并转发到 FastAPI。
     * 身份全部来自 Sa-Token 会话，浏览器无法自行声明。
     *
     * <p>注意：签名用规范化查询串 {@code normalize(query)}（排序+percent-encoding），
     * 而实际 URL 必须用原始值经 UriComponentsBuilder 再编码一次——若把已编码的串
     * 直接拼进 URI 字符串，Spring 会二次编码（% → %25），中文筛选条件全部失效。
     */
    private ResponseEntity<String> call(HttpMethod method, String signPath,
                                        Map<String, String> query, byte[] jsonBody) {
        String normQuery = normalize(query);
        HttpHeaders headers;
        try {
            headers = internalHeaders(method, signPath, normQuery, sha256(jsonBody), "");
        } catch (IllegalStateException ex) {
            return ResponseEntity.status(500).body("{\"detail\":\"INTERNAL_HMAC_SECRET 未配置\"}");
        }

        String url = buildUrl(signPath, query);
        RestClient.RequestBodySpec spec = RestClient.create()
            .method(method)
            .uri(url)
            .headers(h -> h.addAll(headers));

        try {
            spec = spec.contentType(MediaType.APPLICATION_JSON);
            String response = (jsonBody.length == 0 ? spec.body(new byte[0]) : spec.body(jsonBody))
                .retrieve()
                .body(String.class);
            return ResponseEntity.ok(response);
        } catch (RestClientResponseException ex) {
            return upstreamError(ex);
        } catch (Exception ex) {
            return unreachable(method.name(), signPath, ex);
        }
    }

    /**
     * 二进制转发（导出 Excel）：签名逻辑与 {@link #call} 完全一致，
     * 仅以 byte[] 收发，并透传上游的 Content-Type / Content-Disposition。
     */
    private ResponseEntity<byte[]> callBinary(HttpMethod method, String signPath,
                                             Map<String, String> query, byte[] jsonBody) {
        String normQuery = normalize(query);
        HttpHeaders headers;
        try {
            headers = internalHeaders(method, signPath, normQuery, sha256(jsonBody), "");
        } catch (IllegalStateException ex) {
            return ResponseEntity.status(500)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"INTERNAL_HMAC_SECRET 未配置\"}".getBytes(StandardCharsets.UTF_8));
        }

        String url = buildUrl(signPath, query);
        try {
            return RestClient.create()
                .method(method)
                .uri(url)
                .headers(h -> h.addAll(headers))
                .contentType(MediaType.APPLICATION_JSON)
                .body(jsonBody)
                .retrieve()
                .toEntity(byte[].class);
        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(ex.getStatusCode())
                .contentType(MediaType.APPLICATION_JSON)
                .body(ex.getResponseBodyAsString().getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            log.error("内部代理二进制调用失败 {} {}", method, signPath, ex);
            String detail = "{\"detail\":\"上游不可达：" + ex.getClass().getSimpleName() + "\"}";
            return ResponseEntity.status(502)
                .contentType(MediaType.APPLICATION_JSON)
                .body(detail.getBytes(StandardCharsets.UTF_8));
        }
    }

    /**
     * 生成 11 个内部签名头。
     *
     * @param normQuery 已规范化的查询串（无参数为空串）
     * @param payloadSha 请求体或文件内容的 SHA-256
     * @param meta      multipart 非文件字段的规范化串（JSON 请求为空串）
     */
    private HttpHeaders internalHeaders(HttpMethod method, String signPath, String normQuery,
                                        String payloadSha, String meta) {
        if (hmacSecret == null || hmacSecret.isBlank()) {
            throw new IllegalStateException("INTERNAL_HMAC_SECRET 未配置");
        }
        LoginUser loginUser = LoginHelper.getLoginUser();
        String user = "ry:" + LoginHelper.getUsername();
        String role = loginUser.getRoles() == null || loginUser.getRoles().isEmpty()
            ? "unknown"
            : loginUser.getRoles().iterator().next().getRoleKey();
        String deptName = loginUser.getDeptName() == null ? "" : loginUser.getDeptName();
        String deptId = loginUser.getDeptId() == null ? "" : String.valueOf(loginUser.getDeptId());
        boolean admin = SUPER_ADMIN_ROLE.equals(role);

        Set<String> perms = loginUser.getMenuPermission() == null
            ? new TreeSet<>()
            : new TreeSet<>(loginUser.getMenuPermission());
        String permsHeader = String.join(" ", perms);

        String collegeHeader = pct(deptName);
        String collegesHeader = admin ? "" : collegeHeader;
        String adminHeader = admin ? "true" : "false";

        String timestamp = String.valueOf(Instant.now().getEpochSecond());
        String nonce = IdUtil.simpleUUID();

        String canonical = String.join("\n",
            method.name(), signPath, normQuery, timestamp, nonce, payloadSha, meta,
            user, role, collegeHeader, collegesHeader, deptId, adminHeader, permsHeader);
        String signature = hmacHex(hmacSecret, canonical);

        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-User", user);
        headers.set("X-Internal-Role", role);
        headers.set("X-Internal-College", collegeHeader);
        headers.set("X-Internal-Colleges", collegesHeader);
        headers.set("X-Internal-Dept", deptId);
        headers.set("X-Internal-Admin", adminHeader);
        headers.set("X-Internal-Perms", permsHeader);
        headers.set("X-Internal-Timestamp", timestamp);
        headers.set("X-Internal-Nonce", nonce);
        headers.set("X-Internal-Payload-Sha256", payloadSha);
        headers.set("X-Internal-Signature", signature);
        return headers;
    }

    /** FastAPI 返回 4xx/5xx：原样透传状态码与 JSON 错误体。 */
    private static ResponseEntity<String> upstreamError(RestClientResponseException ex) {
        return ResponseEntity.status(ex.getStatusCode())
            .contentType(MediaType.APPLICATION_JSON)
            .body(ex.getResponseBodyAsString());
    }

    /** 网关到 FastAPI 的链路异常：502，不泄露内部地址。 */
    private static ResponseEntity<String> unreachable(String method, String path, Exception ex) {
        log.error("内部代理调用失败 {} {}", method, path, ex);
        return ResponseEntity.status(502)
            .contentType(MediaType.APPLICATION_JSON)
            .body("{\"detail\":\"上游不可达：" + ex.getClass().getSimpleName() + "\"}");
    }

    /** 与 Python 端 _norm_pairs 完全一致：键排序 + 逐字节 percent-encoding。 */
    private static String normalize(Map<String, String> params) {        if (params == null || params.isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : new TreeMap<>(params).entrySet()) {
            if (sb.length() > 0) {
                sb.append('&');
            }
            sb.append(pct(e.getKey())).append('=').append(pct(e.getValue()));
        }
        return sb.toString();
    }

    /**
     * 用原始参数值构造上游 URL：由 Spring 做一次 UTF-8 percent-encoding。
     * 与 normalize() 的分工——签名要规范化串，URL 要原始值，避免二次编码。
     */
    private String buildUrl(String signPath, Map<String, String> query) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromUriString(importApiBase + signPath);
        if (query != null) {
            query.forEach(builder::queryParam);
        }
        return builder.build().toUriString();
    }

    private static String pct(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : value.getBytes(StandardCharsets.UTF_8)) {
            int c = b & 0xFF;
            if (UNRESERVED.indexOf((char) c) >= 0) {
                sb.append((char) c);
            } else {
                sb.append('%').append(String.format("%02X", c));
            }
        }
        return sb.toString();
    }

    private static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 不可用", ex);
        }
    }

    private static String hmacHex(String secret, String data) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGO);
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), HMAC_ALGO));
            return HexFormat.of().formatHex(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("HMAC 计算失败", ex);
        }
    }

    private static final class Json {
        private static final com.fasterxml.jackson.databind.ObjectMapper MAPPER =
            new com.fasterxml.jackson.databind.ObjectMapper();

        private Json() {
        }

        static byte[] write(Object value) {
            try {
                return MAPPER.writeValueAsBytes(value);
            } catch (Exception ex) {
                throw new IllegalStateException("序列化失败", ex);
            }
        }
    }
}
