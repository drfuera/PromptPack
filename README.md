# PromptPack

**Interactive file packer for AI-assisted development workflows**

PromptPack helps you prepare your codebase for AI conversations by creating structured compilations of your source files. It includes an interactive TUI for file selection, patch management for tracking changes, and seamless integration with clipboard tools.

## Features

- 🌳 **Interactive Tree Browser** - Navigate and select files with an intuitive curses-based interface
- 📦 **Smart File Packing** - Generate code.txt with complete file contents and project structure
- 🏷️ **Ctags Integration** - Create ctags.txt with symbol definitions for better code understanding
- 🔧 **Patch Management** - Track, apply, revert, and reapply code changes with full history
- 💾 **Persistent Selection** - Save file selections in .promptpack for quick regeneration
- 📋 **Clipboard Integration** - Copy file contents and patch results directly to clipboard
- 📊 **Token Counting** - Estimate token usage for different AI models (GPT-4, Claude, DeepSeek, etc.)

## Installation

### Prerequisites

- Python 3.6+
- Universal Ctags
- tiktoken (pip install tiktoken)
- Clipboard tool: xclip, xsel, or pbcopy

### Install Universal Ctags

#### Ubuntu/Debian
```bash
sudo apt install universal-ctags
```

#### macOS
```bash
brew install universal-ctags
```

### Install Python Dependencies

```bash
pip install tiktoken
```

### Download and Setup

```bash
wget https://raw.githubusercontent.com/drfuera/PromptPack/main/promptpack.py
chmod +x promptpack.py
```

Optionally, move to PATH:
```bash
sudo mv promptpack.py /usr/local/bin/promptpack
```

## Usage

### Interactive Mode

Launch the TUI browser to select files:

```bash
python3 promptpack.py
```

**Navigation:**
- ↑↓: Move cursor
- ←→: Collapse/expand directories
- Space: Mark/unmark files
- F1: Generate code.txt
- F2: Generate ctags.txt
- F12: View patch history
- q: Quit

### Quick Mode

Generate code.txt from previously saved .promptpack:

```bash
promptpack -q
```

### Add Files Directly

Add specific files to .promptpack and generate code.txt:

```bash
promptpack -a file1.py file2.py src/main.py
```

### Patch Management

Apply a patch (modify a file):

```bash
promptpack -p "path/to/file.py" "Fix bug in parser" "old code here" "new code here"
```

**Rules:**
- Description max 10 words
- Old text must match EXACTLY (including whitespace)
- Old text must be unique in the file (appear only once)

View patch history and revert/reapply changes:

```bash
Press F12 in interactive mode
```

### Read Files to Clipboard

Read entire file:

```bash
promptpack -r path/to/file.py
```

Read specific lines (with line numbers):

```bash
promptpack -n 10,20 path/to/file.py
```

Copy clipboard buffer and clear:

```bash
promptpack -c
```

## AI Workflow Integration

### Generated Files

**code.txt** - Complete source code with:
- Project tree structure
- Full file contents with headers (### ./path/to/file)
- Instructions for #patch command usage

**ctags.txt** - Symbol definitions with:
- Project structure
- Function/class/variable definitions
- File organization overview

### Using with AI Models

1. **Select Files**: Use interactive mode or -a to mark relevant files
2. **Generate Pack**: Press F1 for code.txt or F2 for ctags.txt
3. **Upload to AI**: Share the generated file with your AI assistant
4. **Apply Patches**: Use the AI's patch commands to modify code

### Patch Command Format for AI

When working with AI assistants, they can generate patches using:

```bash
promptpack -p "relative/path" "Short description" "exact old text" "exact new text"
promptpack -p "relative/path" "Short description" "exact old text" "exact new text"
promptpack -c
```

The -c flag at the end copies all results to clipboard and cleans up temporary files.

### Debugging with AI

View file contents:
```bash
promptpack -r relative/path
promptpack -c
```

View specific lines:
```bash
promptpack -n 10,20 relative/path
promptpack -n 66,80 relative/path
promptpack -c
```

## File Format

### .promptpack

Stores absolute paths of selected files (one per line):
```bash
/home/user/project/src/main.py
/home/user/project/src/utils.py
/home/user/project/tests/test_main.py
```

### patch.json

Tracks all patches with full history:
```bash
[
  {
    "id": 1,
    "timestamp": "2025-12-22T10:30:00",
    "filepath": "/path/to/file.py",
    "description": "Fix parser bug",
    "old_text": "original code",
    "new_text": "fixed code",
    "applied": true
  }
]
```

## Tips and Best Practices

1. **Start with ctags.txt** for large projects - gives AI an overview before diving into full code
2. **Use patch management** - track all changes for easy rollback
3. **Mark incrementally** - start with core files, add more as needed
4. **Check token counts** - ensure your pack fits within model limits
5. **Use -q for repetition** - quickly regenerate after updating .promptpack
6. **Leverage clipboard integration** - streamline your workflow with -c flag

## Model Token Limits

PromptPack shows capacity for:

- **Claude**: 200,000 tokens
- **DeepSeek**: 128,000 tokens
- **Grok**: 128,000 tokens
- **GPT-5**: 128,000 tokens (expected)
- **Qwen**: 128,000 tokens
- **GPT-4**: 32,768 tokens

## Examples

### Scenario 1: New Project Analysis

```bash
# Launch interactive mode
python3 promptpack.py

# Navigate and mark key files
# Press F2 to generate ctags.txt

# Share ctags.txt with AI to get project overview
```

### Scenario 2: Bug Fix with Patches

```bash
# Generate code.txt with relevant files
promptpack -a src/parser.py src/lexer.py tests/test_parser.py

# Work with AI, apply suggested patches
promptpack -p "src/parser.py" "Fix token handling" "old code" "new code"
promptpack -c

# Review patch history if needed
python3 promptpack.py
# Press F12 in TUI
```

### Scenario 3: Iterative Development

```bash
# Initial setup
promptpack -a main.py utils.py

# Make changes, regenerate quickly
promptpack -q

# Add more files as project grows
promptpack -a tests/test_utils.py
```

## Troubleshooting

**"ctags not found"**
- Install universal-ctags (not exuberant-ctags)

**"Could not copy to clipboard"**
- Install xclip (Linux), xsel (Linux), or ensure pbcopy works (macOS)

**"Old text not found in file"**
- Ensure exact match including all whitespace and newlines
- Use promptpack -r to view current file contents

**"Old text appears N times"**
- Text must be unique in file
- Make the old_text more specific to match only once

## Credits

By Andrej Fuera

Romans 8:28
"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."

Special thanks to Jesus. Always Jesus. All the time. All the way.

God bless you!

## License

CC BY
