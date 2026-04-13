# PromptPack

**A powerful CLI tool for AI-assisted development workflows**

PromptPack helps you efficiently package source code for AI assistants (Claude, GPT-4, DeepSeek, etc.) and manage AI-generated patches with precision. Built for developers who want to leverage AI coding assistance while maintaining full control over their codebase.

---

## Features

### 📦 Smart Code Packaging

- **Interactive TUI**: Navigate your project tree with keyboard shortcuts
- **Selective file marking**: Choose exactly which files to include
- **Token counting**: Real-time token estimation for different AI models
- **Persistent selection**: Your file selections are saved in `.promptpack`
- **Two output modes**:
  - `code.txt` — Full source code with embedded AI workflow instructions
  - `ctags.txt` — Lightweight code structure overview via Universal Ctags

### 🔧 Advanced Patch Management

- **Precise text replacement**: Apply patches with exact old→new text matching
- **Three-level smart matching**:
  - Exact matching (default)
  - Flexible whitespace matching (immune to space/tab variations)
  - Tidy matching (normalizes blank lines and trailing whitespace before matching)
- **Wildcard patching**: Skip large middle sections using `***WILDCARD_PROMPTPACK***`
- **Python syntax validation**: Auto-detects and fixes indentation errors after patching
- **Patch history**: Full undo/redo support with F12 patch browser
- **Error logging**: Failed patches are written to `clipboard.tmp` for review

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

---

## Installation

### Requirements

- Python 3.6+
- Universal Ctags (for ctags mode)
- Clipboard utility: `xclip`, `xsel`, or `pbcopy`
- `tiktoken` Python package

### Install Dependencies

**Ubuntu/Debian:**
```bash
sudo apt install python3 python3-pip universal-ctags xclip
pip3 install tiktoken
```

**macOS:**
```bash
brew install universal-ctags
pip3 install tiktoken
```

### Install PromptPack

```bash
# Clone the repository
git clone https://github.com/drfuera/PromptPack.git
cd PromptPack

# Make executable
chmod +x promptpack.py

# Optional: Add to PATH
sudo ln -s "$(pwd)/promptpack.py" /usr/local/bin/promptpack
```

---

## Quick Start

### Interactive Mode

Launch the interactive file browser:

```bash
promptpack
```

Navigate with arrow keys, mark files with `Space`, generate `code.txt` with `F1`, `ctags.txt` with `F2`, browse patch history with `F12`, quit with `q`.

### Quick Code Generation

Generate `code.txt` from saved `.promptpack` selections:

```bash
promptpack -q
```

Add specific files and generate `code.txt` in one step:

```bash
promptpack -a file1.py file2.py src/module.py
```

---

## Usage Guide

### 🎯 Interactive TUI Controls

| Key | Action |
|-----|--------|
| `↑↓` | Navigate files/folders |
| `←→` | Collapse/expand folders |
| `Space` | Mark/unmark file or folder (marks all children) |
| `i` | Mark file + all local Python import dependencies |
| `F1` | Generate `code.txt` |
| `F2` | Generate `ctags.txt` |
| `F12` | Browse and toggle patch history |
| `q` | Quit |

---

### 📝 Patching Files

**Basic patch format:**

```bash
cat <<'PATCH' | promptpack -p "path/to/file.py" "Short description"
old text that exists in file
exactly as it appears
---SPLIT---
new text to replace it
PATCH

promptpack -c
```

**Multiple patches — always end batch with `promptpack -c`:**

```bash
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
```

**Patch requirements:**
- Description: max 10 words
- `old_text`: must match EXACTLY (including all whitespace and newlines)
- `old_text`: must be UNIQUE in the file (appear only once)
- Separator: `---SPLIT---` on its own line between old and new text

---

### 🧩 Wildcard Patching

When `old_text` spans more than a dozen lines, use `***WILDCARD_PROMPTPACK***` as a placeholder to skip the middle section. Only the prefix and suffix need to be unique together.

```bash
cat <<'PATCH' | promptpack -p "path/to/file.py" "Replace large block"
first 2-5 unique lines of old_text
***WILDCARD_PROMPTPACK***
last 2-5 unique lines of old_text
---SPLIT---
complete new replacement text goes here
PATCH

promptpack -c
```

**Wildcard rules:**
- Use only **one** `***WILDCARD_PROMPTPACK***` per patch block
- The prefix + suffix combination must match exactly once in the file
- `***WILDCARD_PROMPTPACK***` is **not** valid in `new_text`, only in `old_text`

---

### 🔍 Search Operations

**Search across files (recursive by default):**

```bash
# Literal search
promptpack -fs "def main" "*.py"

# Wildcard search
promptpack -fs "class *Player*" "game*.py"

# Regex search
promptpack -fs "regex:def\s+\w+\(" "*.py"

promptpack -c
```

**Find text and extract surrounding context:**

```bash
# Grab 10 lines before and 20 lines after the match
promptpack -s "function_name" 10,20 path/to/file.py

# Regex match with context
promptpack -s "regex:^class\s+\w+" 15,30 file.py

promptpack -c
```

**Read specific line ranges:**

```bash
promptpack -n 100,150 path/to/file.py
promptpack -n 10,20 file1.py
promptpack -n 50,75 file2.py
promptpack -c
```

**Read entire file:**

```bash
promptpack -r path/to/file.py
promptpack -c
```

> All `-r`, `-n`, `-s`, and `-fs` results accumulate in `clipboard.tmp`. Always end a batch with `promptpack -c` to copy everything to clipboard and clear the temp file.

---

### 🧹 Code Maintenance

```bash
# Tidy a single file
promptpack -t file.py

# Tidy with wildcard pattern
promptpack -t "*.py"
promptpack -t "src/*.js"

# Multiple patterns at once
promptpack -t "*.py" "*.js" "*.cpp"

# Recursively tidy ALL text files in entire project
promptpack -tr
```

Tidy removes trailing whitespace from every line and collapses consecutive empty lines down to a maximum of one.

---

### 📋 Clipboard Management

All read and search operations append to `clipboard.tmp`. Use `-c` to copy all accumulated output to the system clipboard and delete the temp file.

```bash
promptpack -r file1.py
promptpack -n 100,150 file2.py
promptpack -fs "def main" "*.py"
promptpack -c   # Copy all results to clipboard, remove clipboard.tmp
```

---

## AI Workflow Integration

### The PromptPack Workflow

1. Mark your files using interactive mode or `-a`
2. Generate `code.txt` — AI instructions are embedded automatically
3. Send to your AI assistant (Claude, GPT-4, DeepSeek, Grok, etc.)
4. AI responds with patches in PromptPack format
5. Copy-paste and run the bash block to apply all patches at once
6. Review results in the F12 patch history browser
7. Undo/redo individual patches as needed

### Special AI Commands (Embedded in code.txt)

| Command | Description |
|---------|-------------|
| `#patch` | Patching mode — AI generates patch commands |
| `#ask` | Question mode — AI answers without writing code |
| `#undo` | Revert the last applied patch |
| `#reset` | Revert all patches back to the original `code.txt` state |
| `#outsource` | AI writes a detailed prompt for another AI to solve the problem |
| `#dumb` | Rewrite the last message in plain non-technical language |
| `#done` | Wrap up session — AI generates a `PROMPTPACK Summary` for the next context window |

### Example AI Interaction

User: `#patch Add error handling to the login function`

AI responds with:

```bash
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

promptpack -c
```

User runs the bash block — patch is applied and result is copied to clipboard.

---

## Configuration

### File Selection Storage

Selections are stored in `~/.promptpack` as absolute paths, scoped per project. This allows multiple projects to maintain independent selections on the same machine. Use `promptpack -q` to regenerate `code.txt` without opening the TUI.

### Patch History

Patches are stored in `patch.json` in the project directory. Open the browser with `F12` in interactive mode to inspect, unapply, or reapply any patch.

```json
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
```

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

Press `i` on any `.py` file in the TUI to automatically mark it along with all locally resolvable `import` dependencies. Pressing `i` again toggles all dependencies off. This ensures `code.txt` always contains the full dependency graph needed for AI context.

### Token Estimation

Live token counts are shown in the status bar and printed after `code.txt` is generated:

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

```bash
sudo apt install universal-ctags   # Ubuntu/Debian
brew install universal-ctags        # macOS
```

### "Could not copy to clipboard"

Install a clipboard utility:

```bash
sudo apt install xclip   # Ubuntu/Debian
```

Or use `xsel` (Linux) or `pbcopy` (macOS, built-in).

### Patch fails: "Old text not found"

- Search `code.txt` for the current exact code
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
- Verify uniqueness by searching the file or `code.txt` with Ctrl+F before writing the patch
- For blocks longer than ~12 lines, use `***WILDCARD_PROMPTPACK***`
- Always put all patches and `promptpack -c` in the same bash block

**File Selection:**
- Mark only what the AI actually needs
- Use `ctags.txt` for an initial high-level overview
- Use `i` (import deps) to pull in full dependency graphs for Python projects

**Search:**
- Batch as many `-r`, `-n`, `-s`, `-fs` calls as you know you need before running `-c`
- Use `regex:` prefix explicitly for any regex patterns

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

Special thanks to Jesus. Always Jesus. All the time. All the way.
God bless you!
