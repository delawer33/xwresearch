---
name: code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this workspace's documented coding standards?) and Spec (does the code match what the originating issue/PRD asked for?). Runs both reviews in parallel sub-agents and reports them side by side. Exonware-adapted (multi-repo, gh api, AGENTS.md/CLAUDE.md standards, tool-index reuse check). Use when the user wants to review a branch, a PR, work-in-progress changes, or asks to "review since X".
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this workspace's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

## Process

### 1. Pin the fixed point

**Multi-repo workspace:** a change may span several `repos/*`. Establish the repo list first — from the user, the orchestrate manifest, or `git -C repos/<r> status` on the candidates. Pin a fixed point and run diff/log **per repo, from inside that repo** — never from the workspace root.

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. If they didn't specify one, ask for it.

Capture the diff command once per repo: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

Before going further, confirm each fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside two parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, etc.) — fetch via `gh api repos/exonware/<repo>/issues/<n>`. **Never `gh issue view`/`gh issue list` — they're broken in this workspace.**
2. A path the user or orchestrator passed as an argument — including an orchestrate manifest, where the bullet's brief + done condition IS the spec.
3. A PRD/spec file under `<repo>/docs/` or `wayfinder/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Standards here are: root **`AGENTS.md`** (workspace conventions), the **target repo's `CLAUDE.md`** (truth for that repo), and **`docs/glossary.md`** for term misuse. `CODING_STANDARDS.md`/`CONTRIBUTING.md` don't exist in these repos — don't hunt for them.

On top of the documented sources, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) plus two ecosystem smells. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.
- **Reinvented Tool** *(ecosystem)* — the diff hand-rolls a helper, client, parser, HMAC, deep-merge, or similar that `docs/tool-index.md` already lists. → cite the tool-index entry; use it instead.
- **Wrong Layer** *(ecosystem)* — feature logic added to a product/project repo that belongs in an `xw*` package (priority: xw > product > project). → name the target `xw*` package. Judgement call.
- **Narrative Comment** *(ecosystem)* — a comment that tells the story of the change instead of stating a constraint: temporal references ("used to", "no longer", "before this fix"), verification results and dates, bug post-mortems, session narration. The tell: it only makes sense to someone who saw the bug. The author-agent cannot see these — inside its session the bug *is* the why — which is why a cold reader must judge them. → delete; move anything durable into the commit message or the issue. (AGENTS.md §4 cold-reader test.)
- **Defensive Debris** *(ecosystem)* — belt-and-braces residue of a debugging session left around the actual change: broad try/except that swallows, fallbacks for states that can't occur, re-validation of already-validated data, log lines narrating control flow. → delete; keep only guards whose failure mode is real and named.

### 4. Spawn both sub-agents in parallel

Send a single message with two `Agent` tool calls. Use the `general-purpose` subagent for both.

**Both sub-agents are read-only reviewers — say so explicitly in every prompt:** "You are reviewing only. Do not run `git commit`, `git merge`, `git push`, `git checkout`, `git reset`, or any other command that changes repo state — read-only git commands (`diff`, `log`, `show`, `status`) only. Report findings as text; do not fix anything or stage/commit changes yourself." This applies even if the diff looks unfinished or a fix seems obvious — that decision belongs to whoever invoked the review, not the reviewer.

**Tell each sub-agent, verbatim: "Do not use SendMessage. Your final response text IS your
report — just end your turn with it."** Without this they try to message their findings back to
a recipient name that doesn't resolve, retry in a loop, and the report surfaces to the wrong
place. Costly and easy to miss, because the review itself looks like it succeeded.

**Also tell each sub-agent, verbatim:**

- "`gh issue view`/`gh issue list` are broken in this workspace — use `gh api repos/:owner/:repo/issues/...`."
- "Scope every claim to what you actually read: 'in this diff', not 'nowhere in the codebase'. If you didn't verify something, label it unverified."

**If you are yourself a sub-agent** (this skill reached you via `/implement` rather than a
person): you still spawn both reviewers normally, but the user cannot answer questions. Use the
commit you started from as the fixed point in step 1, and don't idle waiting — write your own
summary while they run, and if one doesn't return, perform that axis yourself and say so.

**Standards sub-agent prompt** — include:

- The full diff command(s) and commit list(s), per repo, each with the repo path to run them from.
- The standards-source paths: root `AGENTS.md`, each target repo's `CLAUDE.md`, `docs/glossary.md`, and `docs/tool-index.md` (for the Reinvented Tool check) — **plus the smell baseline from step 3 pasted in full** — the sub-agent has no other access to it.
- The output of `task lint:comments -- <repo> <fixed-point>` (run it yourself before spawning) — pasted in as **leads for the Narrative Comment smell**: the regex catches the common phrasings, the sub-agent confirms or dismisses each and hunts the phrasings the regex can't catch. A clean lint does not close the smell.
- The brief: "Report — per repo, then per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent prompt** — include:

- The diff command(s) and commit list(s), per repo, each with the repo path to run them from.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. When the change spans repos, keep each report's per-repo grouping (`### <repo>` inside each axis). Do **not** merge or rerank findings — the two axes are deliberately separate (see _Why two axes_).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
