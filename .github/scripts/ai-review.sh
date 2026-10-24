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
# 连接阶段上限。2026-10-24 实测：上游地址路由不通时，curl 只有 --max-time，
# 探测干等 30s、正式请求干等 300s 全耗在 TCP 连不上上；--connect-timeout
# 把「连不上」（秒级可判死）和「生成慢」（需要长超时）分开约束。
LLM_CONNECT_TIMEOUT="${LLM_CONNECT_TIMEOUT:-15}"
# LLM 环节（探测 + 正式请求 + 重试）的总预算。job 上限是 15 分钟，checkout、
# 取 diff、发评论还要占掉一部分；不设总账的话，探测跑满再叠加重试会把 job
# 拖过 900s，最后被 kill 在「发布失败说明」之前 —— 留痕逻辑等于白写。
# 720 = job 上限 900s 减去 checkout、取 diff、发评论的余量。
LLM_BUDGET="${LLM_BUDGET:-720}"
# 到点前至少留这么多秒发评论
LLM_RESERVE=60
# 60KB ≈ 1.5 万 token。此前 120KB 约 3~4 万 token，端到端生成很容易超过任何
# 网关的空闲超时；降一半后配合流式输出，实测能拿到首字节并跑完。
DIFF_LIMIT="${DIFF_LIMIT:-61440}"
# 不参与评审的路径。这些文件体积大、token 密度低，且 docs/ 与 samples/ 里
# 可能含真实数据 —— 少发出去一点，README §13 的泄露面就小一点。
DIFF_EXCLUDE="${DIFF_EXCLUDE:-^(docs/|samples/|import-api/wheels/|web/node_modules/)|(package-lock[.]json|pnpm-lock[.]yaml|yarn[.]lock)$|[.](xlsx|xls|xlsm|csv|tsv|png|jpe?g|gif|svg|ico|pdf|zip|whl|woff2?)$}"
# 数值型变量来自仓库 Variables，配错成非数字时会在后面的算术展开处直接终止
# 脚本——而那时还没走到 fail，PR 上一点痕迹都没有。所以先统一校验并回退默认值。
is_uint() { case "${1:-}" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
for CFG_VAR in LLM_TIMEOUT LLM_RETRY LLM_CONNECT_TIMEOUT LLM_BUDGET PROBE_TIMEOUT DIFF_LIMIT; do
  if ! is_uint "${!CFG_VAR:-}"; then
    case "$CFG_VAR" in
      LLM_TIMEOUT) LLM_TIMEOUT=300 ;;
      LLM_RETRY) LLM_RETRY=1 ;;
      LLM_CONNECT_TIMEOUT) LLM_CONNECT_TIMEOUT=15 ;;
      LLM_BUDGET) LLM_BUDGET=720 ;;
      PROBE_TIMEOUT) PROBE_TIMEOUT=30 ;;
      DIFF_LIMIT) DIFF_LIMIT=61440 ;;
    esac
    # 未设置时 ${VAR:-默认} 已经填了默认值，走到这里说明仓库变量写成了非数字
    echo "$CFG_VAR 的值不是正整数（或未设置），已回退为 ${!CFG_VAR}"
  fi
done
LLM_DEADLINE=$((SECONDS + LLM_BUDGET))
remaining_budget() { echo $((LLM_DEADLINE - SECONDS)); }

FAIL_MARKER="<!-- ai-review-failed -->"  # 失败说明的识别标记，HTML 注释在页面上不可见
# 排查方向随失败原因变化：原因是「模型只思考不出正文」时还让人去查密钥，
# 等于把接手的人往反方向带。
FAIL_HINT=""
DEFAULT_HINT='- 排查方向：仓库 Secrets 中 `AI_MODEL` / `AI_BASE_URL` 是否可用'

# 找出本 PR 上既有的失败说明（可能有多条：并发运行或历史重跑留下的），
# 每行一个 id；没有则输出空字符串
find_status_comment() {
  # 末尾过滤成纯数字：gh --paginate 多页输出时页间可能混入非数字行，
  # 后面的 while read 会把它们当成 comment id 去调用接口
  gh api "repos/$REPO/issues/$PR/comments" --paginate \
    --jq '.[] | select(.body | startswith("<!-- ai-review-failed -->")) | .id' 2>/dev/null \
    | grep -E '^[0-9]+$'
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
  local ids first id
  ids=$(find_status_comment)
  first=$(printf '%s\n' "$ids" | head -1)
  if [ -n "$first" ]; then
    if gh api -X PATCH "repos/$REPO/issues/comments/$first" \
         -F body=@/tmp/pr-fail.md >/dev/null 2>&1; then
      echo "已更新既有的失败说明（comment=$first）"
      # 并发或历史重跑可能留下多条同类说明，其余删掉
      printf '%s\n' "$ids" | tail -n +2 | while read -r id; do
        [ -n "$id" ] && gh api -X DELETE "repos/$REPO/issues/comments/$id" >/dev/null 2>&1
      done
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
    # 先用 "diff --git" 头的路径做个初判，后面遇到 +++ / --- 行再校正：
    # 头行按 " b/" 切在重命名（a/old b/new）和文件名含空格时会取错路径，
    # 而 +++ b/xxx 才是新路径的唯一权威来源。
    /^diff --git / {
      flush()
      line = $0; sub(/^diff --git /, "", line)
      i = index(line, " b/")
      path = (i > 0) ? substr(line, i + 3) : line
      gsub(/"/, "", path)
      keep = (path !~ exclude)
      pending = 1
      if (!keep) { print path > "/dev/stderr"; buf = "" } else { buf = $0 "\n" }
      next
    }
    # 二进制 diff 没有 +++ 行，pending 会一直悬到下一个 diff --git 头；
    # 这里显式清零，避免状态泄漏到后面的段落
    pending && /^(Binary files|GIT binary patch)/ { pending = 0 }
    # 只看 +++ 行：--- 是旧路径，删除文件时它是 /dev/null，重命名时它是旧名字，
    # 拿它做判断会误伤「从 docs/ 挪到代码目录」这类改动
    pending && /^\+\+\+ / {
      p = $0; sub(/^\+\+\+ /, "", p); sub(/\t.*$/, "", p)
      sub(/^[ab]\//, "", p); gsub(/"/, "", p)
      pending = 0
      # 头行已经判为不保留的，不要在这里翻案（否则会留下没有归属的片段）
      if (keep && p !~ exclude) { buf = buf $0 "\n" }
      else if (keep) { print p > "/dev/stderr"; buf = "" ; keep = 0 }
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
# 只匹配高置信度的密钥形态。命中即中止整次评审（宁可误伤也不漏报）——误伤的
# 代价只是这次没有 AI 评审，漏报的代价是把凭据真的发了出去。
# 扫的是「过滤后、截断前」的完整 diff：只扫截断后的 60KB 的话，写在后面的
# 密钥会被截掉从而漏检，然后照常发出去。
BLOCKED=""
check_secret() {
  # 用 -e 传模式：私钥特征串以 "-" 开头，不加 -e 会被 grep 当成选项
  grep -aqE -e "$2" /tmp/pr.diff.kept && BLOCKED="${BLOCKED}${BLOCKED:+, }$1"
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

# 3.5) 自动探测并关闭推理模型的「思考阶段」
# 2026-10-21 实测：deepseek-*-flash 这类推理模型会把整份超时预算耗在
# reasoning_content 上，正文始终零字节，评论只能写「未完成」。
# 各家网关的开关字段不一样（chat_template_kwargs.enable_thinking /
# enable_thinking / thinking.type / reasoning_effort / thinking_budget），
# 写死任何一个都是赌某个网关的实现。
# 所以：先用一次极小的探测请求判断这个模型到底会不会先思考；会的话再逐个试
# 开关，取第一个让 reasoning_content 归零的。探测成本（几秒到 30 秒）远低于
# 一次注定失败的正式请求（300 秒）。
# 探测提示词必须能触发思考（真给一段 diff）：平凡提示词下推理模型本来就不
# 思考，探测会全部误判为「无需关闭」。
PROBE_TIMEOUT="${PROBE_TIMEOUT:-30}"
PROBE_CANDIDATES='[{"chat_template_kwargs":{"enable_thinking":false}},{"enable_thinking":false},{"thinking":{"type":"disabled"}},{"reasoning_effort":"none"},{"thinking_budget":0}]'
THINK_OFF=""
PROBE_CODE=""
PROBE_TEXT_LEN=0
PROBE_REASON_LEN=0

# 取响应里某个字段的长度。端点忽略 stream 时回完整 JSON，正常时是 SSE，两条路都要能读。
llm_field_len() {
  # 注意：SSE 末尾的 "data: [DONE]" 不是 JSON，jq 会在拼完正文后返回非 0。
  # 这里不能写 `|| v=""` —— 那会把已经拼好的内容整个丢掉，最终读到 0 字节。
  local f="$1" k="$2" v=""
  v=$(jq -j ".choices[0].message.$k // empty" "$f" 2>/dev/null) || true
  if [ -z "$v" ]; then
    v=$(grep -a '^data:' "$f" 2>/dev/null | sed 's/^data:[[:space:]]*//' \
      | jq -j ".choices[0].delta.$k // empty" 2>/dev/null) || true
  fi
  printf '%s' "$v" | wc -c | tr -d '[:space:]'
}

# $1 = 要追加到请求体的 JSON 对象（"{}" 表示不加）；$2 = 本次超时（可选）
# 结果写入 PROBE_* 三个变量
probe_once() {
  local extra="$1" tmo="${2:-$PROBE_TIMEOUT}" code=""
  # max_tokens 给 256：上限太低会把思维链一起截断，探测就读不到
  # reasoning_content，从而把「会思考的模型」误判成「不思考」。
  # 注释不能写在多行命令的中间 —— 那会把反斜杠续行一起注释掉，jq 收不到过滤器。
  jq -n --rawfile sys /tmp/probe-prompt.md --rawfile diff /tmp/probe.diff \
    --arg model "$AI_MODEL" --argjson extra "$extra" \
    '{model: $model, stream: true, temperature: 0.2, max_tokens: 256,
      messages: [{role: "system", content: $sys}, {role: "user", content: $diff}]} + $extra' \
    > /tmp/probe-body.json 2>/dev/null || return 2
  : > /tmp/probe-out.txt
  # 连接阶段单独约束：探测本身只有 30s，若上游连不上，10s 内就该判死，
  # 不让它把整个探测超时耗在 TCP 握手上
  local ctmo=10
  [ "$tmo" -lt "$ctmo" ] && ctmo=$tmo
  code=$(curl -sS -N -o /tmp/probe-out.txt -w "%{http_code}" \
    --max-time "$tmo" \
    --connect-timeout "$ctmo" \
    -X POST "${AI_BASE_URL%/}/chat/completions" \
    -H "Authorization: Bearer $AI_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d @/tmp/probe-body.json) || code="curl_error"
  PROBE_CODE="$code"
  PROBE_TEXT_LEN=$(llm_field_len /tmp/probe-out.txt content)
  PROBE_REASON_LEN=$(llm_field_len /tmp/probe-out.txt reasoning_content)
  # 「应答成功」≠「拿到正文」：推理模型只吐思维链时 HTTP 也是 200。
  # 两者要分开判断，否则「只思考」会被当成探测失败，直接跳过所有开关。
  [ "$code" = "200" ] || return 1
  [ "${PROBE_TEXT_LEN:-0}" -gt 0 ] && return 0
  [ "${PROBE_REASON_LEN:-0}" -gt 0 ] && return 0
  return 1
}

if [ -z "${AI_EXTRA_BODY:-}" ] && [ "$(remaining_budget)" -gt "$PROBE_TIMEOUT" ]; then
  head -c 1500 /tmp/pr.diff.trunc > /tmp/probe.diff
  cat > /tmp/probe-prompt.md <<'PROBE'
你是代码评审员。读下面这段 diff 片段，用一句话（不超过 30 字）指出最值得关注的一点。
PROBE
  if probe_once '{}'; then
    if [ "${PROBE_REASON_LEN:-0}" -gt 0 ]; then
      echo "探测：模型先输出思维链（${PROBE_REASON_LEN} 字节），逐个尝试关闭思考的开关…"
      local_n=$(printf '%s' "$PROBE_CANDIDATES" | jq 'length')
      local_i=0
      while [ "$local_i" -lt "$local_n" ]; do
        local_left=$(remaining_budget)
        # 预算见底就停止探测：继续试下去会把正式请求的时间也吃掉，
        # 最后既没结论也没留下失败说明
        if [ "$local_left" -le "$LLM_RESERVE" ]; then
          echo "探测：剩余预算 ${local_left}s，停止探测，保住正式请求的时间"
          break
        fi
        local_tmo=$PROBE_TIMEOUT
        [ "$local_left" -lt "$local_tmo" ] && local_tmo=$local_left
        local_cand=$(printf '%s' "$PROBE_CANDIDATES" | jq -c ".[$local_i]")
        if probe_once "$local_cand" "$local_tmo"; then
          if [ "${PROBE_REASON_LEN:-0}" -eq 0 ] && [ "${PROBE_TEXT_LEN:-0}" -gt 0 ]; then
            THINK_OFF="$local_cand"
            echo "探测：$local_cand 生效，正式请求将带上该参数"
            break
          fi
          echo "探测：$local_cand 仍有思维链（${PROBE_REASON_LEN} 字节），换下一个"
        else
          if [ "${PROBE_CODE:-}" = "429" ]; then
            # 限流已触发：继续换开关只会把仅剩的配额烧光，正式请求必然 429。
            # 2026-10-24 实测：网关限流窗口很紧，探测 6 次后正式请求 100% 429。
            echo "探测：$local_cand 触发限流（HTTP 429），停止探测，把配额留给正式请求"
            break
          fi
          echo "探测：$local_cand 未被接受（HTTP ${PROBE_CODE:-未知}），换下一个"
        fi
        local_i=$((local_i + 1))
      done
      [ -z "$THINK_OFF" ] && echo "探测：所有已知开关都无效，按原样发起正式请求"
    else
      echo "探测：模型直接输出正文（${PROBE_TEXT_LEN} 字节），无需关闭思考"
    fi
  else
    echo "探测请求未成功（HTTP ${PROBE_CODE:-未知}），按原样发起正式请求"
  fi
fi

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
  printf '%s' "$AI_EXTRA_BODY" | jq -e 'type == "object"' >/dev/null 2>&1 || {
    # 默认提示会让人去查 AI_MODEL / AI_BASE_URL，但这里的原因只是变量写错了
    FAIL_HINT='- 排查方向：仓库 Variables 里的 `AI_EXTRA_BODY` 必须是 JSON **对象**，例如 `{"reasoning_effort":"none"}`（详见 CONTRIBUTING §10）'
    fail "AI_EXTRA_BODY 不是合法的 JSON 对象：$AI_EXTRA_BODY"
  }
  printf '%s' "$AI_EXTRA_BODY" > /tmp/extra.json
  jq --slurpfile extra /tmp/extra.json '. * $extra[0]' /tmp/review-body.json > /tmp/review-body.merged \
    && mv /tmp/review-body.merged /tmp/review-body.json
elif [ -n "$THINK_OFF" ]; then
  # 自动探测得到的开关（见 3.5）
  jq --argjson extra "$THINK_OFF" '. + $extra' /tmp/review-body.json > /tmp/review-body.merged \
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
HTTP_CODE="未发起"; RC=0; ELAPSED=0
while :; do
  LEFT=$(remaining_budget)
  # 探测已经吃掉不少时间时，正式请求必须按剩余预算收缩，不能照用 300s：
  # 被 job 超时 kill 掉的话，前面拿到的内容一点都发不出去。
  if [ "$LEFT" -le "$LLM_RESERVE" ]; then
    echo "LLM 预算耗尽（剩余 ${LEFT}s），放弃正式请求"
    break
  fi
  CUR_TIMEOUT=$LLM_TIMEOUT
  [ "$LEFT" -lt "$CUR_TIMEOUT" ] && CUR_TIMEOUT=$LEFT
  # 连接阶段上限取 min(LLM_CONNECT_TIMEOUT, CUR_TIMEOUT)：CUR_TIMEOUT 可能已被
  # 剩余预算压得很小，connect-timeout 不应反过来超过总超时
  CT=$LLM_CONNECT_TIMEOUT
  [ "$CUR_TIMEOUT" -lt "$CT" ] && CT=$CUR_TIMEOUT
  : > /tmp/review-stream.txt
  START=$SECONDS
  HTTP_CODE=$(curl -sS -N -o /tmp/review-stream.txt -w "%{http_code}" \
    --max-time "$CUR_TIMEOUT" \
    --connect-timeout "$CT" \
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
  # 429 用更长的退避：限流窗口通常在秒级以上，实测 sleep 5 后立刻重试仍是 429
  if [ "$HTTP_CODE" = "429" ]; then sleep 20; else sleep 5; fi
done

if [ -z "$REVIEW" ]; then
  # 正文为空但思维链很长：推理模型把整个超时预算花在思考上，
  # 报「超时」会把接手的人引向错误方向（去查网络），得说清是模型行为。
  if [ "${REASONING_LEN:-0}" -gt 200 ]; then
    # 已自动试过开关仍无效 = 这个网关不吃已知任何一种；明确说已试过，
    # 免得接手的人再从零排查一遍
    if [ -n "$THINK_OFF" ]; then
      TRIED="本次已自动加上 \`$THINK_OFF\` 关闭思考，模型仍在输出思维链"
    else
      TRIED="本次已自动试过 $(printf '%s' "$PROBE_CANDIDATES" | jq 'length') 种关闭思考的开关，这个网关都没有接受"
    fi
    FAIL_HINT='- 排查方向：在仓库 Variables 里设置 `AI_EXTRA_BODY`（用你的网关实际支持的字段），或把 `AI_MODEL` 换成非推理模型（详见 CONTRIBUTING §10）'
    fail "模型只产出了思维链（${REASONING_LEN} 字节），${LLM_TIMEOUT}s 内没有进入正文。这不是网络问题——连接正常、数据持续到达，是推理模型的思考阶段吃掉了全部时间。${TRIED}；请用仓库变量 AI_EXTRA_BODY 指定该网关的开关字段，或换一个非推理模型"
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
STALE_IDS=$(find_status_comment)
if [ -n "$STALE_IDS" ]; then
  printf '%s\n' "$STALE_IDS" | while read -r stale; do
    [ -n "$stale" ] && gh api -X DELETE "repos/$REPO/issues/comments/$stale" >/dev/null 2>&1 \
      && echo "已清理历史失败说明（comment=$stale）"
  done
fi
