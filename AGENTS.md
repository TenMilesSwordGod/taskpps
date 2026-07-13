# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" �� "Write tests for invalid inputs, then make them pass"
- "Fix the bug" �� "Write a test that reproduces it, then make it pass"
- "Refactor X" �� "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] �� verify: [check]
2. [Step] �� verify: [check]
3. [Step] �� verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

Rules:
    - reply / comment/ commit in Chinese
    - never use hardcoding/simulate data/not sure fallback
    - reduce code duplication, use abstractions where possible
    - use linting tools to check code quality after each change step
    - write tests for new features or changes, and ensure they pass(just run influence domain, run full tests will cost so much time)
    - before start should use find skills to check all skills description for any situatuion    
    - use TDD to write code, ensure each change pass the test
    - python should use uv to manage dependencies, if do not want use uv, can use local: .venv
    - **当原定方案无法完成用户任务时，必须先与用户确认替代方案，禁止擅自切换方案或执行不可逆操作（如 commit/push/创建 PR）**
    - all debug tmp files should store in current folder .debug folder.
    - **所有新增/修改的函数和设计必须有中文注释**：注释解释"为什么这么写"而非"做了什么"（如设计决策、边界条件、兼容考虑）
    - **多次改动叠加注释，不删旧说明**：同一段代码经历多次修改时，在原有注释下方追加新注释，格式 `# v2 (2026-07): 说明` / `# 注意(2026-07): 说明`，保留完整的演进上下文
---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.