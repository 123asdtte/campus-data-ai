#!/usr/bin/env bash
# PR 自动评审：把变更发给 LLM，评审结论作为 PR 评论发布。
# 依赖仓库 Secrets：AI_API_KEY / AI_BASE_URL / AI_MODEL（缺任一则跳过，不阻塞 PR）。
#
# 两条硬约束：
# 1. 评审失败绝不阻塞 PR —— 任何失败路径统一 exit 0。
# 2. 失败必须在 PR 上留痕 —— 否则「没跑」和「跑过但没发现问题」在 PR 页面
#    看起来完全一样，评审会变成一种虚假的安全感（2026-10-21 实测：上游返回
#    HTTP 504，job 仍然显示绿色，PR 上零痕迹）。
set -uo pipefail

PR="${PR_NUMBER:?PR_NUMBER 未设置}"
REPO="${GITHUB_REPOSITORY:?}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-0}"
# 末尾取短 hash 用；set -u 下直接写 ${GITHUB_SHA:0:7} 在变量缺失时会让脚本当场退出
SHA="${GITHUB_SHA:-unknown}"
SHA="${SHA:0:7}"

# LLM 调用上限：上游 504 是常态，必须给硬上限。
# 没有 --max-time 时 curl 会一直挂着，把 runner 耗到 GitHub 的 6 小时上限。
LLM_TIMEOUT="${LLM_TIMEOUT:-300}"      # 单次请求上限（秒）
LLM_RETRY="${LLM_RETRY:-1}"            # 5xx / 超时的重试次数
LLM_RETRY_MAX="${LLM_RETRY_MAX:-600}"  # 含重试的总时长上限（秒）
DIFF_LIMIT=122880                      # 120KB

# 在 PR 上说明「本次评审未完成」，然后按设计退出 0（不阻塞合并）
fail() {
  echo "AI 评审失败：$1"
  # 用 printf 逐行写，不用 heredoc：原因里可能带上游返回的 JSON 片段，
  # heredoc 会解释其中的反斜杠转义，导致贴出来的内容变形。
  {
    printf '## 🤖 AI 评审未完成\n\n'
    printf '提交 `%s` 的**自动评审没有产出结论**，原因：%s\n\n' "$SHA" "$1"
    printf '这不代表 PR 有问题，也**不阻塞合并**，请按常规人工评审。\n\n'
    printf -- '- 排查方向：仓库 Secrets 中 `AI_MODEL` / `AI_BASE_URL` 是否可用\n'
    printf -- '- 运行日志：[%s 的评审任务](%s)\n\n' "$SHA" "$RUN_URL"
    printf '<sub>该说明由流水线在评审失败时自动发布；修复上游后可重新运行本任务。</sub>\n'
  } > /tmp/pr-fail.md
  gh pr comment "$PR" --repo "$REPO" --body-file /tmp/pr-fail.md >/dev/null 2>&1 \
    && echo "已在 PR 上发布失败说明" \
    || echo "失败说明发布失败（忽略，不影响合并）"
  exit 0
}

# 1) 未配置密钥时优雅跳过（配置方法见 CONTRIBUTING.md §10）
if [ -z "${AI_API_KEY:-}" ] || [ -z "${AI_BASE_URL:-}" ] || [ -z "${AI_MODEL:-}" ]; then
  echo "未配置 AI_API_KEY / AI_BASE_URL / AI_MODEL，跳过 AI 评审。"
  echo "配置方法：仓库 Settings → Secrets and variables → Actions，或 gh secret set AI_API_KEY"
  exit 0
fi

# 2) 取 PR diff（过大时截断头部 120KB）
timeout 60 gh pr diff "$PR" --repo "$REPO" > /tmp/pr.diff 2>/dev/null \
  || fail "获取 PR diff 失败或超时"
if [ ! -s /tmp/pr.diff ]; then
  echo "diff 为空（纯合并/无变更），跳过评审"; exit 0
fi

if [ "$(wc -c < /tmp/pr.diff)" -gt "$DIFF_LIMIT" ]; then
  # 按字节截断可能切在多字节字符中间，产生非法 UTF-8；
  # 后面要把它塞进 JSON，必须先丢掉残缺序列，否则请求体直接是坏字节。
  head -c "$DIFF_LIMIT" /tmp/pr.diff | iconv -c -f UTF-8 -t UTF-8 > /tmp/pr.diff.trunc
  printf '\n... [diff 超长，已截断，完整内容请直接查看文件变更]\n' >> /tmp/pr.diff.trunc
else
  cp /tmp/pr.diff /tmp/pr.diff.trunc
fi

# 3) 评审提示词：聚焦本项目最在意的问题
cat > /tmp/review-prompt.md <<'PROMPT'
你是资深代码评审员，负责审查校园数据管理项目的 PR。

项目背景：FastAPI + PostgreSQL + React；学生数据按「学院」隔离；
所有业务写入依赖 PostgreSQL 触发器在同事务写审计（operation_logs）；
当前主系统尚无认证，正在分阶段接入若依认证链路。

审查重点（按优先级）：
1. 认证/授权绕过：是否有接口未挂依赖就读写数据；是否信任客户端自报身份（X-Actor 等）
2. 数据范围：学院隔离是否在 SQL WHERE 层强制；参数是否可能扩大范围
3. SQL 安全：是否参数化；有无拼接调用方输入
4. 事务与审计：业务写入与审计是否同事务；回滚是否一致
5. 敏感信息：密钥/密码/真实数据是否硬编码或打印
6. 兼容性与回退：改动是否影响存量数据；出问题如何撤回

输出格式（中文）：
- 【阻断】必须修复才能合并的问题（没有就写「未发现阻断性问题」）
- 【建议】可选改进
- 【确认】需要人工核实的点（AI 无法判断的部分）

不要复述 diff；不要输出与本 PR 无关的泛泛建议。
PROMPT

# 4) 调用 LLM（OpenAI 兼容协议）
# 用 --rawfile 而非 --arg "$(cat ...)"：120KB 内容过 shell 参数既可能触到 ARG_MAX，
# 也会让非法字节的报错信息难以定位。
jq -n --rawfile sys /tmp/review-prompt.md --rawfile diff /tmp/pr.diff.trunc \
  --arg model "$AI_MODEL" \
  '{model: $model, messages: [{role: "system", content: $sys}, {role: "user", content: $diff}], temperature: 0.2, max_tokens: 8000}' \
  > /tmp/review-body.json

HTTP_CODE=$(curl -sS -o /tmp/review-resp.json -w "%{http_code}" \
  --max-time "$LLM_TIMEOUT" \
  --retry "$LLM_RETRY" --retry-delay 5 --retry-max-time "$LLM_RETRY_MAX" \
  -X POST "${AI_BASE_URL%/}/chat/completions" \
  -H "Authorization: Bearer $AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/review-body.json) || HTTP_CODE="curl_error"

REVIEW=$(jq -r '.choices[0].message.content // empty' /tmp/review-resp.json 2>/dev/null || true)

if [ "$HTTP_CODE" != "200" ] || [ -z "$REVIEW" ]; then
  DETAIL="HTTP $HTTP_CODE"
  if [ -s /tmp/review-resp.json ]; then
    DETAIL="$DETAIL：$(head -c 200 /tmp/review-resp.json | tr -d '\r\n')"
  fi
  fail "LLM 调用未返回可用结论（$DETAIL）"
fi

# 5) 发布评审评论
{
  echo "## 🤖 AI 评审（自动，仅供参考）"
  echo
  echo "$REVIEW"
  echo
  echo "---"
  echo "*基于提交 \`$SHA\`，由 \`$AI_MODEL\` 自动生成；结论仅供参考，合并决策仍需人工确认。*"
} > /tmp/pr-comment.md

gh pr comment "$PR" --repo "$REPO" --body-file /tmp/pr-comment.md >/dev/null
echo "AI 评审已发布为 PR 评论"
