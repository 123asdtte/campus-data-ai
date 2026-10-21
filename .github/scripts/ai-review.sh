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
# 优先用 PR 的实际提交：pull_request 事件下 GITHUB_SHA 是合并预演提交
# （refs/pull/N/merge），写进评论会指向一个查不到的分支提交。
# 末尾统一取短 hash；set -u 下直接写 ${VAR:0:7} 在变量缺失时会让脚本当场退出。
SHA="${PR_HEAD_SHA:-${GITHUB_SHA:-unknown}}"
SHA="${SHA:0:7}"

# LLM 调用上限：上游 504 是常态，必须给硬上限。
# 没有 --max-time 时 curl 会一直挂着，把 runner 耗到 GitHub 的 6 小时上限。
LLM_TIMEOUT="${LLM_TIMEOUT:-300}"      # 单次请求上限（秒）
LLM_RETRY="${LLM_RETRY:-1}"            # 5xx / 超时的额外重试次数
# 60KB ≈ 1.5 万 token。此前 120KB 约 3~4 万 token，端到端生成很容易超过任何
# 网关的空闲超时；降一半后配合流式输出，实测能拿到首字节并跑完。
DIFF_LIMIT="${DIFF_LIMIT:-61440}"
# 不参与评审的路径。这些文件体积大、token 密度低，且 docs/ 与 samples/ 里
# 可能含真实数据 —— 少发出去一点，README §13 的泄露面就小一点。
DIFF_EXCLUDE="${DIFF_EXCLUDE:-^(docs/|samples/|import-api/wheels/|web/node_modules/)|(package-lock[.]json|pnpm-lock[.]yaml|yarn[.]lock)$|[.](xlsx|xls|xlsm|csv|tsv|png|jpe?g|gif|svg|ico|pdf|zip|whl|woff2?)$}"
FAIL_MARKER="<!-- ai-review-failed -->"  # 失败说明的识别标记，HTML 注释在页面上不可见
# 排查方向随失败原因变化：原因是「模型只思考不出正文」时还让人去查密钥，
# 等于把接手的人往反方向带。
FAIL_HINT=""
DEFAULT_HINT='- 排查方向：仓库 Secrets 中 `AI_MODEL` / `AI_BASE_URL` 是否可用'

# 找出本 PR 上既有的失败说明；没有则输出空字符串
find_status_comment() {
  gh api "repos/$REPO/issues/$PR/comments" --paginate \
    --jq '.[] | select(.body | startswith("<!-- ai-review-failed -->")) | .id' 2>/dev/null | head -1
}

# 在 PR 上说明「本次评审未完成」，然后按设计退出 0（不阻塞合并）
fail() {
  echo "AI 评审失败：$1"
  # 用 printf 逐行写，不用 heredoc：原因里可能带上游返回的 JSON 片段，
  # heredoc 会解释其中的反斜杠转义，导致贴出来的内容变形。
  {
    printf '%s\n' "$FAIL_MARKER"
    printf '## 🤖 AI 评审未完成\n\n'
    printf '提交 `%s` 的**自动评审没有产出结论**，原因：%s\n\n' "$SHA" "$1"
    printf '这不代表 PR 有问题，也**不阻塞合并**，请按常规人工评审。\n\n'
    printf '%s\n' "${FAIL_HINT:-$DEFAULT_HINT}"
    printf -- '- 运行日志：[%s 的评审任务](%s)\n\n' "$SHA" "$RUN_URL"
    printf '<sub>该说明由流水线在评审失败时自动发布；修复上游后可重新运行本任务。</sub>\n'
  } > /tmp/pr-fail.md

  # 只保留一条失败说明：已有就原地更新。
  # 否则每次 push 都新增一条，上游持续不可用时 PR 会被同类评论刷满。
  local existing
  existing=$(find_status_comment)
  if [ -n "$existing" ]; then
    if gh api -X PATCH "repos/$REPO/issues/comments/$existing" \
         -F body=@/tmp/pr-fail.md >/dev/null 2>&1; then
      echo "已更新既有的失败说明（comment=$existing）"
      exit 0
    fi
  fi

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

# 2) 取 PR diff
timeout 60 gh pr diff "$PR" --repo "$REPO" > /tmp/pr.diff 2>/dev/null \
  || fail "获取 PR diff 失败或超时"
if [ ! -s /tmp/pr.diff ]; then
  echo "diff 为空（纯合并/无变更），跳过评审"; exit 0
fi

# 2.1) 按路径过滤：整段 diff 以 "diff --git a/X b/Y" 开头，逐段判定是否保留。
# 用 awk 而不是按行 grep，是因为需要丢弃整个文件段（含上下文行），
# 只删文件头会把 hunk 内容留下，反而让模型看到无归属的片段。
filter_diff() {
  awk -v exclude="$DIFF_EXCLUDE" '
    function flush() { if (keep && buf != "") printf "%s", buf; buf = "" }
    /^diff --git / {
      flush()
      line = $0; sub(/^diff --git /, "", line)
      i = index(line, " b/")
      path = (i > 0) ? substr(line, i + 3) : line
      gsub(/"/, "", path)
      keep = (path !~ exclude)
      if (!keep) { print path > "/dev/stderr" } else { buf = $0 "\n" }
      next
    }
    { if (keep) buf = buf $0 "\n" }
    END { flush() }
  ' "$1" 2> "$2"
}

filter_diff /tmp/pr.diff /tmp/pr.diff.skipped > /tmp/pr.diff.kept || cp /tmp/pr.diff /tmp/pr.diff.kept
if [ ! -s /tmp/pr.diff.kept ]; then
  echo "变更全部落在不评审的路径（docs/ samples/ 锁文件等），跳过评审"; exit 0
fi

# 2.2) 超长时截断。按字节截断可能切在多字节字符中间，产生非法 UTF-8；
# 后面要把内容塞进 JSON，必须先丢掉残缺序列，否则请求体直接是坏字节。
if [ "$(wc -c < /tmp/pr.diff.kept)" -gt "$DIFF_LIMIT" ]; then
  # 截断必然切坏一个多字节字符，iconv 会为此报错，属预期，屏蔽噪声
  head -c "$DIFF_LIMIT" /tmp/pr.diff.kept | iconv -c -f UTF-8 -t UTF-8 2>/dev/null > /tmp/pr.diff.trunc
  printf '\n... [diff 超长，已在此处截断，未包含的改动请直接查看 Files changed]\n' >> /tmp/pr.diff.trunc
else
  cp /tmp/pr.diff.kept /tmp/pr.diff.trunc
fi

# 2.3) 告诉模型哪些文件被过滤掉了：它需要知道"这个 PR 还动了别的东西"，
# 否则容易给出"没有看到任何测试变更"这类基于不完整输入的结论。
if [ -s /tmp/pr.diff.skipped ]; then
  SKIPPED_N=$(sort -u /tmp/pr.diff.skipped | wc -l)
  {
    printf '\n---\n[已按路径过滤，以下文件未纳入评审：'
    sort -u /tmp/pr.diff.skipped | head -8 | tr '\n' ' '
    [ "$SKIPPED_N" -gt 8 ] && printf '等 %s 个' "$SKIPPED_N"
    printf ']\n'
  } >> /tmp/pr.diff.trunc
fi

echo "diff：原始 $(wc -c < /tmp/pr.diff) 字节，过滤后 $(wc -c < /tmp/pr.diff.kept) 字节，送审 $(wc -c < /tmp/pr.diff.trunc) 字节"

# 2.4) 敏感信息前置拦截。
# 评审的代价是把 diff 完整发给外部模型端点，而 README §13 明令「不要分发凭据」。
# 只匹配高置信度的密钥形态，宁可不报也不误伤——误伤会让正常 PR 失去评审，
# 而漏报的风险由「不发出去」这个默认动作兜底。
BLOCKED=""
check_secret() {
  # 用 -e 传模式：私钥特征串以 "-" 开头，不加 -e 会被 grep 当成选项
  grep -aqE -e "$2" /tmp/pr.diff.trunc && BLOCKED="${BLOCKED}${BLOCKED:+, }$1"
  return 0
}
check_secret "AWS AccessKey" 'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}'
check_secret "私钥文件内容" '-----BEGIN [A-Z ]*PRIVATE KEY-----'
check_secret "OpenAI 风格密钥" 'sk-[A-Za-z0-9_-]{24,}'
check_secret "GitHub Token" 'gh[pousr]_[A-Za-z0-9]{20,}'
if [ -n "$BLOCKED" ]; then
  # 只说命中哪一类，绝不回显命中的字符串本身——否则等于把密钥写进 PR 评论
  FAIL_HINT='- 下一步：确认该字符串是否为真实凭据。若是，请立即轮换并从提交历史中移除，然后重新运行本任务'
  fail "diff 中疑似含凭据（$BLOCKED），已阻止发送到外部模型；请确认是否为真实凭据，必要时轮换"
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

注意：若 diff 末尾标注了「已按路径过滤」，说明文档、样例数据、锁文件等
未纳入评审，不要据此判断"某项改动缺失"。

不要复述 diff；不要输出与本 PR 无关的泛泛建议。
PROMPT

# 4) 调用 LLM（OpenAI 兼容协议，流式）
# 用 --rawfile 而非 --arg "$(cat ...)"：60KB 内容过 shell 参数既可能触到
# ARG_MAX，也会让非法字节的报错信息难以定位。
# stream: true 是这里的关键 —— 非流式要等整段生成完才回包，中间零字节，
# 网关的空闲超时会把长任务判死（2026-10-21 实测：300 秒 0 字节，HTTP 000）。
jq -n --rawfile sys /tmp/review-prompt.md --rawfile diff /tmp/pr.diff.trunc \
  --arg model "$AI_MODEL" \
  '{model: $model, stream: true, temperature: 0.2, max_tokens: 8000,
    messages: [{role: "system", content: $sys}, {role: "user", content: $diff}]}' \
  > /tmp/review-body.json

# 可选：给请求体追加参数，用于关掉推理模型的思考阶段。
# 各家开关不同（reasoning_effort / thinking / chat_template_kwargs / enable_thinking），
# 写死在脚本里等于赌某个网关的实现，所以交给仓库变量配置：
#   Settings → Variables → AI_EXTRA_BODY = {"reasoning_effort":"none"}
if [ -n "${AI_EXTRA_BODY:-}" ]; then
  printf '%s' "$AI_EXTRA_BODY" | jq -e 'type == "object"' >/dev/null 2>&1 \
    || fail "AI_EXTRA_BODY 不是合法的 JSON 对象：$AI_EXTRA_BODY"
  printf '%s' "$AI_EXTRA_BODY" > /tmp/extra.json
  jq --slurpfile extra /tmp/extra.json '. * $extra[0]' /tmp/review-body.json > /tmp/review-body.merged \
    && mv /tmp/review-body.merged /tmp/review-body.json
fi

# 从响应里取出正文。端点忽略 stream 时会回完整 JSON，两条路都要能走。
REVIEW=""
STREAM_NOTE=""
REASONING_LEN=0
extract_review() {
  local src=/tmp/review-stream.txt
  if jq -e '.choices[0].message.content' "$src" >/dev/null 2>&1; then
    REVIEW=$(jq -j '.choices[0].message.content // empty' "$src" 2>/dev/null) || true
    return 0
  fi
  # SSE：每行 "data: {...}"，delta.content 逐块拼接；jq -j 让它不额外补换行。
  # grep 无匹配时会返回 1，pipefail 下不能据此判断解析失败，所以统一 || true。
  REVIEW=$(grep -a '^data:' "$src" 2>/dev/null \
    | sed 's/^data:[[:space:]]*//' \
    | grep -av '^\[DONE\][[:space:]]*$' \
    | jq -j '.choices[0].delta.content // empty' 2>/dev/null) || true
  # 推理模型（如 deepseek-*-flash 系列）先整段输出思维链，再给正文。
  # 正文为空而思维链很长，说明时间全花在思考上，超时是结果不是原因。
  REASONING_LEN=$(grep -a '^data:' "$src" 2>/dev/null \
    | sed 's/^data:[[:space:]]*//' \
    | jq -j '.choices[0].delta.reasoning_content // empty' 2>/dev/null | wc -c) || true
  # 正常 SSE 以 [DONE] 收尾；没有它说明连接被中途掐断，内容可能停在半句
  if [ -n "$REVIEW" ] && ! tail -c 200 "$src" | grep -aq '\[DONE\]'; then
    STREAM_NOTE="上游未发送结束标记，以下结论可能被截断。"
  fi
  return 0
}

# 自己控制重试，不用 curl --retry：重试时输出文件是否被清空依赖 curl 版本，
# 叠加起来可能得到两段拼接的残缺内容。
ATTEMPT=1
MAX_ATTEMPTS=$((LLM_RETRY + 1))
# 重试总数不能吃掉 job 预算：workflow 的 timeout-minutes 是 15，
# 要留出 checkout、gh 调用和「发布失败说明」的时间，否则最后一步被 kill，
# 前面辛苦加的留痕逻辑等于没写。三次以内、总时长压在 10 分钟内。
if [ $((MAX_ATTEMPTS * LLM_TIMEOUT)) -gt 600 ]; then
  MAX_ATTEMPTS=$((600 / LLM_TIMEOUT))
  [ "$MAX_ATTEMPTS" -lt 1 ] && MAX_ATTEMPTS=1
fi
while :; do
  : > /tmp/review-stream.txt
  START=$SECONDS
  HTTP_CODE=$(curl -sS -N -o /tmp/review-stream.txt -w "%{http_code}" \
    --max-time "$LLM_TIMEOUT" \
    -X POST "${AI_BASE_URL%/}/chat/completions" \
    -H "Authorization: Bearer $AI_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d @/tmp/review-body.json)
  RC=$?
  [ "$RC" -ne 0 ] && HTTP_CODE="curl_error"
  ELAPSED=$((SECONDS - START))

  REVIEW=""; STREAM_NOTE=""; REASONING_LEN=0
  extract_review
  RECV=$(wc -c < /tmp/review-stream.txt)

  # 拿到正文就算成功；但若连接是中断的（curl 18/28/56），内容必然不完整，
  # 不能当成正常结论发出去，必须挂上显式警告。
  if [ -n "$REVIEW" ] && { [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "curl_error" ]; }; then
    if [ "$HTTP_CODE" != "200" ]; then
      STREAM_NOTE="上游连接在生成过程中中断（curl 退出码 $RC），以下结论不完整，可能缺少最后一部分。"
    fi
    echo "LLM 响应：第 $ATTEMPT 次尝试，HTTP $HTTP_CODE，耗时 ${ELAPSED}s，输出 $(printf '%s' "$REVIEW" | wc -c) 字节"
    break
  fi

  # 收到了数据说明连接是通的，重试只会再耗掉一整个超时（实测：同一份 18KB diff
  # 两次各收 631KB / 953KB 后超时）。只有一个字节都没收到才值得重试。
  if [ "$HTTP_CODE" = "curl_error" ] && [ "$RECV" -gt 0 ]; then break; fi

  # 只对瞬时故障重试；401/403/404 是密钥或模型名配错，重试没有意义
  case "$HTTP_CODE" in
    408|429|5??|curl_error) ;;
    *) break ;;
  esac
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then break; fi
  ATTEMPT=$((ATTEMPT + 1))
  echo "第 $((ATTEMPT - 1)) 次尝试失败（HTTP $HTTP_CODE，${ELAPSED}s），重试中…"
  sleep 5
done

if [ -z "$REVIEW" ]; then
  # 正文为空但思维链很长：推理模型把整个超时预算花在思考上，
  # 报「超时」会把接手的人引向错误方向（去查网络），得说清是模型行为。
  if [ "${REASONING_LEN:-0}" -gt 200 ]; then
    FAIL_HINT='- 排查方向：在仓库 Variables 里设置 `AI_EXTRA_BODY` 关掉思考，或把 `AI_MODEL` 换成非推理模型（详见 CONTRIBUTING §10）'
    fail "模型只产出了思维链（${REASONING_LEN} 字节），${LLM_TIMEOUT}s 内没有进入正文。这不是网络问题——连接正常、数据持续到达，是推理模型的思考阶段吃掉了全部时间。处理方式：用仓库变量 AI_EXTRA_BODY 关掉思考（如 {\"reasoning_effort\":\"none\"}），或换一个非推理模型"
  fi
  # 28=超时 18/56=连接被掐 6=域名解析失败 7=连不上
  case "$RC" in
    28) HINT="，响应超时（模型在 ${LLM_TIMEOUT}s 内没有产出）" ;;
    18|56) HINT="，上游中途断开连接" ;;
    6|7) HINT="，无法连接到 AI_BASE_URL" ;;
    *) HINT="" ;;
  esac
  DETAIL="HTTP $HTTP_CODE，${ELAPSED}s，收到 $(wc -c < /tmp/review-stream.txt) 字节$HINT"
  if [ -s /tmp/review-stream.txt ]; then
    DETAIL="$DETAIL；响应片段：$(tail -c 160 /tmp/review-stream.txt | tr -d '\r\n')"
  fi
  fail "LLM 调用未返回可用结论（$DETAIL）"
fi

# 5) 发布评审评论
{
  echo "## 🤖 AI 评审（自动，仅供参考）"
  echo
  [ -n "$STREAM_NOTE" ] && { echo "> ⚠️ $STREAM_NOTE"; echo; }
  echo "$REVIEW"
  echo
  echo "---"
  echo "*基于提交 \`$SHA\`，由 \`$AI_MODEL\` 自动生成；结论仅供参考，合并决策仍需人工确认。*"
} > /tmp/pr-comment.md

gh pr comment "$PR" --repo "$REPO" --body-file /tmp/pr-comment.md >/dev/null
echo "AI 评审已发布为 PR 评论"

# 评审成功后清掉历史失败说明，避免 PR 上同时挂着「未完成」和「已完成」两条互相矛盾的评论
STALE=$(find_status_comment)
if [ -n "$STALE" ]; then
  gh api -X DELETE "repos/$REPO/issues/comments/$STALE" >/dev/null 2>&1 \
    && echo "已清理历史失败说明（comment=$STALE）"
fi
