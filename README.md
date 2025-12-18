# PromptPack

Interactive TUI tool for bundling project files into single -code.txt- or -ctags.txt- files optimized for AI-assisted code modification. Supports both direct file context (code.txt) and Universal Ctags analysis (ctags.txt) for different AI workflow needs.

## Features

- Interactive TUI - Navigate and select files with keyboard controls  
- Dual Output Formats - Generate -code.txt- for direct context or -ctags.txt- for code analysis  
- Persistent Selections - Automatically saves marked files in -~/.promptpack-  
- Token Analysis - Calculate token counts and model compatibility  
- Smart Filtering - Automatically excludes binary and hidden files  
- Quick Regeneration - Recreate files from saved selections  
- Batch File Addition - Add multiple files via command line  
- Tree Visualization - Project structure display with file sizes  
- Partial Directory Marks - Visual indicators for partially selected directories  

## Installation

```bash
# Clone repository
git clone https://github.com/drfuera/PromptPack.git
cd PromptPack

# Make executable
chmod +x promptpack.py

# Install Python dependencies
pip install tiktoken

# Install Universal Ctags (required)
sudo apt install universal-ctags

# Optional: Add to PATH
sudo ln -s $(pwd)/promptpack.py /usr/local/bin/promptpack
```

## Usage

### Interactive Mode (TUI)
```bash
./promptpack.py
```

**Controls:**
- -↑/↓- - Navigate up/down
- -←/→- - Collapse/Expand directories
- -Space- - Mark/unmark files/directories
- -F1- - Generate -code.txt- with marked files
- -F2- - Generate -ctags.txt- with marked files
- -q/Q- - Quit

### Quick Mode (Regenerate from Saved Selections)
```bash
# Regenerate code.txt from ~/.promptpack
./promptpack.py -q

# Regenerate ctags.txt from ~/.promptpack
# (Run in interactive mode and press F2)
```

### Add Files via Command Line
```bash
# Add specific files to promptpack and generate code.txt
./promptpack.py -a file1.py file2.js path/to/file3.html

# Multiple files with wildcards (using shell expansion)
./promptpack.py -a src/*.py tests/*.py
```

## Output Formats

### 1. code.txt
Contains full source code of selected files with instructions for AI to respond with bash heredoc scripts for precise file modifications.

**Structure:**
- Instructions for AI patch generation
- Project tree structure
- Full source files with headers (-- ./path/to/file.py-)

**AI Response Format:**
The AI returns executable bash commands using Python heredoc scripts:
```bash
python3 <<'EOF'
try:
    with open("relative/path", "r") as f:
        content = f.read()
    content = content.replace("exact old text", "exact new text")
    with open("relative/path", "w") as f:
        f.write(content)
except Exception:
    raise SystemExit(1)
EOF
[ $? -eq 0 ] && echo -e "✅ relative/path" || echo -e "🔴 relative/path"
```

### 2. ctags.txt
Contains Universal Ctags analysis of selected files for AI understanding of code structure, symbols, and relationships.

**Structure:**
- Instructions for AI to request specific files
- Project tree structure
- Ctags output for each file with symbol definitions

## Token Analysis

After generation, PromptPack displays token analysis:
```bash
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

## File Selection Persistence

Marked files are saved in -~/.promptpack- using absolute paths. Each project maintains its own selection set within the file. The format automatically filters paths to only include files from the current working directory.

### Managing Selections
- **Automatic**: Files marked in TUI are automatically saved
- **Manual Addition**: Use -a- flag to add specific files
- **Cross-Project**: File stores selections for multiple projects

## Visual Indicators in TUI

- -[✓]- - Fully marked file or directory (green)
- -[◐]- - Partially marked directory (yellow)
- -[ ]- - Unmarked
- -▶- - Collapsed directory
- -▼- - Expanded directory
- File sizes shown for all items

## Workflow Examples

### Example 1: Multi-file Refactoring
```bash
# 1. Select files interactively
./promptpack.py
# Mark: models/user.py, models/auth.py, api/endpoints.py

# 2. Generate context
Press F1 to create code.txt

# 3. Send to AI with request
"Change all database calls from sync to async using asyncpg"

# 4. Copy-paste AI response into terminal
# All files are modified simultaneously
```

### Example 2: Code Analysis with Ctags
```bash
# 1. Select files for analysis
./promptpack.py
# Mark: src/*.py

# 2. Generate ctags analysis
Press F2 to create ctags.txt

# 3. Send to AI
"Analyze the codebase and identify potential security issues"

# 4. AI can request specific files using:
# promptpack -a file1.py file2.py
```

### Example 3: Quick Batch Addition
```bash
# Add all Python files in src and tests
./promptpack.py -a src/*.py tests/*.py

# code.txt is automatically created
# Token analysis shown immediately
```

## Advanced Features

### Directory Operations
- Space on a directory toggles all files within
- Partial marks show as -[◐]- when some children are marked
- Directory sizes include all contained files

### Smart File Filtering
- Binary files automatically excluded
- Hidden files (starting with -.-) skipped
- Permission errors handled gracefully

### Patch Management
The AI instructions include -#reset- command for reverting changes:
```bash
If we use command #reset this implies that all changes have been reverted back to the original state.
You will disregard all changes made by patches created during the chat session.
```

### Cross-Platform Compatibility
- Works on Linux, macOS, and WSL
- UTF-8 encoding support
- Path normalization for different OSes

## Use Cases

1. **Large Refactoring** - Update patterns across 10+ files simultaneously
2. **API Version Updates** - Modify all endpoint handlers in one operation
3. **Security Patching** - Apply security fixes to multiple vulnerable files
4. **Library Migration** - Replace deprecated library calls throughout codebase
5. **Code Analysis** - Understand complex codebases using ctags analysis
6. **Feature Addition** - Add new functionality across multiple components
7. **Bug Fix Coordination** - Fix related issues in several modules at once

## Tips & Best Practices

1. **Start Small**: Begin with 3-5 core files for initial context
2. **Use Token Analysis**: Ensure you-re within your AI model-s context window
3. **Leverage Persistence**: Use -q- flag for follow-up questions
4. **Combine Approaches**: Use -ctags.txt- for analysis, then -code.txt- for modifications
5. **Check Output**: Always review AI-generated patches before execution
6. **Directory Strategy**: Mark directories when working on entire modules
7. **Backup First**: Ensure you have version control or backups before applying patches

## Troubleshooting

**"Universal Ctags is not installed!"**
```bash
sudo apt install universal-ctags  # Ubuntu/Debian
brew install universal-ctags      # macOS
```

**File not appearing in TUI**
- File may be binary (non-text)
- File may be hidden (starts with -.-)
- Check file permissions

**Token count discrepancies**
- Different tokenizers may give slightly different counts
- tiktoken-s cl100k_base encoding is used (same as GPT-4)

## License

CC BY

## Acknowledgments

Special thanks to Jesus. Always Jesus. All the time. All the way.
God bless you!
