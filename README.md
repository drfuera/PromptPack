# PromptPack

**A powerful CLI tool for AI-assisted development workflows**

PromptPack helps you package your codebase for AI assistants (Claude, GPT, DeepSeek, etc.) and apply AI-generated patches with precision. Built for developers who want AI coding assistance while keeping full control over their codebase.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Interactive TUI Controls](#-interactive-tui-controls)
  - [Patching Files](#-patching-files)
  - [Wildcard Patching](#-wildcard-patching)
  - [Undoing and Redoing Patches](#undo-redo-patches)
  - [Working with Summaries & Work Log](#-working-with-summaries--work-log)
  - [Search Operations](#-search-operations)
  - [Running Shell Commands](#running-shell-commands)
  - [Code Maintenance](#-code-maintenance-1)
  - [Clipboard Management](#-clipboard-management)
- [AI Workflow Integration](#ai-workflow-integration)
  - [The PromptPack Workflow](#the-promptpack-workflow)
  - [Special AI Commands](#special-ai-commands-embedded-in-ctagstxt)
  - [Reviewing Changes with `#audit`](#reviewing-changes-with-audit)
  - [Optimizing with `#optimize`](#optimizing-with-optimize)
  - [Example AI Interaction](#example-ai-interaction)
- [Optional: X11 Middle-Click Paste+Submit](#optional-x11-middle-click-pastesubmit-x11)
- [Configuration](#configuration)
  - [File Selection Storage](#file-selection-storage)
  - [Patch History](#patch-history)
  - [Summary History](#summary-history)
- [Advanced Features](#advanced-features)
  - [Smart Patch Matching](#smart-patch-matching)
  - [Python Syntax Auto-Fix](#python-syntax-auto-fix)
  - [Python Dependency Import Tracking](#python-dependency-import-tracking)
  - [Work Log & On-Demand Patch Detail](#work-log--on-demand-patch-detail)
  - [Token Estimation](#token-estimation)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [License](#license)
- [Credits](#credits)

---

## Features

### 📦 Smart Code Packaging

- **Interactive TUI**: Navigate your project tree with keyboard shortcuts
- **Selective file marking**: Choose exactly which files to include
- **Token counting**: Live token count of your selection in the status bar
- **Persistent selection**: File selections are saved in `.promptpack`
- **`ctags.txt` output**: A lightweight structure overview (via Universal Ctags), with the full PromptPack AI-workflow instructions embedded at the top and a compact `# WORKLOG` of the project's history at the bottom

### 🔧 Advanced Patch Management

- **Precise text replacement**: Apply patches with exact old→new text matching
- **Three-level smart matching**:
  - Exact matching (default)
  - Flexible whitespace matching (immune to space/tab variations)
  - Tidy matching (normalizes blank lines and trailing whitespace before matching)
- **Wildcard patching**: Skip large middle sections using `***WILDCARD_PROMPTPACK***`
- **Python syntax validation**: Auto-detects and fixes indentation errors after patching
- **Patch history**: Full undo/redo support with an F12 patch browser
- **Error logging**: Failed patches are written to `clipboard.tmp` for review

### 📊 Task Summaries & Work Log

- **Summary history (`--summary "about text" --rating N`)**: Save a timestamped changelog entry to `summary.json` after each completed task. The quoted argument is a 1–2 sentence, information-dense `about` line; the heredoc on stdin holds the verbose text explaining what changed and why, for future AI sessions or human reviewers; `--rating 1-3` grades how much the task matters for the code and future development (3 = architecture, data format, workflow rules or decisions future work must respect; 2 = new feature or noticeable behavior change; 1 = bugfix, docs, cosmetics). All three parts are required — a call missing any of them is rejected and nothing is saved. The summary is linked automatically to every patch applied since the previous summary
- **Mark a summary reverted (`-us`)**: Flags a summary entry as `reverted` in `summary.json` — a historical annotation only. It never touches any patch or any code; undoing actual code changes is always done explicitly, one patch at a time, via `-u`
- **Work log (`-w`)**: Combine `patch.json` + `summary.json` into a lightweight `work.txt` — a PATCH TOC (date, ID, file, description) up top, followed by the full chronological log (full summary text + compact one-line patch entries, no code embedded)
- **Patch history lookup (`-ph`)**: Fetch full old/new code for one or more specific `PATCHID`s on demand — lets the AI use `work.txt`'s dates and descriptions to decide what's worth a closer look, without ever needing to read all of `patch.json` directly
- **`# WORKLOG` in `ctags.txt`**: Every time `ctags.txt` is generated it ends with a compact, chronological, size-capped worklog: one line per summary (`ID LOG R<n>:about`, with its rating) and, for recent tasks, one line per patch (`ID PATCH:description`) just before the LOG that closes its task. It is tiered by recency and rating: the 50 newest tasks in full, then up to 25 older tasks rated 2–3 and up to 25 older tasks rated 3, where older tasks show their patch IDs as a range such as `[P41-43]`. Reverted tasks drop out of the older tiers, and a note at the top says how many tasks were omitted. It gives the AI a cheap overview of the project history; usually only the last few entries matter
- **Summary lookup (`-log`)**: Fetch the full text of one or more summaries by ID, space- or comma-separated (`-log 53 54 55`), together with their rating, `about` line and linked patch IDs, so the AI pulls only the summaries it needs instead of reading all of `work.txt`
- **Complete worklog (`-completelog`)**: Print the same worklog format as the `# WORKLOG` in `ctags.txt`, but unfiltered: every task with its rating and every patch line. Use it when the filtered view is not enough

### 🔍 Code Navigation & Search

- **File search (`-fs`)**: Search across multiple files with wildcards or regex, recursive by default
- **Context search (`-s`)**: Find text and extract N lines before/after the match
- **Line extraction (`-n`)**: Read specific line ranges from files
- **Full file read (`-r`)**: Read complete files into the clipboard pipeline
- **Clipboard pipeline**: All results accumulate in `clipboard.tmp`, copied at once with `-c`

### 🐍 Python Dependency Tracking

- **Import-aware marking (`i` key)**: Automatically mark a Python file and all its local dependencies
- Recursively traces `import` and `from ... import` statements across the project tree
- Toggle all deps on/off with a single keypress

### 🧹 Code Maintenance

- **Tidy files (`-t`)**: Remove trailing whitespace and reduce consecutive empty lines to max 1
- **Recursive tidy (`-tr`)**: Process all text files in the entire project tree at once
- **Wildcard patterns**: Target specific file types (`*.py`, `src/*.js`, etc.)

### 🖥️ Command Execution

- **Run shell commands (`-e`)**: Execute a bash command (optionally with a timeout) with output captured live into `clipboard.tmp`
- **Safety blacklist**: Destructive commands (`rm`, `rmdir`, `dd`, `chmod`, `mv`, `truncate`, `shred`, fork bombs) are blocked outright

### 🔬 AI Code Review & Optimization

- **`#audit`**: Structured bug and risk review with fixed passes (requirements, contracts, boundary values, pre-mortem, security, consistency). `#test` still works as an alias
- **`#optimize`**: Language-independent performance review (goal and metric, domain, resource analysis, complexity, eight optimization levers, measurement) for anything from HTML to C#, GUI to network code
- **Autonomous by design**: Both run without user input — one single fetch round, then the AI verifies or measures in its own environment instead of asking you to run anything
- **Report only**: Nothing is patched until you approve it

### 📄 Instruction Export

- **`-i` flag**: Export the AI-workflow instructions (the same block embedded in `ctags.txt`) to a standalone `promptpack_instructions.txt` file — handy for pasting into a system prompt or sharing without a full project package

---

## Installation

### Requirements

- Python 3.6+
- Universal Ctags
- Clipboard utility: `xclip`, `xsel`, or `pbcopy`
- `tiktoken` Python package

### Install Dependencies

**Ubuntu/Debian:**
````bash
sudo apt install python3 python3-pip universal-ctags xclip
pip3 install tiktoken
````

**macOS:**
````bash
brew install universal-ctags
pip3 install tiktoken
````

### Install PromptPack

````bash
# Clone the repository
git clone https://github.com/drfuera/PromptPack.git
cd PromptPack

# Make executable
chmod +x promptpack.py

# Optional: Add to PATH
sudo ln -s "$(pwd)/promptpack.py" /usr/local/bin/promptpack
````

---

## Quick Start

### Interactive Mode

Launch the interactive file browser:

````bash
promptpack
````

Navigate with arrow keys, mark files with `Space`, generate `ctags.txt` with `F1`, browse patch history with `F12`, quit with `q`.

### Export Instructions Only

Export the AI-workflow instructions on their own, without packaging any files:

````bash
promptpack -i
````

This writes `promptpack_instructions.txt` to the current directory.

---

## Usage Guide

### 🎯 Interactive TUI Controls

| Key | Action |
|-----|--------|
| `↑↓` | Navigate files/folders |
| `←→` | Collapse/expand folders |
| `Space` | Mark/unmark file or folder (marks all children) |
| `i` | Mark file + all local Python import dependencies |
| `F1` | Generate `ctags.txt` |
| `F12` | Browse and toggle patch history |
| `q` | Quit |

---

### 📝 Patching Files

**Basic patch format:**

````bash
cat <<'PATCH' | promptpack -p "path/to/file.py" "Short description"
old text that exists in file
exactly as it appears
---SPLIT---
new text to replace it
PATCH

promptpack -c
````

**Multiple patches — always end batch with `promptpack -c`:**

````bash
cat <<'PATCH' | promptpack -p "file1.py" "Fix login bug"
old_code_here
---SPLIT---
new_code_here
PATCH

cat <<'PATCH' | promptpack -p "file2.py" "Add error handling"
other_old_code
---SPLIT---
other_new_code
PATCH

promptpack -c
````

**Patch requirements:**
- Description: max 10 words
- `old_text`: must match EXACTLY (including all whitespace and newlines)
- `old_text`: must be UNIQUE in the file (appear only once)
- Separator: `---SPLIT---` on its own line between old and new text

---

### 🧩 Wildcard Patching

When `old_text` spans more than a dozen lines, use `***WILDCARD_PROMPTPACK***` as a placeholder to skip the middle section. Only the prefix and suffix need to be unique together.

````bash
cat <<'PATCH' | promptpack -p "path/to/file.py" "Replace large block"
first 2-5 unique lines of old_text
***WILDCARD_PROMPTPACK***
last 2-5 unique lines of old_text
---SPLIT---
complete new replacement text goes here
PATCH

promptpack -c
````

**Wildcard rules:**
- Use only **one** `***WILDCARD_PROMPTPACK***` per patch block
- The prefix + suffix combination must match exactly once in the file
- `***WILDCARD_PROMPTPACK***` is **not** valid in `new_text`, only in `old_text`

---

### ↩️ <a id="undo-redo-patches"></a>Undoing and Redoing Patches

**Undo a specific patch by its PATCHID:**

````bash
promptpack -u 12
promptpack -c
````

If undo fails because the new text isn't unique, undo the more recent overlapping patches first (highest PATCHID down), then retry. Patches can also be toggled undo/redo from the `F12` browser in interactive mode.

---

### 📊 Working with Summaries & Work Log

**Save a task summary (recommended at the end of every patch task):**

````bash
cat <<'SUMMARY' | promptpack --summary "Dense 1-2 sentence about: files touched, what changed, why." --rating 2
Explain what changed in each file and why, for a reader with zero context.
SUMMARY
promptpack -c
````

The quoted argument is the `about` line. It is stored separately in `summary.json` and listed in the `# WORKLOG` section of `ctags.txt`, so keep it to 1–2 sentences, as information-dense as possible. Use plain prose only — no double quotes, backticks or `$` inside it, because the shell interprets them inside double quotes. The heredoc holds only the verbose text. `--rating N` is required too.

**Rating scale** — judge by: would an AI that sees only the `# WORKLOG` make a mistake or redo work if this task were missing? When unsure between two levels, pick the lower:

- `3` = architecture, data format, workflow rules, public interface, or a decision future work must respect (rare, roughly 1 task in 8)
- `2` = new feature or a noticeable behavior change
- `1` = bugfix, docs, cosmetics, small refactor without behavior change

The rating decides how long a task stays in the `# WORKLOG`. If any part (about text, verbose text or rating) is missing the call is rejected immediately, with an error in `clipboard.tmp`, and nothing is saved. When a summary is saved, it is linked automatically to every patch applied since the previous summary, so you never pass PATCHIDs yourself.

**Fetch full summaries by ID (IDs come from the `# WORKLOG` section in `ctags.txt`):**

````bash
promptpack -log 53 54 55
promptpack -c
````

IDs can be space- or comma-separated (`-log 53,54,55`). The output shows the rating, the linked patch IDs as a range, the `about` line and the full text. Missing IDs are reported without failing the ones that were found. Use `-ph` for the code of a specific patch — LOG and PATCH IDs are separate number series.

**Print the complete, unfiltered worklog:**

````bash
promptpack -completelog
promptpack -c
````

Same format as the `# WORKLOG` in `ctags.txt`, but with every task and every patch line instead of the filtered view. It can be long, so use it only when the filtered view is not enough, then fetch details with `-log` and `-ph`.

**Mark a summary as reverted (does NOT touch any patch or code):**

````bash
promptpack -us 4
promptpack -c
````

This only flags the `summary.json` entry itself as historical/reverted. To actually undo code changes, find the relevant `PATCHID`s (via `-w`/`work.txt` or `-ph`) and undo each one explicitly with `-u`.

**Build the combined work log:**

````bash
promptpack -w
promptpack -c
````

Writes `work.txt`: a PATCH TOC (date, PATCHID, file, description) followed by the full chronological log — summaries in full, patches as compact one-liners. Safe to read in full even on a large project, since no code is embedded.

**Fetch full code for specific patches:**

````bash
promptpack -ph 12 15 18
promptpack -c
````

Returns the old/new code for just those PATCHIDs, identified from `work.txt`'s dates and descriptions — avoids ever needing to read all of `patch.json` directly.

---

### 🔍 Search Operations

**Search across files (recursive by default):**

````bash
# Literal search
promptpack -fs "def main" "*.py"

# Wildcard search
promptpack -fs "class *Player*" "game*.py"

# Regex search
promptpack -fs "regex:def\s+\w+\(" "*.py"

promptpack -c
````

**Find text and extract surrounding context:**

````bash
# Grab 10 lines before and 20 lines after the match
promptpack -s "function_name" 10,20 path/to/file.py

# Regex match with context
promptpack -s "regex:^class\s+\w+" 15,30 file.py

promptpack -c
````

**Read specific line ranges:**

````bash
promptpack -n 100,150 path/to/file.py
promptpack -n 10,20 file1.py
promptpack -n 50,75 file2.py
promptpack -c
````

**Read entire file:**

````bash
promptpack -r path/to/file.py
promptpack -c
````

> All `-r`, `-n`, `-s`, and `-fs` results accumulate in `clipboard.tmp`. Always end a batch with `promptpack -c` to copy everything to clipboard and clear the temp file.

---

### 🖥️ <a id="running-shell-commands"></a>Running Shell Commands

````bash
# No timeout
promptpack -e "echo hello"

# With a timeout (seconds)
promptpack -e 15 "python3 main.py"

promptpack -c
````

Output (stdout and stderr, streamed live) is appended to `clipboard.tmp`. Destructive commands (`rm`, `rmdir`, `dd`, `chmod`, `mv`, `truncate`, `shred`, fork bombs) are blocked outright and never run.

---

### 🧹 Code Maintenance

````bash
# Tidy a single file
promptpack -t file.py

# Tidy with wildcard pattern
promptpack -t "*.py"
promptpack -t "src/*.js"

# Multiple patterns at once
promptpack -t "*.py" "*.js" "*.cpp"

# Recursively tidy ALL text files in entire project
promptpack -tr
````

Tidy removes trailing whitespace from every line and collapses consecutive empty lines down to a maximum of one.

---

### 📋 Clipboard Management

All read, search, and execute operations append to `clipboard.tmp`. Use `-c` to copy all accumulated output to the system clipboard and delete the temp file. On success `-c` prints a one-line confirmation with the size in KB and the token count of what was copied.

````bash
promptpack -r file1.py
promptpack -n 100,150 file2.py
promptpack -fs "def main" "*.py"
promptpack -c   # Copy all results to clipboard, remove clipboard.tmp
````

---

## AI Workflow Integration

### The PromptPack Workflow

1. Mark your files using interactive mode
2. Generate `ctags.txt` (`F1`) — the AI instructions and project structure/symbol overview are embedded automatically
3. Send `ctags.txt` to your AI assistant (Claude, GPT-4, DeepSeek, Grok, etc.)
4. The AI already has the full instruction set from `ctags.txt` alone — it reads any file it needs directly with `promptpack -r path`, no separate packaging step required
5. AI responds with patches in PromptPack format, ending the block with a `--summary` heredoc
6. Copy-paste and run the bash block to apply all patches and save the summary at once
7. Review results in the F12 patch history browser
8. Undo individual patches as needed with `-u <PATCHID>` — this is the only way code changes get reverted
9. The `# WORKLOG` at the bottom of `ctags.txt` gives the AI a compact, tiered overview of earlier work (newest tasks in full, older ones filtered by rating); it fetches full summaries with `-log <ID...>` and full patch code with `-ph <PATCHID...>` only when needed
10. Run `-completelog` when the filtered view is not enough, or `-w` to rebuild `work.txt` with every summary in full; both grow large on long projects, so the worklog plus `-log` is the preferred way in

### Special AI Commands (Embedded in ctags.txt)

| Command | Description |
|---------|-------------|
| `#patch` | Patching mode — AI generates patch commands |
| `#ask` | Question mode — AI answers without writing code |
| `#undo` | Revert the last applied patch |
| `#reset` | Revert all patches, back to the original state |
| `#outsource` | AI writes a detailed prompt for another AI to solve the problem, ending with the `promptpack -r` commands needed to gather relevant files |
| `#dumb` | Rewrite the last message in plain non-technical language |
| `#ideas` | List alternative solutions/ideas, no code |
| `#audit` | Structured bug and risk review in three modes: `#audit` (this session's patches), `#audit <target>` (a named function, class or file) and `#audit full` (whole codebase, one module per round). Fixed passes (requirements, contracts, boundary values, pre-mortem, security, consistency), runs autonomously, checks run in the AI's own environment, report only. `#test` is still accepted as an alias |
| `#optimize` | Language-independent performance review in the same three modes. Passes for goal and metric, domain, resource analysis, complexity, eight optimization levers, domain bottlenecks and cost/risk, measured by the AI in its own environment, report only |
| `#name` | Suggest a short (3–8 word) internal codename for the current version/problem — for reference only, never written into code |
| `#done` | Wrap up session — AI generates a `PROMPTPACK Summary` for the next context window |

### Reviewing Changes with `#audit`

`#audit` (formerly `#test`, still accepted as an alias) is a structured bug and risk review. It runs autonomously: the AI asks no questions and waits for no approval between steps. Everything it needs is collected into one single `promptpack` block, the only time you have to run something and paste output back, and from there it works through to the final report.

`#audit` has three modes. Plain `#audit` reviews the patches the AI wrote in the current session plus directly affected code (callers and callees; it may read one or two clearly relevant imported files, but does not wander further). `#audit <target>` reviews a named function, class or file, whether or not it changed this session, plus directly affected code. `#audit full` covers the whole codebase, but never in a single reply: the AI plans from the ctags list, prioritizes risky parts such as parsing, file I/O and shell calls, reviews one module per round, states plainly what was reviewed and what was not reached, and ends every round with a line naming the next module, so a plain "continue" resumes. `full` is a reserved word, so it cannot be used as a target name.

In session mode the AI knows its own patches from the `[PATCHID n]` lines you pasted back. Only if the session was restarted via `#done` does it fall back to the patch IDs under the latest `LOG` lines of the `# WORKLOG`, fetched with `-ph`. In every mode it reads the actual code with `-r`/`-n` (even if shown earlier, because patching can auto-correct indentation and the file may differ from the patch text) and searches for callers and callees of the changed functions with `-fs`, all in one fetch block. The block is skipped if everything is already in the conversation.

Seven reasoning passes run in a fixed order, each using the results of the earlier ones: scope, requirements coverage, Design by Contract, boundary analysis, pre-mortem, OWASP/CWE/CERT (only if input, files, paths, shell or parsing are touched) and consistency/design. In session mode the requirements pass asks whether the change did exactly what was asked; if not, passes 3-7 are skipped but you still get a report. In `<target>` and `full` mode there is no request to compare with, so the code is compared with its purpose (docstring, README, function name) or the pass is skipped with a stated reason. The check that the summary matches the patches applies only in session mode. The AI may skip a pass only by stating a reason in one line. Every finding has file and line, severity (bug, risk, minor remark) and status `VERIFIED` or `SUSPECTED`; bugs come with a concrete triggering input.

The eighth pass, verification, is mandatory and is done by the AI itself, in its own environment (code execution tool, sandbox or shell), on copies of the code it was shown: a syntax check, a linter (`pyflakes`/`ruff` or the language's equivalent), existing tests, and a small reproduction for every `SUSPECTED` bug. You are never handed a verification block. If the AI has no execution environment it does not ask you to run anything: it verifies by hand-tracing concrete values, leaves what it cannot confirm as `SUSPECTED` and marks the report "not executed". No patches are written during `#audit`; fixes come only after your okay, as a normal `#patch`.

### Optimizing with `#optimize`

`#optimize` is a language-independent performance review, meant to work the same way for HTML, PHP, Python, C#, GUI and TUI code, OpenGL, network code and anything in between. It follows the same ground rules as `#audit`: report only, fully autonomous (no questions, at most one fetch round, measurements run by the AI in its own environment), the same three modes (`#optimize`, `#optimize <target>`, `#optimize full` with the same limits) and the same locate-and-fetch rules. It works from evidence, never from intuition: no change is recommended on a hunch alone.

It rests on one model: total cost = how many times something runs × what each run costs, spent on some resource (CPU, memory, disk, network, GPU, locks or waiting, or the user's perceived latency). Every pass reduces one of the two factors or the resource they burn. Seven reasoning passes run in a fixed order:

1. **Goal and metric**: what should get better (frame time, latency, throughput, memory, startup time, size, battery) and for which input size or scenario
2. **Domain and toolchain**: language, runtime, framework and domain (GUI/TUI, graphics, web front-end or back-end, database, network, CLI, embedded and so on) identified from files, imports and ctags, with the matching measurement tools and typical bottlenecks; every domain claim must point at a concrete line
3. **Resource analysis**: where the cost goes and which hot path dominates, ranked by expected share of the total cost (Amdahl: speeding up a 2% part is not worth the change)
4. **Workload and complexity**: how often each hotspot runs and on how much data, Big-O in time and memory, nested loops, repeated scans, repeated sorting
5. **The eight levers**, cheapest and safest first: remove the work; do it less often (cache, memoize, dirty flags); move it out of the hot path; do it in bulk (batching, buffering, instancing); do it lazily; do it cheaper (better algorithm or data structure, fewer allocations); do it concurrently or off the critical thread (only for a proven bottleneck); do it approximately when an exact result is not required
6. **Domain bottlenecks**: the known typical problems of the identified domains, such as N+1 queries, draw calls and per-frame buffer uploads, UI thread blocking, GC pressure in hot loops, render-blocking resources or connection reuse. Only what the code actually shows is reported
7. **Cost and risk**: expected gain, risk of changed behavior and added complexity for every candidate; marginal or unmeasurable candidates are rejected, and premature optimizations already in the code are flagged

Every finding has file and line, a category (algorithmic, redundant work, memory and I/O, concurrency, domain-specific), expected gain, risk and a status: `VERIFIED` (measured, or proven by a trace or count such as a call count) or `SUSPECTED` (plausible but not measured).

The eighth pass, measurement, is again done by the AI in its own environment: a baseline first, then a profiler or timer on the isolated hotspot with realistic input sizes, call counts, a complexity check by timing at n and 10n, memory measurement where relevant, and where possible the candidate change tested on the same inputs with the output compared to the original. If the code needs something the AI does not have (GPU, display, database, network, hardware), it measures the pure-logic parts it can isolate and states what stays unmeasured. Without an execution environment it never asks you to run anything and never invents numbers: findings stay `SUSPECTED` and are marked "not measured".

The final report ranks candidates by gain divided by risk, each with status, a measured or estimated figure and the proposed change in one sentence, followed by what was not reviewed. No patches are written during `#optimize`. After your okay, each optimization is applied as its own patch task with behavior unchanged; if the gain turns out marginal after patching, the AI recommends `#undo`.

### Example AI Interaction

User: `#patch Add error handling to the login function`

AI responds with:

````bash
cat <<'PATCH' | promptpack -p "auth/login.py" "Add error handling to login"
def login(username, password):
    user = db.get_user(username)
    return user.verify_password(password)
---SPLIT---
def login(username, password):
    try:
        user = db.get_user(username)
        if not user:
            raise ValueError("User not found")
        return user.verify_password(password)
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return False
PATCH

cat <<'SUMMARY' | promptpack --summary "login() in auth/login.py now catches lookup and password-check failures and logs them instead of crashing." --rating 2
Added error handling to login() in auth/login.py: wraps the database
lookup and password check in a try/except, raises a clear error when the
user isn't found, and logs any failure instead of letting it crash
unhandled. This prevents unexpected exceptions from reaching callers and
makes login failures easier to diagnose from the logs.
SUMMARY

promptpack -c
````

User runs the bash block — patch and summary are applied, and the result is copied to clipboard.

---

## Optional: X11 Middle-Click Paste+Submit (`x11/`)

Two small helper scripts speed up the copy → paste → submit loop that PromptPack workflows repeat constantly: copying an AI-generated bash block into a terminal, and pasting terminal output (the result of `promptpack -c`) back into the AI chat. With the helpers enabled, a single middle click pastes the clipboard and presses Enter, saving a few hand movements on every patch or reply.

| Script | Purpose |
|--------|---------|
| `HomePageMiddleClickPasteSubmit.sh` | **Toggle.** Turns middle-click Paste+Enter on or off. Run it once to enable, again to disable. |
| `HomePageMiddleClick_Status.sh` | **Status.** Prints `PasteSubmit ✅` when enabled and `PasteSubmit ⛔` when disabled. Meant to be polled by a panel applet or status bar. |

**How it works:** the toggle script adds or removes a marked block (`# BEGIN paste-enter-toggle` … `# END paste-enter-toggle`) in `~/.xbindkeysrc` and restarts `xbindkeys`. While the block exists, mouse button 2 runs `xdotool key Shift+Insert`, waits 0.2 s and then runs `xdotool key Return`. The status script only checks whether that block is present, so it is safe to call as often as your panel needs.

**Requirements:**
- An **X11 session** — these scripts do not work under Wayland, where `xbindkeys` cannot capture global mouse clicks and `xdotool` cannot send input to native Wayland windows
- `xbindkeys` and `xdotool` (`sudo apt install xbindkeys xdotool` on Ubuntu/Debian)
- `bash`, `grep`, `sed` and `pkill` (present on practically every distro)

**Setup:**

````bash
chmod +x x11/HomePageMiddleClickPasteSubmit.sh x11/HomePageMiddleClick_Status.sh

# Toggle on/off (bind this to a panel button, launcher or keyboard shortcut)
./x11/HomePageMiddleClickPasteSubmit.sh

# Show current state (point your panel applet / status bar at this)
./x11/HomePageMiddleClick_Status.sh
````

The status script outputs plain text, so it works with any desktop or bar that can display a command's output: a Cinnamon applet, Xfce generic monitor, polybar, i3blocks and similar.

**Things to know:**
- Middle click is captured **globally** while the feature is on, so normal middle-click behavior (primary-selection paste, closing tabs, opening links in new tabs) stops working until you toggle it off
- Enter is sent immediately after the paste, so whatever is on the clipboard is **submitted at once**. Only enable it when you trust the clipboard content, and review commands before running them in a terminal
- `Shift+Insert` pastes the clipboard in most applications, but a few terminals and Qt programs may paste the primary selection instead
- `xbindkeys` is only started when the toggle runs. Add `xbindkeys` to your session autostart so an enabled binding survives a logout or reboot

---

## Configuration

### File Selection Storage

Selections are stored in `~/.promptpack` as absolute paths, scoped per project. This allows multiple projects to maintain independent selections on the same machine.

### Patch History

Patches are stored in `patch.json` in the project directory. Open the browser with `F12` in interactive mode to inspect, unapply, or reapply any patch.

````json
[
  {
    "id": 1,
    "timestamp": "2025-01-25T10:30:00",
    "filepath": "/absolute/path/to/file.py",
    "description": "Add error handling",
    "old_text": "...",
    "new_text": "...",
    "applied": true
  }
]
````

### Summary History

Task summaries are stored in `summary.json` in the project directory, written via `--summary` after each completed task. Each entry has a separate `about` field (the quoted `--summary` argument) next to the verbose `text` (the heredoc), a `rating` (1–3) and `patch_ids`, the IDs of every patch applied since the previous summary. An entry without a valid rating counts as 2 in the worklog.

````json
[
  {
    "id": 1,
    "timestamp": "2025-01-25T10:35:00",
    "text": "Added error handling to login() in auth/login.py...",
    "about": "login() in auth/login.py now catches lookup and password-check failures and logs them.",
    "rating": 2,
    "patch_ids": [1, 2]
  }
]
````

`-us <SUMMARYID>` sets `"reverted": true` (plus a `reverted_at` timestamp) on the matching entry. This is a historical annotation only — it never deletes the entry and never touches `patch.json` or any file on disk. To undo the actual code changes a summary describes, undo each relevant `PATCHID` explicitly with `-u`. In the `# WORKLOG` of `ctags.txt`, a reverted summary is dropped from the older tiers and tagged `[REVERTED]` among the newest ones.

---

## Advanced Features

### Smart Patch Matching

PromptPack uses three escalating levels of text matching to handle real-world copy-paste variations:

1. **Exact match** — character-for-character, fastest
2. **Flexible whitespace** — matches when spacing/indentation differs
3. **Tidy matching** — normalizes trailing whitespace and blank lines before comparing

### Python Syntax Auto-Fix

For `.py` files, PromptPack automatically validates syntax after applying a patch. If an `IndentationError` is detected, it attempts to auto-correct indentation. If the error cannot be resolved, the patch is aborted and the file is left untouched.

### Python Dependency Import Tracking

Press `i` on any `.py` file in the TUI to automatically mark it along with all locally resolvable `import` dependencies. Pressing `i` again toggles all dependencies off. This ensures `ctags.txt` reflects the full dependency graph relevant to the AI's task.

### Work Log & On-Demand Patch Detail

As `patch.json` and `summary.json` grow on a long-running project, reading them in full can eat a large chunk of an AI's context window. Instead, `ctags.txt` ends with a compact, size-capped `# WORKLOG`: chronological, one line per summary (`ID LOG R<n>:about`, with its impact rating) and, for recent tasks, one line per applied patch (`ID PATCH:description`) just before the LOG that closes its task. It has three tiers: the 50 newest tasks in full (every rating, with patch lines), up to 25 older tasks rated 2–3, and up to 25 older tasks rated 3; older tasks show their patch IDs as a range like `[P41-43]` instead of separate lines. Reverted tasks never stay in the older tiers, patches not yet claimed by a summary come last as work in progress, and a note at the top states how many tasks were omitted (LOG IDs then have gaps). The AI scans it for orientation, then fetches only what matters — `-log <ID...>` for full summaries and `-ph <PATCHID...>` for full patch code — keeping context usage proportional to what's actually relevant. LOG and PATCH IDs are separate number series, and the WORKLOG is regenerated whenever `ctags.txt` is (`F1`).

`-completelog` prints the same worklog format without any filtering (every task with its rating and every patch line). `-w` builds the complete `work.txt` (a PATCH TOC plus the full chronological log with full summary text and one-line patch entries, never code) for when every summary is needed in full. Both grow large on long projects.

### Token Estimation

Live token counts are shown in the status bar, and the file size in bytes and the token count are printed after `ctags.txt` is generated. `promptpack -c` also prints the size in KB and the token count of what it copies.

---

## Troubleshooting

### "Universal Ctags is not installed!"

````bash
sudo apt install universal-ctags   # Ubuntu/Debian
brew install universal-ctags        # macOS
````

### "Could not copy to clipboard"

Install a clipboard utility:

````bash
sudo apt install xclip   # Ubuntu/Debian
````

Or use `xsel` (Linux) or `pbcopy` (macOS, built-in).

### Patch fails: "Old text not found"

- Search `ctags.txt` (or the live file via `-r`) for the current exact code
- Ensure whitespace (tabs vs spaces) matches precisely
- Use a minimal but unique 1–3 line `old_text`
- If the block is large, use wildcard patching instead

### Patch fails: "Old text appears N times"

- Add more context to make `old_text` unique
- Include unique surrounding lines or identifiers

### Patch fails after regex in `-s` or `-fs`

- Always prefix regex patterns with `regex:` — e.g. `regex:def\s+\w+\(`
- Without the prefix, `\|`, `\s`, etc. are treated as literal characters

---

## Best Practices

**Patching:**
- Use the MINIMUM `old_text` needed for a unique match — shorter = more resilient
- Verify uniqueness by searching the file with `-fs` or Ctrl+F before writing the patch
- For blocks longer than ~12 lines, use `***WILDCARD_PROMPTPACK***`
- Always put all patches and `promptpack -c` in the same bash block

**File Selection:**
- Mark only what the AI actually needs
- Use `ctags.txt` for a high-level overview plus the embedded AI instructions
- Use `i` (import deps) to pull in full dependency graphs for Python projects
- Let the AI use `-r` directly for any file it needs — no separate packaging step required

**Search:**
- Batch as many `-r`, `-n`, `-s`, `-fs` calls as you know you need before running `-c`
- Use `regex:` prefix explicitly for any regex patterns

**Summaries & Work Log:**
- End every patch task with `--summary "about" --rating N` plus a verbose heredoc before the closing `-c` — skip it only when purely repairing a failed patch or running a plain `-u` undo
- Rate honestly: 3 for architecture, data formats, workflow rules or decisions future work must respect (rare), 2 for a new feature or noticeable behavior change, 1 for bugfixes, docs and cosmetics; when unsure, pick the lower. The test: would an AI that only sees the `# WORKLOG` go wrong or redo work without this entry?
- Keep the `about` argument to 1–2 dense sentences of plain prose (no double quotes, backticks or `$`); it is what the AI sees in the `# WORKLOG`
- Write summary text for a reader with zero context: name every file touched and explain why, not just what
- Remember `-us` only flags a summary's own record — it never undoes code. Use `-u <PATCHID>` for that, one patch at a time
- Get oriented from the `# WORKLOG` in `ctags.txt` without pulling code into context, then `-log <ID...>` for summaries worth reading in full and `-ph <PATCHID...>` for the specific patches worth a closer look; use `-completelog` when the filtered view is not enough, and `-w` only when you truly need every summary in full

---

## License

PromptPack is free software, released under the [GNU General Public License v3.0](LICENSE) (GPL-3.0). You may use, study, modify and share it. If you distribute a modified version, it must also be released under the GPL v3 with its source code available. See the [LICENSE](LICENSE) file for the full text.

The GPL applies to PromptPack itself. Using PromptPack on your own projects does not make those projects subject to the GPL.

---

## Credits

**By Andrej Fuera**

*Romans 8:28*
*"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."*

All thanks and praise be to Jesus. Always Jesus. All the time. All the way.
God bless you!
