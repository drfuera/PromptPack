# PromptPack

**An intelligent code packaging tool for AI-assisted development**

PromptPack helps you efficiently share your codebase with AI assistants by intelligently selecting, packaging, and patching files. It features an interactive TUI, automatic token counting, and intelligent whitespace-aware patching.

---

## ✨ Features

### 📦 Code Packaging
- **Interactive File Selection**: Navigate your project structure with an intuitive TUI
- **Smart Filtering**: Automatically excludes binary files and hidden directories
- **Token Counting**: Real-time token estimation for various AI models (Claude, GPT-4, DeepSeek, etc.)
- **Persistent Selection**: Save your file selections in `.promptpack` for reuse

### 🧩 Intelligent Patching
- **Whitespace-Agnostic Matching**: Patches work even when AI gets indentation wrong
- **Format Preservation**: Maintains your file's original indentation and formatting
- **Atomic Operations**: All patches are tracked in `patch.json` with full history
- **Safe Replacements**: Ensures old text appears exactly once before applying changes
- **Undo/Redo Support**: Revert or reapply any patch via F12 history viewer

### 🛠️ Development Tools
- **File Reading**: Extract specific line ranges with `-n` flag
- **Clipboard Integration**: Automatic clipboard copying via `xclip`, `xsel`, or `pbcopy`
- **Project Tree Export**: Generate project structure with `tree` command integration
- **CTags Support**: Generate symbol listings for quick code navigation

---

## 📋 Requirements

- Python 3.6+
- Universal Ctags: `sudo apt install universal-ctags`
- Clipboard tool (optional): `xclip`, `xsel`, or `pbcopy`

**Python Dependencies:**
```bash
pip install tiktoken
```

---

## 🚀 Installation
```bash
git clone https://github.com/drfuera/PromptPack.git
cd PromptPack
chmod +x promptpack.py
sudo ln -s $(pwd)/promptpack.py /usr/local/bin/promptpack
```

---

## 📖 Usage

### Interactive Mode

Launch the TUI file selector:
```bash
promptpack
```

**Keyboard Shortcuts:**
- `↑↓`: Navigate files/folders
- `←→`: Collapse/expand folders
- `Space`: Mark/unmark files
- `F1`: Generate `code.txt` with selected files
- `F2`: Generate `ctags.txt` with symbol index
- `F12`: View patch history
- `q`: Quit

### Quick Mode

Generate `code.txt` from existing `.promptpack` selections:
```bash
promptpack -q
```

### Add Files

Add specific files to `.promptpack` and generate `code.txt`:
```bash
promptpack -a file1.py src/file2.js utils/helper.py
```

---

## 🔧 Patching Files

### Apply a Patch
```bash
cat <<'PATCH' | promptpack -p "relative/path/file.py" "Short description"
old text here
with exact formatting
---SPLIT---
new text here
with new formatting
PATCH
```

**Important Patch Rules:**
- Description must be **max 10 words**
- Old text must appear **exactly once** in the file
- Old text doesn't need exact whitespace - intelligent matching will find it!
- Use `---SPLIT---` to separate old and new text
- Supports all special characters (quotes, newlines, etc.)

### Example: Multiple Patches
```bash
cat <<'PATCH' | promptpack -p "app.py" "Add logging import"
import os
import sys
---SPLIT---
import os
import sys
import logging
PATCH

cat <<'PATCH' | promptpack -p "app.py" "Update function signature"
def process(data):
    return data
---SPLIT---
def process(data, verbose=False):
    if verbose:
        logging.info(f"Processing {len(data)} items")
    return data
PATCH

promptpack -c
```

The final `promptpack -c` copies all results to clipboard and cleans up temporary files.

---

## 📄 Reading Files

### Read Entire File
```bash
promptpack -r path/to/file.py
promptpack -c
```

### Read Specific Lines
```bash
promptpack -n 50,100 path/to/file.py
promptpack -c
```

**Auto-adjustment:** If you request lines beyond the file length (e.g., 96-130 when file has 125 lines), the range automatically adjusts to maintain the requested line count (becomes 91-125).

---

## 🗂️ Generated Files

### `code.txt`
Complete compilation of selected files with:
- Project structure tree
- File headers with relative paths
- Full source code content
- Instructions for AI on how to patch files

### `ctags.txt`
Symbol index of selected files with:
- Function/class definitions
- Method signatures
- Variable declarations
- Line numbers for quick navigation

### `.promptpack`
Stores absolute paths of marked files for reuse across sessions.

### `patch.json`
Tracks all applied patches with:
- Patch ID and timestamp
- File path and description
- Old and new text content
- Applied/unapplied status

---

## 🎯 Whitespace-Agnostic Patching

PromptPack intelligently handles whitespace mismatches:

**Your File:**
```python
def hello():
    print("Hello")    # 4 spaces
    return True
```

**AI's Patch (wrong indentation):**
```python
def hello():
  print("Hello")      # 2 spaces
  return True
```

**Result:** ✅ Patch applies successfully and **preserves your 4-space indentation**!

This solves a common problem where AI assistants copy code with incorrect indentation but you want to maintain your project's formatting standards.

---

## 📊 Token Counting

PromptPack shows real-time token usage for:

| Model | Context Window |
|-------|----------------|
| Claude | 200,000 tokens |
| GPT-4 | 32,768 tokens |
| GPT-5 | 128,000 tokens |
| DeepSeek | 128,000 tokens |
| Grok | 128,000 tokens |
| Qwen | 128,000 tokens |

Status indicators show if your package fits:
- ✅ Green: Fits within context
- 🔴 Red: Exceeds context limit

---

## 🔄 Patch Management

### View History
Press `F12` in interactive mode to view all patches with:
- Patch ID and timestamp
- Applied/unapplied status
- File path and description
- Toggle patches with `Space`

### Command Line History
```bash
# Patches are automatically tracked in patch.json
cat patch.json | jq '.'
```

---

## 💡 Workflow Example
```bash
# 1. Select files interactively
promptpack
# Press Space on files you need, F1 to generate code.txt

# 2. Share code.txt with AI assistant
# AI analyzes and suggests changes

# 3. Apply AI's suggested patches
cat <<'PATCH' | promptpack -p "src/main.py" "Fix bug in parser"
if data == None:
    return False
---SPLIT---
if data is None:
    return []
PATCH

# 4. Copy results to clipboard
promptpack -c

# 5. Review changes, iterate as needed
```

---

## 🎨 Icons in Output

- 🧩 - Patch successfully applied
- ✨ - New file created
- ✅ - Operation succeeded
- ❌ - Operation failed
- 🔴 - Context limit exceeded

---

## 📜 License

This project is dedicated to the glory of God.

**Romans 8:28**  
*"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."*

---

## 👨‍💻 Author

**Andrej Fuera**

Special thanks to Jesus. Always Jesus. All the time. All the way.  
God bless you!

---

## 🔗 Links

- **GitHub**: [https://github.com/drfuera/PromptPack](https://github.com/drfuera/PromptPack)
- **Issues**: [Report bugs or request features](https://github.com/drfuera/PromptPack/issues)
