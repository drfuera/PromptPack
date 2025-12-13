# PromptPack

Interactive TUI tool for bundling project files into a single `code.txt` file optimized for AI-assisted code modification. The AI returns bash commands that can be copy-pasted directly into the terminal to apply changes to multiple files at once.

## The Workflow

1. **Select files** with the interactive TUI
2. **Generate code.txt** with project context
3. **Send to any AI** (Claude, GPT, DeepSeek, etc.)
4. **Copy-paste the response** directly into your terminal
5. **All files are patched** in one go

## Why PromptPack?

✅ **AI-Agnostic**: Works with any LLM (Claude, GPT, DeepSeek, Qwen, etc.)  
✅ **Multi-file patches**: Modify 10+ files with a single copy-paste  
✅ **Exact replacements**: Python heredoc scripts ensure precise text replacement  
✅ **Zero configuration**: AI receives instructions and code structure automatically  
✅ **Persistent selections**: Your file choices are saved for quick regeneration

## Installation
```bash
# Clone and make executable
git clone <your-repo-url>
cd promptpack
chmod +x promptpack.py

# Install dependency
pip install tiktoken

# Optional: Add to PATH
sudo ln -s $(pwd)/promptpack.py /usr/local/bin/promptpack
```

## Usage

### Interactive Mode - Select Files
```bash
./promptpack.py
```

**Controls:**
- `↑↓`: Navigate tree
- `←→`: Collapse/Expand directories
- `Space`: Mark/unmark files
- `Enter`: Generate code.txt
- `q`: Quit

Mark the files relevant to your current task. Your selections are automatically saved.

### Quick Mode - Regenerate from Saved Selections
```bash
./promptpack.py -q
```

Instantly regenerates `code.txt` with your previously marked files. Perfect when you just need to refresh the context for a follow-up prompt.

## How It Works

### 1. Generate code.txt
```bash
./promptpack.py
# Mark your files, press Enter
```

### 2. Send to AI

Open `code.txt` and send it to any AI with your request:
```
The API endpoint should validate email format before saving.
Fix the timeout issue in the websocket handler.
```

### 3. Copy-Paste the Response

The AI returns executable bash commands:
```bash
python3 <<'EOF'
try:
    with open('api/validators.py', 'r') as f:
        content = f.read()
    content = content.replace('def validate_email(email):\n    return True', 
                              'def validate_email(email):\n    import re\n    pattern = r\'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$\'\n    return re.match(pattern, email) is not None')
    with open('api/validators.py', 'w') as f:
        f.write(content)
except Exception:
    raise SystemExit(1)
EOF
[ $? -eq 0 ] && echo -e "✅ api/validators.py" || echo -e "🔴 api/validators.py"

python3 <<'EOF'
try:
    with open('websocket/handler.py', 'r') as f:
        content = f.read()
    content = content.replace('timeout=30', 'timeout=60')
    with open('websocket/handler.py', 'w') as f:
        f.write(content)
except Exception:
    raise SystemExit(1)
EOF
[ $? -eq 0 ] && echo -e "✅ websocket/handler.py" || echo -e "🔴 websocket/handler.py"
```

Copy-paste this entire block into your terminal - both files are patched instantly.

## Output Format

`code.txt` includes:

1. **Instructions** - Tells AI to respond with bash heredoc scripts
2. **Project tree** - Visual structure of your codebase
3. **Source files** - All marked files with headers (`### ./path/to/file.py`)

The AI uses the project tree to understand file locations and the source code to generate exact text replacements.

## Token Analysis

After generation, see token counts and model compatibility:
```
✅ code.txt created!

Included 12 files
File size: 45,231 bytes
Tokensize: 10,847 tokens

Model capacity:
✅   8.5%    DeepSeek   (128k context)
✅   8.5%    Grok       (128k context)
✅  33.1%    GPT-4      (32k context)
✅   8.5%    GPT-5      (128k context)
✅   5.4%    Claude     (200k context)
✅   8.5%    Qwen       (128k context)
```

## Advanced Features

### Persistent Selections

Marked files are saved in `~/.promptpack` with absolute paths. Each project maintains its own selection set.
```bash
# Mark files for feature A
./promptpack.py
# ... mark files, press Enter

# Work on feature A
# ... multiple AI interactions

# Quickly regenerate context
./promptpack.py -q
```

### Smart Filtering

- **Text files only**: Binary files are automatically excluded
- **No hidden files**: Files starting with `.` are skipped
- **Permission handling**: Gracefully skips inaccessible directories

### Visual Indicators

- `[✓]` Marked file or fully marked directory
- `[◐]` Partially marked directory
- `[ ]` Unmarked
- `▶/▼` Collapsed/Expanded directory
- File sizes displayed for all items

## Real-World Example
```bash
# Working on authentication system
./promptpack.py
# Mark: auth/login.py, auth/session.py, models/user.py, api/auth.py

# Generate code.txt
# Send to AI: "Add rate limiting to login endpoint"

# AI responds with 3 heredoc scripts modifying different files
# Copy-paste the entire response into terminal
# All files patched in 2 seconds

# Later: Add another feature
./promptpack.py -q  # Regenerate with same files
# New prompt: "Add 2FA support"
# Repeat
```

## Why Heredoc Format?

Traditional AI code responses are hard to apply:
- ❌ Partial code snippets require manual integration
- ❌ "Replace lines 45-67" is error-prone
- ❌ Multiple files need multiple copy-pastes

With PromptPack:
- ✅ Complete file modifications
- ✅ Exact text replacement (no line numbers)
- ✅ Multiple files in one copy-paste
- ✅ Immediate feedback (✅/🔴 status)
- ✅ Works in any terminal

## Use Cases

- **Refactoring**: Update patterns across multiple files
- **Bug fixes**: Fix related issues in several modules
- **Feature addition**: Modify multiple components at once
- **Code modernization**: Update syntax/patterns throughout codebase
- **API changes**: Update all endpoint handlers simultaneously

## Tips

1. **Start small**: Mark only files relevant to current task
2. **Use quick mode**: Regenerate context for follow-up questions
3. **Check tokens**: Ensure you're within your model's limits
4. **Directory marking**: Space on a directory marks all files inside
5. **Trust the format**: AI learns the heredoc pattern from code.txt instructions

## License

CC BY
