# Agentic / Harness Engineering Research Report

> 기준일: 2026-04-26  
> 문서 성격: 순수 연구 리포트. 즉시 구현 플랜이나 ADR이 아니라, 로컬 LLM 환경에서 작은 업무/도메인별 AI 에이전트 설계를 검토하기 위한 기술 조사 문서다.

## Executive Summary

이 리포트의 중심 질문은 다음이다.

> 하나의 LLM 서비스가 계속 거대한 공통 컨텍스트를 오가며 모든 사용자 요청을 처리하는 방식보다, 관리 에이전트가 작은 업무/도메인별 specialist agent를 호출하는 방식이 로컬 Qwen3.6-35B-A3B(MoE, 활성 3B) 환경에서 왜 유리한가?

조사 결과, 권고 방향은 다음 구조다.

```
manager agent
  -> domain/task specialist agents
  -> narrow tool surface
  -> scoped memory/context
  -> eval/trace harness
```

핵심 근거는 네 가지다.

1. 최신 agentic engineering은 "모든 것을 한 agent에 넣는 방식"보다 단순하고 조합 가능한 workflow에서 시작해, 필요한 경우에만 agent autonomy를 높이는 방향으로 이동하고 있다. Anthropic은 성공적인 agentic system이 복잡한 framework보다 단순하고 조합 가능한 패턴을 쓰는 경우가 많다고 정리한다. [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
2. multi-agent 구조는 모든 문제에 좋은 것이 아니라, 독립적인 하위 탐색이 많고 병렬화 가치가 큰 문제에서 강하다. Anthropic의 research system 사례는 breadth-first research에서 multi-agent가 효과적이지만, token 비용과 coordination 복잡도가 커진다고 설명한다. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
3. 로컬 LLM에서는 context length가 길어도 tool catalog, tool result, multi-turn history가 길어질수록 function calling 품질이 떨어질 수 있다. LongFuncEval은 tool 수, tool response 길이, conversation 길이가 늘 때 function-calling 성능이 크게 저하될 수 있음을 보고한다. [LongFuncEval](https://arxiv.org/abs/2505.10570)
4. Qwen3.6-35B-A3B는 긴 context와 tool use를 지원하는 MoE(총 35B / 활성 3B, 256 experts 중 8 routed + 1 shared)지만, 공식 문서는 Qwen3 계열 function calling이 template/prompting에 크게 의존하고 별도 `qwen3_coder` tool parser와 `qwen3` reasoning parser를 권장한다고 설명한다. 따라서 큰 단일 agent보다 작은 agent별 prompt/tool/context budget을 설계하는 편이 안정성, latency, memory 사용량 측면에서 유리하다. [Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B), [Qwen function calling docs](https://qwen.readthedocs.io/en/stable/framework/function_call.html)
5. 2025년 하반기 이후 harness primitive는 prompt와 tool calling을 넘어 `Skills`, repository instruction file, subagent, hook, compaction/memory, sandbox, prompt cache까지 넓어졌다. 이들은 모두 "큰 prompt 하나"가 아니라 "작고 재사용 가능한 capability packaging + deterministic runtime control" 방향을 가리킨다.

결론적으로 v1 권고는 외부 A2A network가 아니라 내부 manager-specialist runtime이다. MCP/capability 계약은 tool boundary로 재사용하고, A2A는 장기적인 조직 간 또는 서비스 간 agent interoperability 후보로 두는 것이 현실적이다.

## Terminology

| 용어 | 의미 | 설계상 역할 |
|---|---|---|
| Agentic engineering | LLM이 tool, memory, retrieval, feedback을 사용해 여러 단계의 업무를 수행하도록 시스템을 설계하는 분야 | 모델 호출보다 runtime, state, tool, guardrail 설계가 중요하다 |
| Agent | 환경 feedback과 tool result를 보고 다음 행동을 선택하는 실행 단위 | manager 또는 specialist로 나눌 수 있다 |
| Workflow | 코드가 정한 경로로 LLM/tool을 조합하는 구조 | 예측 가능한 업무에 적합하다 |
| Harness / scaffold | agent loop, tool routing, state persistence, sandbox, checkpoint, trace, eval을 포함한 실행 껍질 | 모델의 능력을 실제 제품 성능으로 바꾸는 핵심 레이어다 |
| Context engineering | 필요한 정보만 적절한 시점에 context window로 넣는 설계 | "전부 주입"이 아니라 just-in-time retrieval과 reference 기반 접근을 선호한다 |
| Tool gateway | agent가 호출 가능한 tool 목록, schema, approval, ACL, audit를 통제하는 경계 | 보안과 품질의 핵심 통제점이다 |
| Memory | agent가 세션을 넘어 보존하는 정보 | global memory보다 domain/task/user scoped memory가 안전하다 |
| Orchestration | manager가 specialist를 선택하고 결과를 합성하는 흐름 | deterministic routing과 LLM routing을 혼합한다 |
| MCP | LLM app과 외부 tool/context/resource를 연결하는 표준 프로토콜 | tool/context boundary 표준화에 적합하다 |
| A2A | 독립 agent 간 discovery, delegation, task exchange를 위한 상호운용 프로토콜 | 내부 단일 런타임보다 조직/벤더/서비스 경계를 넘을 때 가치가 커진다 |
| Skill / capability package | 특정 업무 수행법, 참고 자료, 스크립트, template를 묶은 on-demand package | specialist descriptor를 filesystem/package 단위로 구현하는 패턴이다 |
| Durable instruction layer | 매 세션 자동 로드되는 project/repository instruction file | team convention과 invariant를 prompt 밖에서 version control한다 |
| Hook | tool call, compaction, stop 같은 lifecycle event에 붙는 deterministic handler | prompt-only governance를 보완하는 정책/검증 경계다 |
| Compaction | 긴 대화를 요약해 active context를 줄이는 메커니즘 | long-running agent의 context overflow를 다룬다 |
| Sandbox | agent가 code/browser/shell을 실행하는 격리 runtime | credential, filesystem, network, process 권한을 분리한다 |

## 2025-2026 Technical Trends

### 1. "큰 agent 하나"보다 composable workflow에서 시작

Anthropic의 agent 설계 가이드는 agentic system을 workflow와 agent로 구분한다. workflow는 코드가 경로를 정하고, agent는 LLM이 tool 사용과 절차를 동적으로 선택한다. 실무적으로는 가장 단순한 해결책에서 시작하고, 예측 불가능한 단계 수나 동적 의사결정이 필요할 때만 agent autonomy를 높이는 접근이 권장된다. [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

이 흐름은 로컬 LLM 환경에 특히 중요하다. 로컬 모델은 frontier hosted model보다 tool selection, long-horizon planning, noisy context 처리에서 여유가 적다. 따라서 모든 tool과 모든 business context를 한 prompt에 넣는 방식은 latency와 품질을 동시에 악화시킬 수 있다.

### 2. Multi-agent는 breadth-first, 독립 병렬 작업에 강하다

Anthropic의 multi-agent research system은 lead agent가 전략을 세우고 여러 subagent가 독립적으로 검색/조사를 수행하는 orchestrator-worker 구조다. 내부 평가에서 single-agent 대비 큰 성능 향상을 보였지만, 일반 chat보다 token 사용량이 훨씬 크고 coordination failure가 생길 수 있다고 설명한다. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

따라서 multi-agent는 기본값이 아니라 선택지다. 다음 조건이 맞을 때 효과가 크다.

- 독립적인 하위 문제로 분해할 수 있다.
- 각 하위 문제가 다른 tool/context를 필요로 한다.
- 결과 합성이 가능하고, 중간 결과를 artifact로 남길 수 있다.
- 사용자가 추가 latency나 token 비용을 감수할 만큼 업무 가치가 크다.

반대로 요청이 단일 도메인의 짧은 read/write 작업이면 specialist agent 하나 또는 deterministic workflow가 더 적합하다.

### 3. Harness engineering은 prompt engineering보다 넓다

최근 Anthropic engineering 글들은 harness를 단순 prompt wrapper가 아니라 agent 실행 시스템 전체로 다룬다. long-running agent에는 initializer, progress artifact, checkpoint, clean handoff, eval, trace가 필요하다. [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

2026년 글에서는 harness가 모델의 약점을 보완하기 위해 만든 가정이 시간이 지나면 낡을 수 있으므로, session, harness, sandbox를 안정적인 인터페이스로 분리해야 한다고 설명한다. [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)

즉 harness engineering의 핵심은 다음이다.

- agent loop를 어떻게 멈추고 재개할 것인가
- 어떤 tool result를 context에 넣고 어떤 것은 artifact/reference로 남길 것인가
- 실패한 tool call을 모델에게 어떻게 돌려줄 것인가
- agent의 전체 trajectory를 어떻게 trace/eval할 것인가
- sandbox와 credential을 어떻게 분리할 것인가

### 4. Context engineering은 "전부 미리 넣기"에서 "필요할 때 가져오기"로 이동

Anthropic의 context engineering 글은 context를 모두 upfront로 넣는 방식보다 lightweight identifier를 유지하고 필요할 때 tool로 불러오는 just-in-time 접근을 강조한다. [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

로컬 LLM에서는 이 원칙이 더 강하다. context window가 커도 KV cache memory, prefill latency, tool selection noise가 증가한다. 따라서 agent별 context budget을 나누고, 원문 대신 resource id, page id, meeting id, query handle 같은 reference를 먼저 넘기는 설계가 유리하다.

### 5. Skills / capability packaging은 progressive disclosure의 실전 구현이다

Anthropic Agent Skills는 2025년 후반 이후 harness engineering에서 가장 구체적인 capability packaging 패턴으로 볼 수 있다. Skill은 directory 안의 `SKILL.md`, reference file, script, template로 구성되고, Claude는 startup 때 skill name/description(약 100 token)만 읽은 뒤 task가 맞을 때 `SKILL.md` 본문(5k token 미만)을 로드하고 추가 파일과 script는 필요할 때만 읽거나 실행한다. 공식 문서는 이를 progressive disclosure로 부르며, 번들된 파일은 호출되기 전까지 context window를 소비하지 않는다. [Anthropic, Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills), [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview), [Claude Code Skills](https://code.claude.com/docs/en/skills)

이 패턴은 specialist agent descriptor와 직접 연결된다.

- `description`은 manager/router가 어떤 specialist를 고를지 판단하는 routing metadata다.
- `SKILL.md`는 해당 capability의 compact operating manual이다.
- `references/`, `scripts/`, `templates/`는 active context에 항상 넣지 않는 deferred context다.
- focused skill을 여러 개 두는 방식은 focused specialist agent를 여러 개 두는 방식과 같은 tradeoff를 가진다.

따라서 작은 domain agent를 설계할 때 prompt를 먼저 쓰기보다 "이 agent의 skill package가 무엇인가"를 먼저 정의하는 것이 좋다.

### 6. Repository instruction file은 durable instruction layer가 됐다

`AGENTS.md`는 coding agent가 repository별 setup, test, style, architecture constraint를 예측 가능한 위치에서 읽도록 하는 open format이다. 공식 사이트는 이를 "agent를 위한 README"로 설명하고, 60k개 이상의 open-source project가 사용한다고 밝힌다. [AGENTS.md](https://agents.md/)

이 계층은 `SKILL.md`와 역할이 다르다.

- `AGENTS.md`: 매 세션 자동 로드되는 stable project invariant와 workflow.
- `CLAUDE.md`, `.cursor/rules`, Copilot instruction 등: 특정 tool/runtime용 instruction layer.
- `SKILL.md`: 특정 task가 감지될 때만 로드되는 on-demand capability package.

Agentic product에도 같은 구분이 필요하다. 모든 domain convention을 manager prompt에 넣는 대신, workspace/project invariant는 durable instruction layer에 두고, domain/task 지식은 skill/capability package로 분리해야 한다.

### 7. Subagents는 manager-specialist 모델의 직접 구현 사례다

Claude Code subagents 문서는 subagent를 별도 context window, custom system prompt, specific tool access, independent permissions를 가진 specialized assistant로 정의한다. 또한 verbose search/log/test output을 main conversation에 넣지 않고 subagent context 안에서 처리한 뒤 summary만 반환하는 것을 핵심 사용 사례로 든다. [Claude Code subagents](https://code.claude.com/docs/en/sub-agents), [How and when to use subagents in Claude Code](https://claude.com/blog/subagents-in-claude-code)

이는 이 리포트의 manager-specialist 구조와 거의 같은 실전 reference다.

- main conversation = manager/synthesis context
- subagent = specialist context
- tool allowlist / disallowed tools = narrow tool surface
- model field = task별 비용/latency 최적화
- memory scope = specialist별 scoped memory
- background subagent = 병렬 side task
- isolation/worktree = sandboxed implementation path

따라서 "작은 업무/도메인별 agent를 계속 만들어내는 구조"는 더 이상 이론적 제안이 아니라, production coding harness에서 이미 표준 기능으로 자리 잡은 패턴이다.

### 8. Hooks, compaction, memory는 prompt-only harness를 대체한다

Claude Code hook 모델은 `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`, `PostCompact`, `InstructionsLoaded`, `PermissionRequest` 같은 다수의 lifecycle event에 deterministic command를 붙인다. 특히 `PreToolUse`는 위험한 tool call을 실행 전에 차단하고, `PostToolUse`는 결과 검증·logging에 쓸 수 있으며, `PreCompact`/`PostCompact`는 manual/auto matcher로 context compaction 전후 상태를 다룬다. [Claude Code hooks](https://code.claude.com/docs/en/hooks)

Claude memory tool 문서는 long-running workflow에서 compaction과 memory tool을 함께 쓰는 패턴을 설명한다. Compaction은 오래된 conversation context를 server-side summary로 줄이고, memory는 compaction boundary를 넘어 반드시 보존해야 할 정보를 별도 파일로 유지한다. [Claude memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

이 흐름은 세 가지 교훈을 준다.

- "정책을 prompt에 써두기"보다 hook/gateway에서 deterministic하게 검사해야 한다.
- long-running agent는 session log, compact summary, memory artifact를 별도 object로 다뤄야 한다.
- compaction은 무료가 아니다. 요약 손실, stale memory, project invariant drift를 eval해야 한다.

### 9. Tool design 자체가 agent 품질을 좌우한다

Tool description과 schema는 agent context 안에 들어가므로, 모델 행동을 직접 steering한다. Anthropic은 tool을 명확하고 의도적으로 정의하고, argument를 실수하기 어렵게 설계하며, eval-driven으로 개선하라고 권고한다. [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

SWE-agent 논문도 같은 방향을 보인다. 고정된 모델이라도 agent-computer interface를 agent 친화적으로 설계하면 software engineering 성능이 크게 달라진다. [SWE-agent ACI](https://arxiv.org/abs/2405.15793)

2025-2026년 coding benchmark도 점점 "순수 모델"보다 "모델 + scaffold + tool interface + sandbox"의 성능을 함께 본다. Qwen3.6-35B-A3B model card 역시 SWE-bench 계열 결과를 internal agent scaffold, bash/file-edit tools, long context window 같은 harness 조건과 함께 제시한다. [Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)

따라서 agent 성능 개선의 우선순위는 보통 다음 순서가 된다.

1. tool을 줄이고 이름/description/args를 명확히 한다.
2. tool result를 작고 구조화한다.
3. agent별 목적과 금지 범위를 좁힌다.
4. 그래도 부족하면 prompt, routing, model, fine-tuning을 검토한다.

### 10. MCP와 A2A는 역할이 다르다

MCP는 LLM application이 data source, tool, workflow에 연결되는 표준이다. 공식 specification은 resource, prompt, tool, progress, cancellation, logging, authorization 같은 기능을 정의한다. [MCP intro](https://modelcontextprotocol.io/docs/getting-started/intro), [MCP 2025-06-18 specification](https://modelcontextprotocol.io/specification/2025-06-18)

A2A는 독립 agent system 간 communication과 delegation을 표준화하려는 흐름이다. Google은 2025년 A2A를 Linux Foundation으로 이전했고, 2026년에는 A2A v1.0과 ecosystem 성장을 발표했다. Google은 MCP가 internal tool integration에 가깝고, A2A가 autonomous entity 간 external coordination에 가깝다고 설명한다. [A2A donation](https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/), [A2A anniversary/status](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html)

내부 단일 제품 안에서 PMS, Meeting, Docs, Planner specialist를 나누는 수준이라면 A2A부터 도입할 필요는 낮다. 먼저 in-process manager-specialist runtime과 MCP-shaped tool gateway를 안정화하고, 다른 시스템의 agent와 상호운용해야 할 때 A2A를 검토하는 순서가 적절하다.

### 11. Framework trend는 "orchestration + state + observability"

주요 framework들이 다르게 보이지만, 공통 방향은 4가지 패턴으로 묶인다.

1. **Application-owned orchestration SDK**: handoff, guardrail, tracing, session, tool approval을 일급 개념으로 두고 호스팅 프레임워크가 아니라 application이 runtime을 소유한다. OpenAI Agents SDK, Mastra, Vercel AI SDK 5가 같은 형태다. [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents), [OpenAI Agents Python SDK](https://openai.github.io/openai-agents-python/), [Mastra](https://mastra.ai/docs), [Vercel AI SDK 5](https://vercel.com/blog/ai-sdk-5)
2. **Workflow graph / multi-agent hierarchy**: parent-child agent, sequential/parallel/loop, agent-as-tool, controllable graph를 제공한다. Google ADK, LangGraph, AutoGen v0.4가 대표적이다. [Google ADK multi-agent systems](https://adk.dev/agents/multi-agents/), [LangGraph](https://langchain-ai.github.io/langgraphjs/reference/modules/langgraph.html), [Microsoft AutoGen v0.4](https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/)
3. **Type-safe / structured agent**: dependency injection과 structured result를 production discipline으로 끌어올린다. PydanticAI가 대표적이다. [PydanticAI](https://pydantic.dev/docs/ai/overview/)
4. **Eval-first workflow primitive**: trace, grader, dataset, eval run을 framework의 1급 객체로 둔다. OpenAI agent evals가 대표 사례다. [OpenAI agent evals](https://developers.openai.com/api/docs/guides/agent-evals)

공통점은 framework 이름이 아니라 runtime property다. 제품에 필요한 것은 "어떤 framework를 쓸 것인가"보다 "agent가 state, trace, tool, approval, failure를 어떻게 다룰 것인가"다.

### 12. Ambient / event-driven agent가 chat-triggered agent를 보완한다

LangChain은 ambient agent를 사용자가 chat을 시작해야만 동작하는 agent가 아니라 event stream을 듣고 필요할 때 notify, question, review를 요청하는 agent로 정의한다. 예시는 email assistant지만, 패턴 자체는 cron, webhook, inbox, queue, calendar, meeting transcript arrival 같은 trigger에 적용된다. [Introducing ambient agents](https://www.blog.langchain.com/introducing-ambient-agents)

업무 도메인 agent에서는 ambient trigger가 특히 중요하다.

- Meeting: 녹취 업로드 후 action item/decision extraction 자동 실행
- PMS: stale issue, blocked issue, due date risk 감지
- Planner: 일정 충돌, follow-up 필요 회의 감지
- Docs/RAG: 새 문서 ingest 후 source quality check

Ambient agent는 완전 자율 실행이 아니라 "notify/question/review"를 명확히 나누는 human-in-the-loop harness와 함께 설계해야 한다.

## Local Qwen3.6-35B-A3B Implications

본 프로젝트는 NVIDIA DGX Spark (GB10) 위 vLLM provider로 `Qwen/Qwen3.6-35B-A3B-FP8`를 운영한다. 이는 dense 모델이 아니라 MoE다 — 총 35B 파라미터 중 token당 활성은 약 3B(256 experts 중 8 routed + 1 shared)다. 운영 함의는 dense 모델과 다른 지점이 있어 별도로 정리한다.

### 1. 긴 context는 필요조건이지 충분조건이 아니다

Qwen3.6-35B-A3B model card는 기본 context length 262,144 token, YaRN 확장 시 약 1M token을 제시하고, OOM이 나면 context window를 줄이되 thinking capability 보존을 위해 충분히 큰 context를 유지하라고 안내한다. 또한 vLLM/SGLang 같은 serving engine과 Qwen용 reasoning/tool parser(`qwen3` reasoning parser, `qwen3_coder` tool parser) 사용을 예시로 든다. [Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)

하지만 긴 context는 function calling 안정성을 자동으로 보장하지 않는다. LongFuncEval은 다음 세 조건에서 tool calling 성능 저하를 관찰했다. [LongFuncEval](https://arxiv.org/abs/2505.10570)

- tool catalog가 커질 때
- tool response가 길어질 때
- multi-turn conversation이 길어질 때

이 결과는 로컬 agent 설계에 직접적인 의미가 있다. Qwen3.6-35B-A3B에 100개 tool과 긴 회의록, 문서 원문, PMS issue history를 한꺼번에 넣는 방식은 "긴 context를 쓴다"가 아니라 "decision surface를 오염시킨다"에 가까울 수 있다. MoE 모델에서는 추가 변수가 하나 더 있다 — token마다 활성화되는 expert 조합이 달라지므로, tool selection이 길어질수록 routing 변동성이 커지는 경향이 있다.

### 2. Qwen tool calling은 공식 template/parser를 기준으로 잡아야 한다

Qwen function calling 문서는 Qwen3의 function calling이 prompt/template 기반이며 Hermes-style tool use를 권장한다고 설명한다. reasoning model에서는 thought section 안에 stopword가 나올 수 있으므로 ReAct stopword 방식 tool template을 권장하지 않는다. [Qwen function calling docs](https://qwen.readthedocs.io/en/stable/framework/function_call.html)

Qwen key concepts 문서는 Qwen3가 tool calling/function calling을 지원하고, tool call을 XML tag 안 JSON object로 표현하는 template를 설명한다. 또한 parallel tool calling과 multi-step tool calling을 지원한다고 정리한다. [Qwen key concepts](https://qwen.readthedocs.io/en/latest/getting_started/concepts.html)

따라서 로컬 Qwen agent runtime은 다음 원칙을 가져야 한다.

- vLLM/SGLang 사용 시 Qwen 공식 parser 설정을 우선한다.
- OpenAI-compatible API라 하더라도 실제 tool call delta/finish_reason/parser behavior를 별도 검증한다.
- thinking mode와 non-thinking mode를 업무별로 나눈다.
- ReAct text parsing을 기본값으로 두지 않는다.
- malformed tool call을 단순 실패로 끝내지 말고 parser fallback, retry limit, trace를 남긴다.

### 3. 작은 specialist agent가 로컬 효율을 높이는 이유

작은 agent 분리는 로컬 LLM에서 다음 이점을 준다.

| 항목 | 단일 거대 agent | manager + specialist |
|---|---|---|
| Tool catalog | 모든 tool을 한 번에 노출하기 쉽다 | agent별 tool을 좁힐 수 있다 |
| Context | 여러 도메인 정보가 섞인다 | domain/task context만 넣는다 |
| Memory | global memory poisoning 위험이 크다 | scoped memory로 격리한다 |
| Latency | prefill과 tool selection 비용이 커진다 | 짧은 prompt와 작은 schema로 줄인다 |
| 변경 영향도 | 한 prompt/tool 변경이 전체 행동에 영향 | domain agent 단위로 영향이 제한된다 |
| 평가 | 실패 원인 분리가 어렵다 | routing/tool/restraint/eval을 agent별로 측정한다 |
| MoE expert routing | 도메인이 섞이면 token마다 활성 expert 조합이 흔들리기 쉽다 | domain별 stable prompt/tool prefix로 활성 expert 분포가 안정화된다 |
| 메모리 사용 | 35B 전체 weight가 하나의 거대 prompt에 묶인다 | 활성 3B의 장점을 살리면서 prefix cache hit이 늘어난다 |

이는 사용자가 제시한 가설과 일치한다. 업무 변화가 잦은 환경에서는 단일 agent를 계속 수정하는 방식보다 domain/task별 agent descriptor를 추가/교체하는 방식이 유지보수성이 높다. 특히 MoE에서는 specialist 단위 prefix 안정화가 expert routing 안정성과 prefix cache hit rate에 동시에 기여한다.

### 4. Code execution과 artifact reference는 token 절약 수단이다

Anthropic의 "Code execution with MCP" 글은 tool definition과 tool result가 context를 많이 소비하는 문제를 지적하고, agent가 code execution 환경에서 tool result를 필터링/가공한 뒤 필요한 요약만 context로 반환하는 방식을 제안한다. [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)

로컬 환경에서는 이 패턴을 완전한 code sandbox로 바로 도입하지 않더라도, 다음 방식으로 적용할 수 있다.

- tool result는 원문 전체가 아니라 요약, id list, top-k preview, artifact path/reference로 반환한다.
- specialist agent output은 manager에게 전체 text로 복사하지 말고 artifact id와 short summary를 넘긴다.
- 대량 데이터 join/filter는 LLM context가 아니라 application service나 deterministic tool이 수행한다.

### 5. Prompt / prefix caching은 specialist 분리의 성능 근거다

로컬 serving에서는 static prefix 재사용이 latency와 throughput에 직접 영향을 준다. vLLM의 Automatic Prefix Caching은 `enable_prefix_caching=True`로 같은 prefix의 KV cache를 재사용하고, SGLang은 RadixAttention/HiCache 계열 prefix caching 최적화를 제공한다. Qwen 문서도 Qwen deployment에 vLLM/SGLang 사용을 권장한다. [vLLM Automatic Prefix Caching](https://docs.vllm.ai/en/latest/design/prefix_caching/), [SGLang HiCache design](https://docs.sglang.io/docs/advanced_features/hicache_design), [Qwen vLLM deployment](https://qwen.readthedocs.io/en/stable/deployment/vllm.html)

Specialist agent 분리는 prompt cache hit rate를 높이는 데 유리하다.

- agent별 system prompt와 tool schema가 안정적인 prefix가 된다.
- manager가 모든 tool schema를 매번 싣지 않아도 된다.
- domain agent별 반복 workload가 같은 prefix를 공유한다.
- dynamic tool result와 user-specific context를 뒤쪽에 배치하기 쉬워진다.

따라서 로컬 Qwen 운영에서는 "agent 수가 늘면 prompt가 복잡해진다"보다 "agent별 stable prefix를 만들어 cache-friendly workload로 나눈다"는 관점이 중요하다.

## Deployment Notes — DGX Spark (GB10)

> 본 프로젝트의 메인 운영 장비는 **NVIDIA DGX Spark (GB10)**다. 기본 운영 모델은 **Qwen3.6-35B-A3B**로 고정한다. 개발·검증·운영 모두 DGX Spark + vLLM + Qwen3.6-35B-A3B 단일 스택을 가정하며, 다른 hardware/runtime 가정은 본 보고서 범위 밖이다. 이 섹션은 NVIDIA 공식 문서/블로그와 NVIDIA Developer Forum, 커뮤니티 실측을 근거 등급을 나눠 정리한다.

### 1. 하드웨어 현실과 한도

- **GB10 Grace Blackwell Superchip**, 1 petaFLOP AI, 128GB coherent unified LPDDR5x.
- **메모리 대역폭 273 GB/s**가 실질적 병목이다. 계산이 아니라 대역폭이 한도를 결정한다.
- 단일 노드 inference 기준: NVIDIA 공식 문서는 최대 200B 모델 지원을 제시하고, NVIDIA DGX Spark agent workload 블로그는 1-node를 low-latency large-context inference와 120B급 fine-tuning/agentic workload에 적합한 구간으로 둔다. 본 보고서의 기본 모델 Qwen3.6-35B-A3B는 이 한도 안에 충분히 들어온다.
- 단일 노드 fine-tune 권장: ~70B.
- 듀얼 QSFP Ethernet 200 Gb/s aggregate으로 2-노드 클러스터 → 256GB / ~400B inference.

[NVIDIA DGX Spark Hardware Overview](https://docs.nvidia.com/dgx/dgx-spark/hardware.html), [LMSYS DGX Spark in-depth review](https://www.lmsys.org/blog/2025-10-13-nvidia-dgx-spark/)

### 2. Qwen3.6-35B-A3B on Spark 성능 신호

아래 값은 공식 NVIDIA 제품 스펙이 아니라 2026-04 기준 forum/community 측정이다. Qwen3.6-35B-A3B 단일 Spark 행은 기본 모델 운영 판단에 직접 참고하고, Qwen3.5/2-node 행은 확장 경로의 analogue로만 취급한다.

| 범주 | 스택 | 양자화 | prefill (tok/s) | decode (tok/s) | 비고 |
|---|---|---|---|---|---|
| Qwen3.6 단일 Spark | vLLM (NVIDIA forum, "serapis") | FP8 | 5,689–8,351 (pp2048 variants) | 75–76 (tg128) | `llama-benchy`, latency mode API |
| Qwen3.6 단일 Spark | vLLM (NVIDIA forum, "cosinus") | FP8 | 4,037–6,212 | 52+ (tg32) | ToolCall-15 success 97% |
| Qwen3.6 단일 Spark | LM Studio (Substack 사례) | Q4_K_M GGUF (~22GB) | — | ~68 | LMStudio + Claude Code 환경, 실측 |
| Qwen3.5 analogue / 2-node | 2x DGX Spark, TP=2 | Marlin FP8 | — | 495 @ concurrency 32 | Qwen3.5-35B-A3B-FP8, 확장 경로 참고용 |

NVIDIA 공식 agent workload 측정에서는 Qwen3.6-35B-A3B가 아니라 Qwen3 Coder Next FP8/vLLM 기준으로, 32K input / 1K output 작업 4개를 동시에 처리할 때 단일 작업 대비 2.6x 시간만 필요하다고 보고한다. 이는 "여러 specialist가 동시에 움직이는 local multi-agent workload가 Spark에서 sub-linear하게 확장될 수 있다"는 구조적 근거로만 사용한다. [NVIDIA Forum: Qwen3.6-35B-A3B (and FP8) has landed](https://forums.developer.nvidia.com/t/qwen-qwen3-6-35b-a3b-and-fp8-has-landed/366822), [NVIDIA Blog: Scaling Autonomous AI Agents and Workloads with NVIDIA DGX Spark](https://developer.nvidia.com/blog/scaling-autonomous-ai-agents-and-workloads-with-nvidia-dgx-spark/)

### 3. Qwen3.6-35B-A3B vLLM serving starting profile

Qwen 공식 model card가 직접 뒷받침하는 부분은 `vllm>=0.19.0`, `qwen3` reasoning parser, `qwen3_coder` tool parser, `language-model-only` 옵션이다. 나머지 DGX Spark/GB10 세부값은 2026-04 기준 커뮤니티 검증 starting profile이며, production baseline으로 고정하기 전에 동일 hardware/driver/vLLM build에서 재측정한다.

```bash
docker run -d --gpus all --ipc host --shm-size 64gb \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:cu130-nightly \
  Qwen/Qwen3.6-35B-A3B-FP8 \
    --max-model-len 65536 \
    --gpu-memory-utilization 0.80 \
    --kv-cache-dtype fp8 \
    --attention-backend flashinfer \
    --load-format fastsafetensors \
    --enable-prefix-caching \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --language-model-only
```

핵심 근거와 근거 등급:

- **공식 Qwen 근거**: `--tool-call-parser qwen3_coder`, `--reasoning-parser qwen3`, `--enable-auto-tool-choice`를 명시한다.
- **공식 Qwen 근거**: `--language-model-only`는 vision encoder와 multimodal profiling을 건너뛰어 KV cache 여유를 확보하는 옵션이다.
- **DGX Spark community 근거**: `max-model-len`을 처음부터 262K로 잡지 않는다. KV cache는 load time에 사전 할당되므로 32K~64K로 시작하고, 필요한 specialist만 별도 instance로 키운다.
- **DGX Spark community 근거**: `gpu-memory-utilization=0.80`은 장기 실행 OOM을 피하기 위한 보수적 시작점이다. 환경별로 0.70/0.80/0.90을 나눠 stress test한다.
- **DGX Spark community 근거**: `vllm/vllm-openai:cu130-nightly`, `flashinfer`, `fastsafetensors`는 GB10/SM121와 Qwen3.6 지원이 빠르게 변하는 구간의 working profile이다. vLLM 정식 릴리스가 따라오면 pinned stable image로 대체한다.
- **DGX Spark community 근거**: MTP speculative decoding은 일부 forum 측정에서 성능 저하가 보고되어 starting profile에서는 끈다. 공식 Qwen card는 MTP 설정도 제시하므로, latency/quality 회귀 테스트 뒤 별도 instance에서 켠다.

[adadrag/qwen3.5-dgx-spark vLLM 가이드](https://github.com/adadrag/qwen3.5-dgx-spark)는 Qwen3.5 기준 porting reference다. Qwen3.6-35B-A3B 기본 운영에는 parser, context, tool-call, long-running loop를 별도 회귀 테스트로 재검증한다.

### 4. Agent harness 관점의 운영 함정 (커뮤니티 실측)

LMStudio 위에 Claude Code를 붙여 Qwen3.6-35B-A3B를 운영한 [Substack 사례](https://internate.substack.com/p/running-claude-code-on-a-dgx-spark)에서 보고된 실제 함정은 다음과 같다.

1. **Thinking을 끄지 마라.** Qwen tool calling이 `<think>` scaffold와 함께 학습되어, thinking을 비활성화하면 XML 태그가 절단되어 tool call이 malformed로 나온다. 속도(68 tok/s)는 빠르지만 agentic loop가 깨진다.
2. **Thinking budget이 부족하면 tool loop가 발생한다.** `MAX_THINKING_TOKENS=8192`가 안전한 baseline. 1024 같은 값은 같은 reasoning을 무한 반복하다 종료.
3. **MCP server는 per-project로 좁혀라.** global MCP 등록 시 baseline context 101k → per-project로 좁히면 27k (75% 감소). 이는 본 보고서의 "agent별 tool surface 좁히기" 원칙의 직접 증거다.
4. **Claude Code 환경변수**: `CLAUDE_CODE_ATTRIBUTION_HEADER=0` (KV prefix cache 보존), `DISABLE_NON_ESSENTIAL_MODEL_CALLS=1` (불필요 roundtrip 차단).
5. **File-based checklist가 compaction을 살아남는다.** Multi-step task에서 plan을 conversation에 두지 말고 파일로 둘 것.
6. **OpenAI-compatible API 경로에서 thinking-only 응답 이슈** 보고가 별도로 존재 — content가 비고 reasoning_content만 오는 케이스. parser/adapter 단에서 별도 검증 필요.

### 5. 본 manager-specialist 설계와의 정합성

DGX Spark 단일 노드 운영은 본 보고서의 권고 방향을 거의 모든 축에서 강화한다.

| 보고서 권고 | DGX Spark 실측이 뒷받침하는 근거 |
|---|---|
| Specialist 분리 + narrow tool surface | 273 GB/s 대역폭 한도와 KV cache load-time 사전 할당 → 큰 prompt prefill이 곧 시스템 한도 소진 |
| Agent별 prefix 안정화 | `--enable-prefix-caching`이 실측에서 가장 확실한 throughput 개선원 |
| Agent별 context budget 분리 | KV cache 사전 할당 특성상 specialist마다 다른 `max-model-len`을 가진 별도 vLLM instance 운영이 자연스럽다 (예: routing 8K, draft 32K, RAG 64K) |
| Thinking/non-thinking specialist 구분 | tool calling이 thinking에 의존하므로 routing(non-thinking, fast) ↔ write/draft(thinking, accurate) 분리가 정당화됨 |
| Tool gateway / hooks의 deterministic 정책 | malformed tool call·thinking budget 이슈가 prompt-only 보호로는 잡히지 않음 |
| Approval gate + verifier | tool loop·repetition은 비용/blast radius가 크므로 외부 send/write 경로에 verifier 권고가 더 강해짐 |

### 6. 확장 경로

- **2-노드 클러스터**: Qwen3.5-35B-A3B-FP8 analogue에서 Marlin FP8 기준 495 tok/s aggregate (c=32) 사례가 있다. Qwen3.6-35B-A3B 기본 운영에서는 같은 수치를 보장하지 말고, manager 노드 ↔ specialist 노드 분리 또는 dense 모델 + MoE 모델 hetero 운영의 헤드룸으로만 본다.
- **모델 escalation**: Qwen3.5-122B-A10B NVFP4 양자화가 단일 Spark에 적재된 community 사례가 있다 (234GB → 75.6GB). 이는 "큰 critic/synthesis 모델을 단일 Spark에 올릴 가능성"을 보여주는 analogue일 뿐이며, Qwen3.6-35B-A3B 기본 운영과 별도 검증 대상이다.
- **vLLM build/parser drift**: Spark 운영 자체가 단일 스택이지만, vLLM nightly 이미지·CUDA build·`qwen3` reasoning parser·`qwen3_coder` tool parser 조합이 빠르게 바뀐다. parser/finish_reason/tool delta 회귀 테스트를 별도 contract로 고정해, image/parser 업그레이드가 silently agent loop를 깨뜨리지 않게 한다 ([`apps/api/src/aidoo_api/core/llm_adapters.py`](apps/api/src/aidoo_api/core/llm_adapters.py)에 vLLM adapter contract를 유지).

## Small Domain Agent Design Method

### 1. Agent를 domain agent와 task agent로 나눈다

Domain agent는 업무 영역을 기준으로 한다.

- PMS agent: issue search, issue detail, task/list/status context, issue draft/update proposal
- Meeting agent: meeting search, transcript summary, action/decision extraction, follow-up schedule draft
- Docs agent: document/page search, read, summarize, draft page
- Planner agent: event lookup, availability, schedule proposal
- RAG agent: cross-domain grounded search, source listing, citation-oriented synthesis

Task agent는 반복되는 작업 형태를 기준으로 한다.

- Search agent: 어떤 source에서 무엇을 찾아야 하는지 결정
- Summarize agent: 긴 text를 목적별로 압축
- Extract agent: action item, decision, owner, due date 등 구조화
- Draft agent: 문서, 메일, 회의 agenda, issue body 초안 작성
- Validate agent: 사용자 요청 충족 여부, tool result 근거 여부 확인
- Verifier / critic agent: 별도 관점에서 grounding, 정책 위반, 누락된 요구사항을 검증
- Approval preview agent: write action 전 사용자에게 보여줄 변경 요약 생성

Domain agent와 task agent는 반드시 별도 프로세스일 필요가 없다. v1에서는 동일 runtime 안에서 agent descriptor와 tool scope만 분리해도 충분하다.

### 2. 각 agent descriptor가 가져야 할 필드

작은 specialist agent는 code class보다 descriptor로 먼저 정의하는 편이 좋다. 최소 필드는 다음이다.

| 필드 | 설명 |
|---|---|
| `agent_id` | 안정적인 내부 식별자 |
| `owner_domain` | PMS, Meeting, Docs, Planner, RAG 등 |
| `purpose` | 이 agent가 해결하는 업무 |
| `non_goals` | 하지 말아야 할 일 |
| `tool_allowlist` | 호출 가능한 tool 목록 |
| `context_sources` | 허용된 retrieval/source 종류 |
| `memory_scope` | none, conversation, workspace-domain, user-domain 등 |
| `input_contract` | manager가 넘겨야 하는 구조 |
| `output_contract` | manager에게 반환하는 구조 |
| `failure_policy` | retry, ask user, return partial, escalate 등 |
| `budget` | max turns, max tool calls, max context tokens |
| `eval_cases` | routing/tool/restraint/regression 평가 케이스 |

이 descriptor는 agent prompt보다 중요하다. prompt는 descriptor에서 파생될 수 있어야 하고, tool gateway와 eval harness도 같은 descriptor를 기준으로 동작해야 한다.

### 3. Manager는 deterministic routing을 우선한다

Manager agent가 모든 routing을 LLM 판단에 맡기면, 로컬 모델에서 불필요한 latency와 오판이 늘어난다. 원칙은 "deterministic 신호가 있는 한 LLM router를 호출하지 않는다"이고, 결정 알고리즘은 다음 트리로 표현된다.

```
request
  -> app/resource scope가 명확한가?
      yes -> 해당 domain specialist
      no
  -> deterministic rule/entity가 agent 후보를 1개로 줄이는가?
      yes -> 해당 specialist
      no
  -> write/외부전송/권한변경이 포함되는가?
      yes -> draft/proposal specialist -> approval gate
      no
  -> multi-domain synthesis가 필요한가?
      yes -> 여러 specialist 호출 -> verifier -> manager synthesis
      no -> LLM router로 specialist 선택 또는 사용자에게 clarification
```

실제 요청 분류 예시는 다음과 같다.

| 사용자 요청 | Routing |
|---|---|
| "어제 회의 액션아이템 정리해줘" | Meeting Extract agent |
| "이 이슈 본문을 고객 공유용으로 정리해줘" | PMS read -> Draft agent |
| "다음 주 화요일 오후 가능한 시간 찾아줘" | Planner/Meeting availability agent |
| "이번 프로젝트 상황 보고서 만들어줘" | PMS + Meeting + Docs/RAG -> manager synthesis |

### 4. Verifier / critic-actor 패턴을 별도 단계로 둔다

Local model에서는 최종 답변 agent가 스스로의 hallucination과 grounding gap을 안정적으로 잡지 못할 수 있다. 따라서 중요한 산출물에는 별도 verifier agent를 둔다.

Verifier agent의 입력은 user request, specialist output, evidence refs, policy constraints다. 출력은 `pass/fail`, missing evidence, unsafe action, unsupported claim, required follow-up question 같은 구조화 결과여야 한다. Verifier는 write tool을 갖지 않고 read-only evidence 확인과 policy check만 수행한다.

적용 위치:

- manager synthesis 전 grounding 확인
- write approval preview 전 변경 범위 확인
- RAG answer의 citation coverage 확인
- Meeting/PMS 자동 추출 결과의 누락/중복 확인

Verifier는 모든 요청에 넣지 않는다. 비용이 큰 만큼 external send, write action, executive report, cross-domain summary처럼 실패 비용이 큰 경로에 우선 적용한다.

### 5. Tool surface는 agent별로 좁힌다

Tool 목록이 많으면 모델은 "무엇을 할지"보다 "어떤 tool을 고를지"에 context와 reasoning을 소비한다. 특히 로컬 모델은 유사한 tool name과 긴 schema에 취약할 수 있다.

권장 원칙은 다음이다.

- 한 specialist가 보는 tool은 가능한 3-8개 안쪽으로 유지한다.
- read/write tool을 같은 agent에 무조건 섞지 않는다.
- write tool은 proposal/preview/approval 단계와 실제 execute 단계를 분리한다.
- tool result는 long text보다 structured summary를 반환한다.
- 같은 기능의 tool이 많으면 domain-specific wrapper tool을 만든다.

### 6. Memory는 scoped memory가 기본이다

Global memory는 모든 agent의 행동에 영향을 줄 수 있어 memory poisoning과 stale behavior 위험이 크다. OWASP Agentic Top 10은 memory/context poisoning, insecure inter-agent communication, cascading failures를 agentic system의 주요 위험으로 다룬다. [OWASP Agentic Top 10](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)

따라서 memory scope는 다음 순서로 제한하는 것이 안전하다.

1. No memory: 단발 작업
2. Conversation memory: 현재 대화 안에서만 유지
3. Domain memory: 특정 workspace + domain 안에서만 유지
4. User-domain memory: 특정 user + workspace + domain 안에서 유지
5. Global memory: 기본 금지, 운영 정책과 검증이 있을 때만 허용

Memory write는 tool write와 같은 수준의 approval/audit 대상이 되어야 한다.

## Reference Architecture

### 1. Logical components

```
User
  -> Chat/API Surface
  -> Manager Agent / Deterministic Router
      -> Specialist Agent Runtime
          -> Tool Gateway (MCP-shaped)
          -> Context Broker
          -> Scoped Memory
          -> Artifact Store
          -> Hook / Policy Runtime
          -> Sandbox Runtime
  -> Final Synthesis
  -> Trace / Eval / Audit
```

### 2. Manager Agent

책임:

- 사용자 요청을 domain/task 후보로 분류한다.
- deterministic router 결과를 우선 사용한다.
- specialist agent에 넘길 input contract를 만든다.
- 여러 specialist 결과를 합성한다.
- 출처 부족, 권한 부족, 모호한 요청을 사용자에게 되묻는다.

비책임:

- 모든 domain tool을 직접 호출하지 않는다.
- 장기 memory를 직접 수정하지 않는다.
- write action을 approval 없이 실행하지 않는다.

### 3. Specialist Agents

책임:

- 좁은 목적에 맞는 tool만 사용한다.
- 자기 domain의 context와 memory만 본다.
- output contract에 맞춰 short summary, structured result, artifact reference를 반환한다.
- 실패하면 실패 유형을 명확히 반환한다.

권장 output shape:

```json
{
  "agent_id": "meeting.extract_actions",
  "status": "ok",
  "summary": "회의에서 액션아이템 4건을 찾았습니다.",
  "artifacts": [{"type": "table", "id": "artifact_123"}],
  "evidence_refs": ["meeting:abc", "transcript:line-range"],
  "needs_user_input": false,
  "warnings": []
}
```

### 4. Tool Gateway

Tool gateway는 agent가 실제 시스템에 접근하는 경계다. MCP-shaped schema를 쓰면 LLM-facing tool description과 execution contract를 분리할 수 있다.

필수 기능:

- tool discovery filtering
- read/write mode 구분
- approval_required metadata
- argument validation
- ACL / workspace isolation
- audit / trace event
- tool result projection
- hidden tool direct invoke 차단
- pre/post tool hook에 의한 deterministic policy check
- write/side-effect tool의 approval gate

### 5. Context Broker

Context Broker는 specialist agent가 필요한 정보를 가져오는 통로다.

원칙:

- 원문 bulk injection보다 search -> preview -> read-detail 순서를 사용한다.
- manager는 specialist에게 원문 전체보다 resource reference를 넘긴다.
- specialist output은 manager에게 full text보다 summary + artifact id를 넘긴다.
- 오래된 context는 session log에 남기고, LLM context에는 필요한 slice만 넣는다.
- `AGENTS.md` 같은 durable instruction은 stable prefix로 두고, skill/capability package는 필요할 때만 로드한다.

### 6. Session / Artifact Store

Long-running agent는 한 context window 안에서 끝나지 않을 수 있다. Anthropic의 managed agent 설계처럼 session log는 context window 밖의 durable object로 보는 편이 안전하다. [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)

권장 저장 대상:

- user request
- routing decision
- specialist invocation
- tool call / result
- approval request / resolution
- generated artifact
- final answer
- error / retry / cancellation
- compact summary
- memory read/write operation
- active skill/capability version

Compaction은 session store와 분리해서 다뤄야 한다. `compact_summary`는 다음 turn의 active context를 줄이는 데 유용하지만, 원본 trace를 대체하지 않는다. 중요한 결정, resource id, 승인 상태, pending task는 memory/artifact로 별도 보존해야 한다.

### 7. Sandbox Runtime Catalog

Agent가 code, browser, shell, file operation을 수행할 때는 sandbox가 별도 product surface가 된다. "격리한다"는 원칙만으로는 부족하고, 실행 시간, 네트워크, filesystem, credential, observability 요구에 맞춰 runtime을 골라야 한다.

| 옵션 | 적합한 경우 | 주의점 |
|---|---|---|
| E2B | Linux-like cloud sandbox, code interpreter, desktop/browser style agent runtime | 외부 cloud dependency와 data egress 정책 검토 필요 |
| Modal Sandboxes | 대량 병렬 code execution, Python/ML workload, ephemeral compute | product agent UX보다 infra/API 중심 |
| Daytona Sandboxes | long-running/persistent agent computer, filesystem/process/network 격리 | 운영 비용과 lifecycle 관리 필요 |
| AWS Bedrock AgentCore Code Interpreter / Browser | AWS enterprise boundary, VPC/PrivateLink/CloudWatch integration | AWS IAM 권한 모델과 agent credential 설계가 핵심 |
| Cloudflare Sandbox SDK / Containers | edge-adjacent TypeScript/Workers 기반 command/file/process execution | GA 초기 제품이므로 runtime 제한과 region/data policy 확인 필요 |

공통 요구사항은 같다.

- sandbox credential은 user credential과 분리한다.
- network egress allowlist를 둔다.
- filesystem은 workspace/job 단위로 격리한다.
- session replay와 resource metric을 남긴다.
- sandbox escape와 privilege escalation을 threat model에 포함한다.

### 8. Plan / spec-driven workflow

최근 coding agent harness는 "바로 실행"보다 planning phase를 명시적으로 둔다. Claude Code subagents 문서도 plan-mode용 subagent를 별도 built-in으로 두고, OpenAI/Codex 계열 문서도 research/plan/build 흐름과 sandbox/subagent/workflow 개념을 분리한다. [Claude Code subagents](https://code.claude.com/docs/en/sub-agents), [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents)

업무 agent에도 같은 패턴이 유효하다.

1. 요청을 해석하고 plan/proposal artifact를 만든다.
2. 사용자가 plan 또는 write preview를 승인한다.
3. specialist가 실행한다.
4. verifier가 evidence와 정책을 확인한다.
5. manager가 최종 응답과 trace link를 반환한다.

이 패턴은 approval fatigue를 줄인다. 모든 tool call마다 묻는 대신, 위험한 실행 경계 전에 "무엇을 할지"를 한 번에 보여주고 승인받을 수 있기 때문이다.

### 9. Eval / Trace Harness

Agent 평가는 단일 최종 답변만 보면 부족하다. Anthropic의 eval 글은 transcript/trajectory, final outcome, evaluation harness를 구분한다. [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

필수 평가 축:

- Routing accuracy: 올바른 specialist를 골랐는가
- Tool restraint: 필요 없을 때 tool을 호출하지 않았는가
- Tool choice: 호출한 tool이 맞는가
- Argument accuracy: tool argument가 정확한가
- Grounding: 답변이 tool result 범위 안에 있는가
- Stateful behavior: multi-turn state와 승인 상태가 깨지지 않는가
- Security: hidden tool, cross-workspace, memory poisoning, prompt injection에 안전한가
- Cost/latency: 단일 agent 대비 prefill, total tokens, TTFT가 개선되는가
- Compaction safety: compact 이후 핵심 invariant와 pending state가 유지되는가
- Cache efficiency: specialist 분리 후 prefix cache hit rate와 TTFT가 개선되는가

τ-bench와 ToolSandbox는 실제 tool/user interaction과 stateful tool execution을 평가해야 함을 보여준다. [τ-bench](https://arxiv.org/abs/2406.12045), [ToolSandbox](https://arxiv.org/abs/2408.04682)

## Risks / Anti-patterns

### 1. Agent proliferation

도메인 경계가 명확하지 않은 agent가 계속 늘면 manager routing과 eval이 어려워진다. agent 추가 기준은 "새 prompt"가 아니라 "새 목적, 새 tool surface, 새 eval suite가 필요한가"여야 한다.

### 2. Multi-agent by default

모든 요청을 multi-agent로 보내면 token, latency, trace complexity가 증가한다. 단순 read 요청은 deterministic workflow나 단일 specialist가 더 낫다.

### 3. Global memory poisoning

전역 memory는 한 번 오염되면 모든 agent에 영향을 줄 수 있다. memory는 scoped, typed, auditable해야 하며, 자동 write를 기본 허용하지 않는다.

### 4. Too many tools in one agent

긴 tool catalog는 local model에서 tool choice noise를 키운다. LongFuncEval과 커뮤니티 실험 모두 parser/tool surface 설계가 중요하다는 방향을 지지한다.

### 5. A2A premature adoption

내부 단일 제품 런타임에서 agent를 나누기 위해 A2A를 먼저 도입하면 protocol overhead가 커질 수 있다. A2A는 독립 시스템, 다른 조직, 다른 vendor agent와의 상호운용이 필요해질 때 검토한다.

### 6. Approval fatigue

모든 작업에 approval을 요구하면 사용자는 승인 내용을 제대로 보지 않게 된다. read tool, safe deterministic transform, draft-only action은 자동화하고, 실제 write/외부 전송/권한 변경만 명확한 preview와 함께 approval을 요구한다.

### 7. Prompt-only governance

보안과 정책을 prompt에만 맡기면 tool misuse와 prompt injection에 취약하다. tool gateway, ACL, sandbox, scoped credential, audit, rate limit 같은 deterministic control이 필요하다. Claude Code의 hook model처럼 tool 실행 전후와 compaction 전후에 deterministic handler를 붙일 수 있어야 한다.

### 8. Compaction loss

자동 compaction은 long-running agent를 가능하게 하지만, 중요한 project invariant, pending approval, resource id, 사용자 선호를 요약에서 잃을 수 있다. Compact summary는 원본 trace를 대체하지 않으며, memory/artifact/checkpoint와 함께 써야 한다.

### 9. Cache fragmentation

Specialist agent를 너무 많이 만들거나 prompt/tool schema가 자주 바뀌면 prefix cache hit rate가 떨어진다. Agent descriptor와 tool schema는 versioned stable prefix로 관리하고, dynamic content는 뒤쪽에 배치해야 한다.

## Anecdotal / Community Signals

이 섹션은 공식 문서나 논문과 같은 근거 수준이 아니다. 로컬 LLM 운영자가 체감하는 문제와 검증 포인트를 찾기 위한 참고 신호로만 사용한다.

LocalLLaMA의 tool-calling judgment benchmark는 작은 로컬 모델도 단순 tool 판단에서는 쓸 수 있지만, parser와 restraint가 성능 평가에 큰 영향을 준다고 보고한다. 특히 "tool을 호출할 수 있는가"보다 "호출하지 말아야 할 때 참는가"가 중요하다는 관찰이 있다. [LocalLLaMA tool-calling judgment benchmark](https://www.reddit.com/r/LocalLLaMA/comments/1r4ie8z/i_tested_21_small_llms_on_toolcalling_judgment/)

이 커뮤니티 신호가 주는 실무적 시사점은 다음이다.

- 로컬 agent는 parser test를 별도 eval로 둬야 한다.
- tool-calling success만 보지 말고 no-tool restraint를 측정해야 한다.
- 복잡한 tool ordering이 필요한 업무는 작은 모델이나 넓은 tool surface에 맡기기 어렵다.
- 작은 specialist와 deterministic wrapper tool은 로컬 모델의 판단 부담을 줄일 수 있다.

## Harness Primitives Checklist

Doowon 같은 업무 AI platform에서 최신 harness 흐름을 반영했는지 점검하려면 아래 primitive를 별도로 확인하는 것이 좋다.

| Primitive | 역할 | 적용 기준 |
|---|---|---|
| Durable instruction layer | workspace/project invariant를 매 세션 안정적으로 주입 | `AGENTS.md` 같은 공통 instruction과 tool-specific 파일을 구분 |
| Skill / capability package | task-specific instruction, reference, script, template를 on-demand 로드 | specialist descriptor와 skill metadata를 같은 source로 관리 |
| Subagent runtime | verbose/독립 작업을 별도 context와 tool 권한으로 실행 | domain/task specialist, verifier, background worker에 적용 |
| Tool gateway | tool discovery, schema, ACL, approval, audit를 통제 | MCP-shaped schema와 direct invoke 재검증 유지 |
| Hooks | tool call/stop/compact lifecycle에 deterministic guardrail 삽입 | `PreToolUse`, `PostToolUse`, `PreCompact`, `PostCompact`에 해당하는 이벤트 제공 |
| Compaction + memory | 긴 세션을 요약하고 핵심 상태를 compaction 밖에 보존 | compact summary, memory artifact, checkpoint를 분리 |
| Sandbox runtime | code/browser/shell 실행을 격리 | network, credential, filesystem, replay, metric 정책 포함 |
| Plan/spec-driven gate | 실행 전 계획과 write preview를 사용자에게 제시 | 고위험 write/외부전송/cross-domain synthesis에 우선 적용 |
| Verifier agent | grounding, 정책, 누락 요구사항을 별도 agent가 확인 | executive report, write action, RAG answer에 우선 적용 |
| Eval/trace harness | trajectory 기반 품질/보안/비용 회귀 측정 | routing, tool restraint, compaction, cache, security를 포함 |
| Prompt/prefix cache strategy | stable prefix를 재사용해 latency와 비용 절감 | specialist별 system prompt/tool schema를 안정화 |

## Doowon 적용 시사점

이 문서는 코드 구현 상세를 다루지 않는다. 다만 현재 방향과 연결되는 high-level 시사점은 다음이다.

- 내부 v1은 외부 A2A network가 아니라 manager-specialist runtime으로 충분하다.
- 기존 capability/tool gateway 성격의 계약은 specialist agent의 tool boundary로 재사용하는 편이 좋다.
- `AGENTS.md`/project instruction, skill/capability package, subagent descriptor는 서로 다른 계층으로 분리해 관리하는 편이 좋다.
- PMS, Meeting, Docs, Planner, RAG는 domain specialist 후보가 된다.
- summary/extract/draft/validate/verifier/approval-preview는 task specialist 후보가 된다.
- Meeting/PMS/Planner에는 chat-triggered agent뿐 아니라 ambient/event-driven specialist를 검토할 만하다.
- agent별 descriptor, tool allowlist, context budget, eval suite가 prompt보다 먼저 정의되어야 한다.
- hook, approval gate, sandbox, scoped memory는 prompt가 아니라 runtime primitive로 다뤄야 한다.
- 로컬 Qwen3.6-35B-A3B(MoE, 활성 3B) 운영은 "큰 context에 모든 tool을 넣기"보다 "작은 agent별 prompt/tool/context budget"으로 운영하는 것이 성능, 비용, expert routing 안정성 모두에서 유리하다.

## Conclusion

최근 agentic/harness engineering의 방향은 "더 큰 단일 prompt"가 아니라 "작고 명확한 실행 단위, 안정적인 tool/context boundary, durable trace, eval-driven 개선"이다.

로컬 Qwen3.6-35B-A3B(MoE, 활성 3B) 환경에서는 이 방향이 더 중요하다. Qwen3.6-35B-A3B는 긴 context와 tool use를 지원하지만, 긴 context가 곧 안정적인 agent behavior를 뜻하지 않는다. tool catalog, tool result, conversation history가 커질수록 function calling과 routing 품질은 흔들릴 수 있고, MoE expert routing 변동성까지 더해진다. 활성 파라미터가 작다는 점은 latency/throughput에 유리하지만, 동시에 한 모델에 너무 많은 도메인 책임을 몰아넣을 때의 위험을 dense 모델보다 더 크게 만든다.

따라서 권장 구조는 다음이다.

```
deterministic router first
  -> manager agent only when ambiguous
  -> small domain/task specialist agents
  -> narrow tool allowlist
  -> scoped context and memory
  -> artifact/reference handoff
  -> hooks + approval + sandbox
  -> compaction/memory + prefix cache strategy
  -> trace/eval harness
```

MCP는 tool/context boundary의 표준화 수단으로 즉시 유용하다. A2A는 장기적으로 외부 agent ecosystem과 연결할 때 검토할 표준이다. 내부 제품의 첫 단계에서는 A2A보다 skill/capability packaging, specialist descriptor, tool gateway, hooks, context broker, sandbox, eval harness를 먼저 정교하게 만드는 것이 더 높은 투자 대비 효과를 낼 가능성이 크다.

## Sources

### Official / Vendor Engineering

- Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Anthropic, [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- Anthropic, [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)
- Anthropic, [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- Anthropic, [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Anthropic, [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- Anthropic / Claude API, [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Anthropic / Claude Code, [Skills](https://code.claude.com/docs/en/skills)
- Anthropic / Claude Code, [Subagents](https://code.claude.com/docs/en/sub-agents)
- Anthropic / Claude, [How and when to use subagents in Claude Code](https://claude.com/blog/subagents-in-claude-code)
- Anthropic / Claude Code, [Hooks](https://code.claude.com/docs/en/hooks)
- Anthropic / Claude API, [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- AGENTS.md, [Open format for guiding coding agents](https://agents.md/)
- MCP, [Model Context Protocol intro](https://modelcontextprotocol.io/docs/getting-started/intro)
- MCP, [2025-06-18 specification](https://modelcontextprotocol.io/specification/2025-06-18)
- Google Developers Blog, [Google Cloud donates A2A to Linux Foundation](https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/)
- Google Open Source Blog, [A year of open collaboration: Celebrating the anniversary of A2A](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html)
- OpenAI, [Agents SDK](https://developers.openai.com/api/docs/guides/agents)
- OpenAI, [Agents Python SDK](https://openai.github.io/openai-agents-python/)
- OpenAI, [Agent evals](https://developers.openai.com/api/docs/guides/agent-evals)
- Google ADK, [Multi-agent systems](https://adk.dev/agents/multi-agents/)
- LangGraph, [LangGraph.js API reference](https://langchain-ai.github.io/langgraphjs/reference/modules/langgraph.html)
- LangChain, [Introducing ambient agents](https://www.blog.langchain.com/introducing-ambient-agents)
- Microsoft Research, [AutoGen v0.4](https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/)
- Vercel, [AI SDK 5](https://vercel.com/blog/ai-sdk-5)
- Mastra, [Documentation](https://mastra.ai/docs)
- Pydantic, [PydanticAI overview](https://pydantic.dev/docs/ai/overview/)
- AWS, [Bedrock AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html)
- Cloudflare, [Sandbox SDK](https://developers.cloudflare.com/sandbox/)
- Daytona, [Sandboxes](https://www.daytona.io/docs/en/sandboxes/)
- Modal, [Sandboxes](https://modal.com/docs/guide/sandboxes)
- Qwen, [Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- Qwen, [Function Calling](https://qwen.readthedocs.io/en/stable/framework/function_call.html)
- Qwen, [Key Concepts](https://qwen.readthedocs.io/en/latest/getting_started/concepts.html)
- Qwen, [vLLM deployment](https://qwen.readthedocs.io/en/stable/deployment/vllm.html)
- vLLM, [Automatic Prefix Caching](https://docs.vllm.ai/en/latest/design/prefix_caching/)
- SGLang, [HiCache / prefix cache design](https://docs.sglang.io/docs/advanced_features/hicache_design)

### Research / Evaluation / Security

- Kate et al., [LongFuncEval: Measuring the effectiveness of long context models for function calling](https://arxiv.org/abs/2505.10570)
- Yang et al., [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)
- Yao et al., [τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains](https://arxiv.org/abs/2406.12045)
- Lu et al., [ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities](https://arxiv.org/abs/2408.04682)
- OWASP GenAI Security Project, [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)

### DGX Spark / Qwen3.6-35B-A3B 운영

- NVIDIA, [DGX Spark Hardware Overview](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)
- NVIDIA, [Scaling Autonomous AI Agents and Workloads with NVIDIA DGX Spark](https://developer.nvidia.com/blog/scaling-autonomous-ai-agents-and-workloads-with-nvidia-dgx-spark/)
- NVIDIA, [New Software and Model Optimizations Supercharge NVIDIA DGX Spark](https://developer.nvidia.com/blog/new-software-and-model-optimizations-supercharge-nvidia-dgx-spark/)
- NVIDIA Developer Forum, [Qwen/Qwen3.6-35B-A3B (and FP8) has landed](https://forums.developer.nvidia.com/t/qwen-qwen3-6-35b-a3b-and-fp8-has-landed/366822)
- NVIDIA Developer Forum, [Qwen3.5-35B-A3B-FP8 on 2x DGX Spark: Marlin FP8 on SM121, 495 tok/s at c32](https://forums.developer.nvidia.com/t/qwen3-5-35b-a3b-fp8-on-2x-dgx-spark-main-based-build-marlin-fp8-on-sm121-495-tok-s-at-c32/364842)
- NVIDIA Developer Forum, [Custom built vLLM + Qwen3.5-35B on DGX Spark — sustained 50 tok/s, 1M context](https://forums.developer.nvidia.com/t/custom-built-vllm-qwen3-5-35b-on-nvidia-dgx-spark-gb10-sustained-50-tok-s-1m-context/362590)
- NVIDIA Developer Forum, [DGX Spark: 13 → 49 tok/s with Qwen3.5-35B — Native SM121 Kernel Build Guide](https://forums.developer.nvidia.com/t/dgx-spark-13-49-tok-s-with-qwen3-5-35b-native-sm121-kernel-build-guide/365083)
- NVIDIA Developer Forum, [Qwen3.5-122B-A10B NVFP4 Quantized for DGX Spark — 234GB → 75GB](https://forums.developer.nvidia.com/t/qwen3-5-122b-a10b-nvfp4-quantized-for-dgx-spark-234gb-75gb-runs-on-128gb/361819)
- adadrag, [qwen3.5-dgx-spark: Complete vLLM guide](https://github.com/adadrag/qwen3.5-dgx-spark)
- LMSYS, [NVIDIA DGX Spark In-Depth Review](https://www.lmsys.org/blog/2025-10-13-nvidia-dgx-spark/)
- Substack, [Running Claude Code on a DGX Spark with Qwen 3.6 via LMStudio](https://internate.substack.com/p/running-claude-code-on-a-dgx-spark)
- Hugging Face, [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF)

### Anecdotal / Community

- Reddit r/LocalLLaMA, [I tested 21 small LLMs on tool-calling judgment](https://www.reddit.com/r/LocalLLaMA/comments/1r4ie8z/i_tested_21_small_llms_on_toolcalling_judgment/)
- Hugging Face Discussions, [Qwen3.6-35B-A3B — Poor tools use and endless reasoning loop](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions/20)
- Hugging Face Discussions, [Qwen3.6-35B-A3B — My RTX 3090 ran out of excuses](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions/37)
- Simon Willison, [Qwen3.6-35B-A3B drew me a better pelican than Claude Opus 4.7](https://simonwillison.net/2026/Apr/16/qwen-beats-opus/)
- BuildFastWithAI, [Qwen3.6-35B-A3B: 73.4% SWE-Bench, Runs Locally](https://www.buildfastwithai.com/blogs/qwen3-6-35b-a3b-review)
