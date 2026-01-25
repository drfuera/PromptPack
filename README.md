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
  - `code.txt` - Full source code with AI instructions
  - `ctags.txt` - Lightweight code structure overview

### 🔧 Advanced Patch Management
- **Precise text replacement**: Apply patches with exact old→new text matching
- **Smart matching algorithms**:
  - Exact matching (default)
  - Flexible whitespace matching
  - Tidy matching (immune to formatting variations)
- **Python syntax validation**: Auto-fixes indentation errors
- **Patch history**: Full undo/redo with F12 patch browser
- **Error handling**: Failed patches are logged to `clipboard.tmp`

### 🔍 Code Navigation & Search
- **File search**: Search across multiple files with wildcards or regex
- **Line extraction**: Read specific line ranges from files
- **Context search**: Find text and extract surrounding lines
- **Clipboard integration**: All results copied to clipboard automatically

### 🧹 Code Maintenance
- **Tidy files**: Remove trailing whitespace and normalize empty lines
- **Batch operations**: Process multiple files with wildcard patterns

---

## Installation

### Requirements
- Python 3.6+
- Universal Ctags (for ctags mode)
- Clipboard utility: `xclip`, `xsel`, or `pbcopy`

### Install Dependencies

Ubuntu/Debian:
```bash
sudo apt install python3 python3-pip universal-ctags xclip
pip3 install tiktoken
```

macOS:
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

Launch interactive file browser:
```bash
promptpack
```

Navigate with arrow keys, press Space to mark/unmark files, press F1 to generate code.txt, press F2 to generate ctags.txt, press F12 to view patch history, press q to quit.

### Quick Code Generation

Generate code.txt from saved .promptpack selections:
```bash
promptpack -q
```

Add specific files and generate code.txt:
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
| `Space` | Mark/unmark file or folder |
| `F1` | Generate code.txt |
| `F2` | Generate ctags.txt |
| `F12` | View patch history |
| `q` | Quit |

### 📝 Patching Files

Basic patch format:
```bash
cat <<'PATCH' | promptpack -p "path/to/file.py" "Short description"
old text that exists in file
exactly as it appears
---SPLIT---
new text to replace it
with correct formatting
PATCH
```

Multiple patches in one command:
```bash
cat <<'PATCH' | promptpack -p "file1.py" "Fix bug in main"
old_code_1
---SPLIT---
new_code_1
PATCH

cat <<'PATCH' | promptpack -p "file2.py" "Add error handling"
old_code_2
---SPLIT---
new_code_2
PATCH

# Copy all results to clipboard
promptpack -c
```

Patch requirements:
- Description: Max 10 words
- `old_text`: Must match EXACTLY (including whitespace)
- `old_text`: Must be UNIQUE in the file (appear only once)
- Separator: `---SPLIT---` between old and new text

### 🔍 Search Operations

Search in files (recursive):
```bash
# Literal search
promptpack -fs "def main" "*.py"

# Wildcard search
promptpack -fs "class *Player*" "game*.py"

# Regex search
promptpack -fs "regex:def\s+\w+\(" "*.py"

# Copy results to clipboard
promptpack -c
```

Search and extract context:
```bash
# Find text and grab 10 lines before, 20 lines after
promptpack -s "function_name" 10,20 path/to/file.py

# Regex search with context
promptpack -s "regex:^class\s+\w+" 15,30 file.py

# Copy results to clipboard
promptpack -c
```

Read specific lines:
```bash
# Read lines 100-150
promptpack -n 100,150 path/to/file.py

# Batch read from multiple files
promptpack -n 10,20 file1.py
promptpack -n 50,75 file2.py
promptpack -c
```

Read entire file:
```bash
promptpack -r path/to/file.py
promptpack -c
```

### 🧹 Code Maintenance

Tidy files (remove trailing whitespace, normalize empty lines):
```bash
# Single file
promptpack -t file.py

# Wildcard pattern
promptpack -t "*.py"
promptpack -t "src/*.js"

# Multiple patterns
promptpack -t "*.py" "*.js" "*.cpp"
```

### 📋 Clipboard Management

All read/search operations append to `clipboard.tmp`. Use `-c` to copy everything to clipboard and clear the temp file.

Example workflow:
```bash
promptpack -r file1.py
promptpack -n 100,150 file2.py
promptpack -fs "def main" "*.py"
promptpack -c  # Copy all to clipboard and remove temp file
```

---

## AI Workflow Integration

### The PromptPack Workflow

1. Mark your files using interactive mode or `-a` flag
2. Generate code.txt with AI instructions embedded
3. Send to AI assistant (Claude, GPT-4, DeepSeek, etc.)
4. AI responds with patches in PromptPack format
5. Apply patches automatically with bash script
6. Review results in F12 patch history
7. Undo/redo patches as needed

### Special AI Commands (Embedded in code.txt)

When working with AI assistants, use these commands:

| Command | Description |
|---------|-------------|
| `#patch` | Start patching mode - AI generates patch commands |
| `#ask` | Question mode - AI answers without code changes |
| `#undo` | Revert last applied patch |
| `#reset` | Revert all patches, back to original code.txt |
| `#outsource` | AI creates prompt for another AI to solve problem |
| `#done` | Wrap up session with summary for next conversation |

### Example AI Interaction

User sends: #patch Add error handling to the login function

AI responds with:
```bash
cat <<'PATCH' | promptpack -p "auth/login.py" "Add error handling"
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

User then runs the bash script to apply the patch.

---

## Configuration

### File Selection Storage

File selections are stored in `~/.promptpack` (global) with absolute paths. This allows you to:
- Work on multiple projects
- Maintain separate file selections per project
- Quickly regenerate code.txt with `promptpack -q`

### Patch History

Patches are stored in `patch.json` in your project directory. Press `F12` in interactive mode to browse and toggle patches.

Example patch.json structure:
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

PromptPack uses three levels of text matching:

1. Exact match (fastest): Exact character-by-character matching
2. Flexible whitespace: Matches with varying spaces/tabs/newlines
3. Tidy matching: Normalizes formatting before matching

This makes patches resilient to whitespace variations while maintaining precision.

### Python Syntax Auto-Fix

For `.py` files, PromptPack automatically:
- Validates syntax after patching
- Fixes common indentation errors
- Aborts patch if syntax errors remain

### Token Estimation

Real-time token counting for AI model compatibility:

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

### Common Issues

"Universal Ctags is not installed!"
```bash
sudo apt install universal-ctags  # Ubuntu/Debian
brew install universal-ctags       # macOS
```

"Could not copy to clipboard"

Install: `xclip` (Linux), `xsel` (Linux), or `pbcopy` (macOS)
```bash
sudo apt install xclip  # Ubuntu/Debian
```

Patch fails: "Old text not found"
- Search `code.txt` for the current code
- Copy EXACT text including whitespace
- Use minimal unique text (1-3 lines)
- Check for tab vs space differences

Patch fails: "Old text appears N times"
- Add more context to make `old_text` unique
- Include surrounding lines or unique identifiers

### Best Practices

Patching:
- Use MINIMUM old_text needed for unique match
- Verify uniqueness by searching the file first
- Keep descriptions under 10 words
- Batch related patches in one bash script

File Selection:
- Mark only files the AI needs to see
- Use ctags.txt for quick project overview
- Use code.txt for detailed work
- Review token counts before sending to AI

Search:
- Use wildcards for flexible matching: `*init*`
- Use regex for complex patterns: `regex:^class\s+\w+`
- Batch multiple searches before `-c` clipboard copy

---

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

## License

This project is open source. See LICENSE file for details.

---

## Credits

**By Andrej Fuera**

*Romans 8:28*  
*"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."*

Special thanks to Jesus. Always Jesus. All the time. All the way.  
God bless you!
