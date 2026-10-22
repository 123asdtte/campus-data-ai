package org.dromara.web.controller.internal;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.hutool.core.util.IdUtil;
import lombok.extern.slf4j.Slf4j;
import org.dromara.common.satoken.utils.LoginHelper;
import org.dromara.system.api.model.LoginUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

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
    public ResponseEntity<String> listStudents(@RequestParam(required = false) String keyword) {
        Map<String, String> query = new LinkedHashMap<>();
        if (keyword != null && !keyword.isBlank()) {
            query.put("keyword", keyword);
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

    // ------------------------------------------------------------------ 内部

    /**
     * 构造可信身份、签名并转发到 FastAPI。
     * 身份全部来自 Sa-Token 会话，浏览器无法自行声明。
     */
    private ResponseEntity<String> call(HttpMethod method, String signPath,
                                        Map<String, String> query, byte[] jsonBody) {
        if (hmacSecret == null || hmacSecret.isBlank()) {
            return ResponseEntity.status(500).body("{\"detail\":\"INTERNAL_HMAC_SECRET 未配置\"}");
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

        String normQuery = normalize(query);
        String payloadSha = sha256(jsonBody);
        String timestamp = String.valueOf(Instant.now().getEpochSecond());
        String nonce = IdUtil.simpleUUID();

        String canonical = String.join("\n",
            method.name(), signPath, normQuery, timestamp, nonce, payloadSha, "",
            user, role, collegeHeader, collegesHeader, deptId, adminHeader, permsHeader);
        String signature = hmacHex(hmacSecret, canonical);

        String url = importApiBase + signPath + (normQuery.isEmpty() ? "" : "?" + normQuery);
        RestClient.RequestBodySpec spec = RestClient.create()
            .method(method)
            .uri(url)
            .header("X-Internal-User", user)
            .header("X-Internal-Role", role)
            .header("X-Internal-College", collegeHeader)
            .header("X-Internal-Colleges", collegesHeader)
            .header("X-Internal-Dept", deptId)
            .header("X-Internal-Admin", adminHeader)
            .header("X-Internal-Perms", permsHeader)
            .header("X-Internal-Timestamp", timestamp)
            .header("X-Internal-Nonce", nonce)
            .header("X-Internal-Payload-Sha256", payloadSha)
            .header("X-Internal-Signature", signature);

        try {
            spec = spec.contentType(MediaType.APPLICATION_JSON);
            String response = (jsonBody.length == 0 ? spec.body(new byte[0]) : spec.body(jsonBody))
                .retrieve()
                .body(String.class);
            return ResponseEntity.ok(response);
        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(ex.getStatusCode())
                .contentType(MediaType.APPLICATION_JSON)
                .body(ex.getResponseBodyAsString());
        } catch (Exception ex) {
            log.error("内部代理调用失败 {} {}", method, signPath, ex);
            return ResponseEntity.status(502)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"上游不可达：" + ex.getClass().getSimpleName() + "\"}");
        }
    }

    /** 与 Python 端 _norm_pairs 完全一致：键排序 + 逐字节 percent-encoding。 */
    private static String normalize(Map<String, String> params) {
        if (params == null || params.isEmpty()) {
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
