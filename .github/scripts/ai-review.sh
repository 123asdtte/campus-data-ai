#!/usr/bin/env bash
# PR 自动评审：把变更发给 LLM，评审结论作为 PR 评论发布。
# 依赖仓库 Secrets：AI_API_KEY / AI_BASE_URL / AI_MODEL（缺任一则跳过，不阻塞 PR）。
set -uo pipefail

PR="${PR_NUMBER:?PR_NUMBER 未设置}"
REPO="${GITHUB_REPOSITORY:?}"

# 1) 未配置密钥时优雅跳过（配置方法见 CONTRIBUTING.md §10）
if [ -z "${AI_API_KEY:-}" ] || [ -z "${AI_BASE_URL:-}" ] || [ -z "${AI_MODEL:-}" ]; then
  echo "未配置 AI_API_KEY / AI_BASE_URL / AI_MODEL，跳过 AI 评审。"
  echo "配置方法：仓库 Settings → Secrets and variables → Actions，或 gh secret set AI_API_KEY"
  exit 0
fi

# 2) 取 PR diff（过大时截断头部 120KB）
gh pr diff "$PR" --repo "$REPO" > /tmp/pr.diff 2>/dev/null || {
  echo "获取 diff 失败，跳过 AI 评审"; exit 0;
}
if [ ! -s /tmp/pr.diff ]; then
  echo "diff 为空（纯合并/无变更），跳过评审"; exit 0
fi
head -c 122880 /tmp/pr.diff > /tmp/pr.diff.trunc
if [ "$(wc -c < /tmp/pr.diff)" -gt 122880 ]; then
  echo "" >> /tmp/pr.diff.trunc
  echo "... [diff 超长，已截断，完整内容请直接查看文件变更]" >> /tmp/pr.diff.trunc
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
jq -n --arg sys "$(cat /tmp/review-prompt.md)" --arg diff "$(cat /tmp/pr.diff.trunc)" --arg model "$AI_MODEL" \
  '{model: $model, messages: [{role: "system", content: $sys}, {role: "user", content: $diff}], temperature: 0.2}' \
  > /tmp/review-body.json

HTTP_CODE=$(curl -sS -o /tmp/review-resp.json -w "%{http_code}" \
  -X POST "${AI_BASE_URL%/}/chat/completions" \
  -H "Authorization: Bearer $AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/review-body.json) || HTTP_CODE="curl_error"

REVIEW=$(jq -r '.choices[0].message.content // empty' /tmp/review-resp.json 2>/dev/null || true)

if [ "$HTTP_CODE" != "200" ] || [ -z "$REVIEW" ]; then
  echo "LLM 调用失败（HTTP $HTTP_CODE），跳过发布评审评论："
  head -c 300 /tmp/review-resp.json 2>/dev/null || true
  exit 0   # 评审失败不阻塞 PR
fi

# 5) 发布评审评论
{
  echo "## 🤖 AI 评审（自动，仅供参考）"
  echo
  echo "$REVIEW"
  echo
  echo "---"
  echo "*由 \`$AI_MODEL\` 自动生成；结论仅供参考，合并决策仍需人工确认。*"
} > /tmp/pr-comment.md

gh pr comment "$PR" --repo "$REPO" --body-file /tmp/pr-comment.md >/dev/null
echo "AI 评审已发布为 PR 评论"
