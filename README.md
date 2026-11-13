# PromptPack

**A powerful CLI tool for AI-assisted development workflows**

PromptPack helps you package your codebase for AI assistants (Claude, GPT, DeepSeek, etc.) and apply AI-generated patches with precision. Built for developers who want AI coding assistance while keeping full control over their codebase.

---

## Features

### 📦 Smart Code Packaging

- **Interactive TUI**: Navigate your project tree with keyboard shortcuts
- **Selective file marking**: Choose exactly which files to include
- **Token counting**: Real-time token estimation for different AI models
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

- **Summary history (`--summary "about text"`)**: Save a timestamped changelog entry to `summary.json` after each completed task. The quoted argument is a 1–2 sentence, information-dense `about` line; the heredoc on stdin holds the verbose text explaining what changed and why, for future AI sessions or human reviewers. Both parts are required — a call missing either one is rejected and nothing is saved
- **Mark a summary reverted (`-us`)**: Flags a summary entry as `reverted` in `summary.json` — a historical annotation only. It never touches any patch or any code; undoing actual code changes is always done explicitly, one patch at a time, via `-u`
- **Work log (`-w`)**: Combine `patch.json` + `summary.json` into a lightweight `work.txt` — a PATCH TOC (date, ID, file, description) up top, followed by the full chronological log (full summary text + compact one-line patch entries, no code embedded)
- **Patch history lookup (`-ph`)**: Fetch full old/new code for one or more specific `PATCHID`s on demand — lets the AI use `work.txt`'s dates and descriptions to decide what's worth a closer look, without ever needing to read all of `patch.json` directly
- **`# WORKLOG` in `ctags.txt`**: Every time `ctags.txt` is generated it ends with a compact, chronological worklog — one line per applied patch (`ID PATCH:description`) and one per summary (`ID LOG:about`), with each patch listed just before the LOG that closes its task. It gives the AI a cheap overview of the whole project history; usually only the last few entries matter
- **Summary lookup (`-log`)**: Fetch the full text (and `about` line) of one or more summaries by ID, space- or comma-separated (`-log 53 54 55`), so the AI pulls only the summaries it needs instead of reading all of `work.txt`

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

### ↩️ Undoing and Redoing Patches

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
cat <<'SUMMARY' | promptpack --summary "Dense 1-2 sentence about: files touched, what changed, why."
Explain what changed in each file and why, for a reader with zero context.
SUMMARY
promptpack -c
````

The quoted argument is the `about` line. It is stored separately in `summary.json` and listed in the `# WORKLOG` section of `ctags.txt`, so keep it to 1–2 sentences, as information-dense as possible. Use plain prose only — no double quotes, backticks or `$` inside it, because the shell interprets them inside double quotes. The heredoc holds only the verbose text. If either part is missing the call is rejected immediately, with an error in `clipboard.tmp`, and nothing is saved.

**Fetch full summaries by ID (IDs come from the `# WORKLOG` section in `ctags.txt`):**

````bash
promptpack -log 53 54 55
promptpack -c
````

IDs can be space- or comma-separated (`-log 53,54,55`). Missing IDs are reported without failing the ones that were found. Use `-ph` for the code of a specific patch — LOG and PATCH IDs are separate number series.

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

### 🖥️ Running Shell Commands

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

All read, search, and execute operations append to `clipboard.tmp`. Use `-c` to copy all accumulated output to the system clipboard and delete the temp file.

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
9. The `# WORKLOG` at the bottom of `ctags.txt` gives the AI a compact overview of all earlier work; it fetches full summaries with `-log <ID...>` and full patch code with `-ph <PATCHID...>` only when needed
10. Run `-w` any time to rebuild `work.txt`, the complete chronological changelog; it grows large on long projects, so the worklog plus `-log` is the preferred way in

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
| `#test` | Structured review in three modes: `#test` (this session's patches), `#test <target>` (a named function, class or file) and `#test full` (whole codebase, one module per round) — fixed passes (requirements, contracts, boundary values, pre-mortem, security, consistency), report only, no patches until you approve |
| `#name` | Suggest a short (3–8 word) internal codename for the current version/problem — for reference only, never written into code |
| `#done` | Wrap up session — AI generates a `PROMPTPACK Summary` for the next context window |

### Reviewing Changes with `#test`

`#test` has three modes. Plain `#test` reviews the patches the AI wrote in the current session plus directly affected code (callers and callees; it may read one or two clearly relevant imported files, but does not wander further). `#test <target>` reviews a named function, class or file, whether or not it changed this session, plus directly affected code. `#test full` covers the whole codebase, but never in a single reply: the AI plans from the ctags list, prioritizes risky parts such as parsing, file I/O and shell calls, reviews one module per round, and states plainly what was reviewed and what was not reached. `full` is a reserved word, so it cannot be used as a target name.

In session mode the AI knows its own patches from the `[PATCHID n]` lines you pasted back. Only if the session was restarted via `#done` does it fall back to the patch IDs under the latest `LOG` lines of the `# WORKLOG`, fetched with `-ph`. In every mode it reads the actual code with `-r`/`-n`, because patching can auto-correct indentation and the file may differ from the patch text.

Seven reasoning passes run in a fixed order, each using the results of the earlier ones: scope, requirements coverage, Design by Contract, boundary analysis, pre-mortem, OWASP/CWE/CERT (only if input, files, paths, shell or parsing are touched) and consistency/design. In session mode the requirements pass asks whether the change did exactly what was asked; if not, passes 3-7 are skipped but you still get a report. In `<target>` and `full` mode there is no request to compare with, so the code is compared with its purpose (docstring, README, function name) or the pass is skipped with a stated reason. Callers of changed functions are listed as `SUSPECTED` in the scope pass and checked by a search in the verification block. The check that the summary matches the patches applies only in session mode. The AI may skip a pass only by stating a reason in one line. Every finding has file and line, severity (bug, risk, minor remark) and status `VERIFIED` or `SUSPECTED`; bugs come with a concrete triggering input.

Then comes a single verification block: all `SUSPECTED` findings are collected into one bash block (`-r`, `-n`, `-s`, `-fs`, `-e`, for example `pyflakes`/`ruff`, tests or caller searches). Even with no `SUSPECTED` findings the block holds at least a syntax check such as `py_compile` of the files under review. You run it once and paste the output back, and the AI delivers the final report. No patches are written during `#test`; fixes come only after your okay, as a normal `#patch`.

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

cat <<'SUMMARY' | promptpack --summary "login() in auth/login.py now catches lookup and password-check failures and logs them instead of crashing."
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

Task summaries are stored in `summary.json` in the project directory, written via `--summary` after each completed task. Each entry has a separate `about` field (the quoted `--summary` argument) next to the verbose `text` (the heredoc). Entries created before `about` existed simply lack the field.

````json
[
  {
    "id": 1,
    "timestamp": "2025-01-25T10:35:00",
    "text": "Added error handling to login() in auth/login.py...",
    "about": "login() in auth/login.py now catches lookup and password-check failures and logs them."
  }
]
````

`-us <SUMMARYID>` sets `"reverted": true` (plus a `reverted_at` timestamp) on the matching entry. This is a historical annotation only — it never deletes the entry and never touches `patch.json` or any file on disk. To undo the actual code changes a summary describes, undo each relevant `PATCHID` explicitly with `-u`.

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

As `patch.json` and `summary.json` grow on a long-running project, reading them in full can eat a large chunk of an AI's context window. Instead, `ctags.txt` ends with a compact `# WORKLOG`: chronological, one line per applied patch (`ID PATCH:description`) and per summary (`ID LOG:about`), with each patch listed just before the LOG that closes its task. The AI scans it for orientation, then fetches only what matters — `-log <ID...>` for full summaries and `-ph <PATCHID...>` for full patch code — keeping context usage proportional to what's actually relevant. LOG and PATCH IDs are separate number series, and the WORKLOG is regenerated whenever `ctags.txt` is (`F1`).

`-w` still builds the complete `work.txt` (a PATCH TOC plus the full chronological log with full summary text and one-line patch entries, never code) for when the whole history is needed, but it grows large on long projects.

### Token Estimation

Live token counts are shown in the status bar and printed after `ctags.txt` is generated:

| Model | Max Tokens |
|-------|-----------|
| Claude | 200,000 |
| DeepSeek | 128,000 |
| Grok | 128,000 |
| GPT-5 | 128,000 |
| Qwen | 128,000 |
| GPT-4 | 32,768 |

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
- End every patch task with `--summary "about"` plus a verbose heredoc before the closing `-c` — skip it only when purely repairing a failed patch or running a plain `-u` undo
- Keep the `about` argument to 1–2 dense sentences of plain prose (no double quotes, backticks or `$`); it is what the AI sees in the `# WORKLOG`
- Write summary text for a reader with zero context: name every file touched and explain why, not just what
- Remember `-us` only flags a summary's own record — it never undoes code. Use `-u <PATCHID>` for that, one patch at a time
- Get oriented from the `# WORKLOG` in `ctags.txt` without pulling code into context, then `-log <ID...>` for summaries worth reading in full and `-ph <PATCHID...>` for the specific patches worth a closer look; reserve `-w` for when you truly need the whole history

---

## Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

## License

This project is open source. See the LICENSE file for details.

---

## Credits

**By Andrej Fuera**

*Romans 8:28*
*"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."*

All thanks and praise be to Jesus. Always Jesus. All the time. All the way.
God bless you!
