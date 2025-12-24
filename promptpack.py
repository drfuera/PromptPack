"""
	https://github.com/drfuera/PromptPack

	By Andrej Fuera
	
	Romans 8:28
	"And we know that in all things God works for the good of those who love him, who have been called according to his purpose."

	Special thanks to Jesus. Always Jesus. All the time. All the way.
	God bless you!
"""
#!/usr/bin/env python3
import os
import sys
import curses
from pathlib import Path
import tiktoken
import argparse
import shutil
import subprocess
import json
from datetime import datetime
import subprocess
import shutil

PROMPTPACK_FILE = Path.home() / '.promptpack'
PATCH_HISTORY_FILE = Path('patch.json')
CLIPBOARD_TMP_FILE = Path('clipboard.tmp')
TEXT_CHECK_BYTES = 8192

def check_ctags():
    if not shutil.which('ctags'):
        print("❌ Error: Universal Ctags is not installed!")
        print("\nPlease install it with:")
        print("  sudo apt install universal-ctags")
        sys.exit(1)

class TreeNode:
    def __init__(self, path, is_dir=False, parent=None):
        self.path = Path(path)
        self.name = self.path.name if self.path.name else str(self.path)
        self.is_dir = is_dir
        self.parent = parent
        self.children = []
        self.expanded = False
        self.marked = False
        self.size = 0
        
    def calculate_size(self):
        if not self.is_dir:
            try:
                self.size = self.path.stat().st_size
            except:
                self.size = 0
        else:
            self.size = sum(child.calculate_size() for child in self.children)
        return self.size
    
    def format_size(self):
        size = self.size
        for unit in ['B', 'K', 'M', 'G']:
            if size < 1024.0:
                return f"{size:4.0f}{unit}"
            size /= 1024.0
        return f"{size:4.0f}T"
    
    def has_partial_marks(self):
        if not self.is_dir:
            return False
        
        marked_count = 0
        total_count = 0
        
        def count_marks(node):
            nonlocal marked_count, total_count
            if not node.is_dir:
                total_count += 1
                if node.marked:
                    marked_count += 1
            else:
                for child in node.children:
                    count_marks(child)
        
        count_marks(self)
        return 0 < marked_count < total_count
        
    def toggle_expand(self):
        if self.is_dir:
            self.expanded = not self.expanded
            
    def toggle_mark(self):
        self.marked = not self.marked
        if self.is_dir and self.marked:
            self._mark_all_children(True)
        elif self.is_dir and not self.marked:
            self._mark_all_children(False)
    
    def _mark_all_children(self, mark_state):
        for child in self.children:
            child.marked = mark_state
            if child.is_dir:
                child._mark_all_children(mark_state)

def calculate_tokens(text):
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except:
        return len(text) // 4

def is_text_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(TEXT_CHECK_BYTES)
            return b'\x00' not in chunk
    except:
        return False

def load_promptpack():
    if not PROMPTPACK_FILE.exists():
        return set()
    
    try:
        cwd = Path.cwd().resolve()
        paths = set()
        
        with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                path = Path(line)
                
                if path.is_absolute():
                    abs_path = path.resolve()
                else:
                    continue
                
                try:
                    abs_path.relative_to(cwd)
                    if abs_path.exists():
                        paths.add(abs_path)
                except (ValueError, OSError):
                    pass
        
        return paths
    except:
        return set()

def save_promptpack(marked_files):
    try:
        cwd = Path.cwd().resolve()
        
        existing_other_projects = set()
        if PROMPTPACK_FILE.exists():
            with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    path = Path(line)
                    if not path.is_absolute():
                        continue
                    
                    abs_path = path.resolve()
                    
                    try:
                        abs_path.relative_to(cwd)
                    except ValueError:
                        if abs_path.exists():
                            existing_other_projects.add(str(abs_path))
        
        all_paths = existing_other_projects | {str(f.resolve()) for f in marked_files}
        
        with open(PROMPTPACK_FILE, 'w', encoding='utf-8') as f:
            for path in sorted(all_paths):
                f.write(f"{path}\n")
                
    except Exception as e:
        pass

def read_lines_to_clipboard(line_range, filepath):
    """Läs specifika rader och kopiera till clipboard"""
    filepath = Path(filepath)
    
    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg
    
    try:
        start, end = map(int, line_range.split(','))
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if start < 1 or end > len(lines) or start > end:
            error_msg = f"Invalid range {start},{end} (file has {len(lines)} lines)"
            return False, error_msg
        
        header = f"\n------ {filepath} ------\n\n"
        selected_with_numbers = header
        for i, line in enumerate(lines[start-1:end], start=start):
            selected_with_numbers += f"{i}: {line}"
        
        success_msg = f"✅ Read lines {start}-{end} from {filepath}"
        append_to_clipboard_tmp(selected_with_numbers)
        return True, success_msg
            
    except ValueError:
        error_msg = f"Invalid range format: {line_range} (use: start,end)"
        return False, error_msg
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        return False, error_msg

def read_file_to_clipboard(filepath):
    """Läs fil och kopiera till clipboard"""
    filepath = Path(filepath)
    
    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        success_msg = f"✅ Read {len(content)} bytes from {filepath}"
        append_to_clipboard_tmp(content)
        return True, success_msg
            
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        return False, error_msg

def append_to_clipboard_tmp(message):
    """Lägg till meddelande till clipboard.tmp"""
    try:
        with open(CLIPBOARD_TMP_FILE, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
        return True
    except Exception as e:
        print(f"Warning: Could not write to clipboard.tmp: {e}")
        return False

def copy_clipboard_tmp_to_clipboard():
    """Kopiera innehållet av clipboard.tmp till clipboard"""
    try:
        if not CLIPBOARD_TMP_FILE.exists():
            return False
        
        with open(CLIPBOARD_TMP_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return copy_to_clipboard(content)
    except Exception as e:
        print(f"Warning: Could not read clipboard.tmp: {e}")
        return False

def copy_to_clipboard(text):
    """Kopiera text till clipboard"""
    try:
        if shutil.which('xclip'):
            subprocess.run(['xclip', '-selection', 'clipboard'], 
                         input=text.encode(), check=True)
            return True
        elif shutil.which('xsel'):
            subprocess.run(['xsel', '--clipboard', '--input'], 
                         input=text.encode(), check=True)
            return True
        elif shutil.which('pbcopy'):
            subprocess.run(['pbcopy'], input=text.encode(), check=True)
            return True
    except:
        pass
    return False

def load_patch_history():
    """Ladda patch historik från JSON"""
    if not PATCH_HISTORY_FILE.exists():
        return []
    try:
        with open(PATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load patch history: {e}")
        return []

def save_patch_history(history):
    """Spara patch historik till JSON"""
    try:
        with open(PATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving patch history: {e}")
        return False

def get_next_patch_id():
    """Få nästa lediga patch ID"""
    history = load_patch_history()
    if not history:
        return 1
    return max(p['id'] for p in history) + 1

def apply_patch(filepath, description, old_text, new_text):
    """
    Applicera en patch och spara i historiken
    Returns: (success: bool, message: str)
    """
    filepath = Path(filepath).resolve()
    
    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg
    
    words = description.split()
    if len(words) > 10:
        error_msg = f"[{filepath}] Description too long ({len(words)} words, max 10)"
        return False, error_msg
    
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        if old_text not in original_content:
            error_msg = f"[{filepath}] Old text not found in file"
            return False, error_msg
        
        count = original_content.count(old_text)
        if count > 1:
            error_msg = f"[{filepath}] Old text appears {count} times in file (must be unique)"
            return False, error_msg
        
        new_content = original_content.replace(old_text, new_text)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        history = load_patch_history()
        patch_id = get_next_patch_id()
        
        patch_entry = {
            'id': patch_id,
            'timestamp': datetime.now().isoformat(),
            'filepath': str(filepath),
            'description': description,
            'old_text': old_text,
            'new_text': new_text,
            'applied': True
        }
        
        history.append(patch_entry)
        save_patch_history(history)
        
        success_msg = f"Patch #{patch_id} applied successfully"
        append_to_clipboard_tmp(success_msg)
        return True, success_msg
        
    except Exception as e:
        error_msg = f"[{filepath}] Error: {e}"
        return False, error_msg

def unapply_patch(patch_id):
    """
    Reversa en patch
    Returns: (success: bool, message: str)
    """
    history = load_patch_history()
    
    patch = None
    for p in history:
        if p['id'] == patch_id:
            patch = p
            break
    
    if not patch:
        return False, f"Patch #{patch_id} not found"
    
    if not patch['applied']:
        return False, f"Patch #{patch_id} is already unapplied"
    
    filepath = Path(patch['filepath'])
    if not filepath.exists():
        return False, f"File not found: {filepath}"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if patch['new_text'] not in content:
            return False, f"Cannot unpatch: new text not found in file"
        
        content = content.replace(patch['new_text'], patch['old_text'])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        patch['applied'] = False
        save_patch_history(history)
        
        success_msg = f"Patch #{patch_id} unapplied successfully"
        copy_to_clipboard(success_msg)
        return True, success_msg
        
    except Exception as e:
        error_msg = f"Error: {e}"
        copy_to_clipboard(error_msg)
        return False, error_msg

def reapply_patch(patch_id):
    """
    Återapplicera en patch
    Returns: (success: bool, message: str)
    """
    history = load_patch_history()
    
    patch = None
    for p in history:
        if p['id'] == patch_id:
            patch = p
            break
    
    if not patch:
        return False, f"Patch #{patch_id} not found"
    
    if patch['applied']:
        return False, f"Patch #{patch_id} is already applied"
    
    filepath = Path(patch['filepath'])
    if not filepath.exists():
        return False, f"File not found: {filepath}"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if patch['old_text'] not in content:
            return False, f"Cannot reapply: old text not found in file"
        
        content = content.replace(patch['old_text'], patch['new_text'])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        patch['applied'] = True
        save_patch_history(history)
        
        success_msg = f"Patch #{patch_id} reapplied successfully"
        copy_to_clipboard(success_msg)
        return True, success_msg
        
    except Exception as e:
        error_msg = f"Error: {e}"
        copy_to_clipboard(error_msg)
        return False, error_msg

def mark_from_promptpack(root, promptpack_paths):
    def mark_node(node):
        if not node.is_dir:
            abs_path = node.path.resolve()
            if abs_path in promptpack_paths:
                node.marked = True
        else:
            for child in node.children:
                mark_node(child)
            
            file_children = [child for child in node.children if not child.is_dir]
            
            if file_children:
                all_marked = all(child.marked for child in file_children)
                if all_marked:
                    node.marked = True
    
    mark_node(root)

def build_tree(root_path, load_marks=True):
    root_path = Path(root_path).resolve()
    
    if not root_path.exists():
        return None
    
    root = TreeNode(root_path, is_dir=True)
    root.expanded = True
    
    def populate(node):
        if not node.is_dir:
            return
        
        try:
            entries = sorted(node.path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                
                if entry.is_file() and not is_text_file(entry):
                    continue
                
                child = TreeNode(entry, is_dir=entry.is_dir(), parent=node)
                node.children.append(child)
                if child.is_dir:
                    populate(child)
        except PermissionError:
            pass
    
    populate(root)
    root.calculate_size()
    
    if load_marks:
        promptpack_paths = load_promptpack()
        if promptpack_paths:
            mark_from_promptpack(root, promptpack_paths)
    
    return root

def flatten_visible_tree(root):
    visible = []
    
    def traverse(node, depth=0):
        visible.append((node, depth))
        if node.is_dir and node.expanded:
            for child in node.children:
                traverse(child, depth + 1)
    
    traverse(root)
    return visible

def get_marked_files(node, result=None):
    if result is None:
        result = []
    
    if not node.is_dir and node.marked:
        result.append(node.path)
    
    if node.is_dir:
        for child in node.children:
            get_marked_files(child, result)
    
    return result

def calculate_total_tokens(marked_files):
    total_tokens = 0
    for file_path in marked_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                total_tokens += calculate_tokens(content)
        except:
            pass
    return total_tokens

def write_project_tree(out, root):
    """Skriv ut projektstruktur med tree-kommandot om det finns, annars manuellt"""
    # Försök använda tree-kommandot först
    try:
        # Kör tree-kommandot (exkludera dolda filer)
        result = subprocess.run(
            ['tree', '--noreport', '--charset=utf8', '.'],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            out.write(result.stdout)
            return
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Fallback: skapa träd manuellt
    def write_tree_manual(node, prefix="", is_last=True):
        if node.parent is None:
            out.write(f"{node.name}/\n")
        else:
            connector = "└── " if is_last else "├── "
            out.write(f"{prefix}{connector}{node.name}{'/' if node.is_dir else ''}\n")
        
        if node.is_dir:
            children = [c for c in node.children]
            for idx, child in enumerate(children):
                extension = "    " if is_last else "│   "
                new_prefix = prefix + extension if node.parent else ""
                write_tree_manual(child, new_prefix, idx == len(children) - 1)
    
    write_tree_manual(root)

def show_patch_history(stdscr):
    """Visa patch historik och tillåt unpatch/repatch"""
    curses.curs_set(0)
    history = load_patch_history()
    
    if not history:
        stdscr.clear()
        stdscr.addstr(0, 0, "No patches in history", curses.A_BOLD)
        stdscr.addstr(2, 0, "Press any key to return...")
        stdscr.refresh()
        stdscr.getch()
        return
    
    selected = 0
    scroll = 0
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        title = "Patch History - ↑↓: Navigate | Space: Toggle | q: Back"
        stdscr.addstr(0, 0, title.ljust(width-1)[:width-1], curses.A_REVERSE)
        
        header = f"{'ID':<5} {'Status':<10} {'Date':<20} {'Description':<60} {'File'}"
        try:
            stdscr.addstr(1, 0, header[:width-1], curses.A_BOLD)
        except curses.error:
            pass
        
        display_height = height - 3
        for i in range(display_height):
            idx = scroll + i
            if idx >= len(history):
                break
            
            patch = history[idx]
            status = "✓ Applied " if patch['applied'] else "○ Unapplied"
            date = patch['timestamp'][:19].replace('T', ' ')
            desc = patch['description'][:60]
            filepath = Path(patch['filepath']).name
            
            line = f"{patch['id']:<5} {status:<10} {date:<20} {desc:<60} {filepath}"
            
            attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            if patch['applied']:
                attr |= curses.color_pair(1)
            
            try:
                stdscr.addstr(i + 2, 0, line[:width-1], attr)
            except curses.error:
                pass
        
        stdscr.refresh()
        key = stdscr.getch()
        
        if key == ord('q') or key == ord('Q'):
            break
        elif key == curses.KEY_UP:
            selected = max(0, selected - 1)
            if selected < scroll:
                scroll = selected
        elif key == curses.KEY_DOWN:
            selected = min(len(history) - 1, selected + 1)
            if selected >= scroll + display_height:
                scroll = selected - display_height + 1
        elif key == ord(' '):
            patch = history[selected]
            
            stdscr.clear()
            stdscr.addstr(0, 0, "Processing...", curses.A_BOLD)
            stdscr.refresh()
            
            if patch['applied']:
                success, msg = unapply_patch(patch['id'])
            else:
                success, msg = reapply_patch(patch['id'])
            
            history = load_patch_history()
            
            stdscr.clear()
            color = curses.color_pair(1) if success else curses.color_pair(2)
            stdscr.addstr(0, 0, msg, color | curses.A_BOLD)
            stdscr.addstr(2, 0, "Press any key to continue...")
            stdscr.refresh()
            stdscr.getch()

def draw_tree(stdscr, root, selected_idx, scroll_offset):
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    
    visible_nodes = flatten_visible_tree(root)
    
    title = "↑↓: Navigate | ←→: Expand | Space: Mark | F1: code | F2: ctags | F12: patches | q: Quit"
    stdscr.addstr(0, 0, title.ljust(width-1)[:width-1], curses.A_REVERSE)
    
    display_height = height - 2
    for i in range(display_height):
        line_idx = scroll_offset + i
        if line_idx >= len(visible_nodes):
            break
        
        node, depth = visible_nodes[line_idx]
        
        size_str = node.format_size()
        indent = "  " * depth
        
        if node.is_dir:
            icon = "▶ " if not node.expanded else "▼ "
        else:
            icon = "  "
        
        if node.marked:
            mark = "[✓] "
            mark_color = curses.color_pair(1)
        elif node.is_dir and node.has_partial_marks():
            mark = "[◐] "
            mark_color = curses.color_pair(2)
        else:
            mark = "[ ] "
            mark_color = curses.A_NORMAL
        
        line_prefix = f"{size_str} {indent}{icon}"
        line_suffix = node.name
        
        full_line = f"{line_prefix}{mark}{line_suffix}"
        if len(full_line) > width - 1:
            line_suffix = line_suffix[:width - len(line_prefix) - len(mark) - 4] + "..."
        
        base_attr = curses.A_REVERSE if line_idx == selected_idx else curses.A_NORMAL
        
        try:
            stdscr.addstr(i + 1, 0, line_prefix, base_attr)
            
            col = len(line_prefix)
            if base_attr == curses.A_REVERSE:
                stdscr.addstr(i + 1, col, mark, mark_color | curses.A_REVERSE)
            else:
                stdscr.addstr(i + 1, col, mark, mark_color)
            
            col += len(mark)
            name_attr = base_attr
            if node.marked:
                name_attr |= curses.A_BOLD
            stdscr.addstr(i + 1, col, line_suffix, name_attr)
        except curses.error:
            pass
    
    marked_files = get_marked_files(root)
    total_tokens = calculate_total_tokens(marked_files)
    
    status = f"Marked: {len(marked_files)} files | Tokensize: {total_tokens:,} tokens"
    try:
        stdscr.addstr(height - 1, 0, status[:width-1], curses.A_REVERSE)
    except curses.error:
        pass
    
    stdscr.refresh()

def create_code_file(root):
    marked_files = get_marked_files(root)
    
    if not marked_files:
        return False
    
    marked_files = sorted(marked_files, key=lambda x: str(x))
    
    with open('code.txt', 'w', encoding='utf-8') as out:
        out.write("""The following instructions apply if command #patch is given:
Analyze the attached text document with collected source code which is only a compilation, not a target file.
Interpretation of target file should be done via headers in the form ### ./relative/path.

If a file exists in the project structure below but is not included in this document, and you need to see it to complete the task, ask for that file before proceeding and it will be given to you.

Return patch commands using the promptpack -p format with stdin that make exact text replacements in files.
For each change needed, use the promptpack patch command.
Number every #patch incrementally starting with #1.

Always put all promptpack commands in same bash as 'promptpack -c' depends on it.
Each command is run separately and we temporarily store the result of them.
By ensuring 'promptpack -c' is added to the end of each bash window, we make sure all result date is copied to clipboard and the tmp file is removed.

Rules:
- Description must be max 10 words
- Old_text must match EXACTLY (including all whitespace and newlines)
- Old_text must be unique in the file (appear only once)
- Use ---SPLIT--- to separate old and new text
- stdin handles all special characters safely (quotes, newlines, etc.)

Format for patching files:
```bash
cat <<'PATCH1' | promptpack -p "relative/path" "Short description"
exact old text here
with all whitespace preserved
---SPLIT---
exact new text here
with all whitespace preserved
PATCH1

cat <<'PATCH2' | promptpack -p "relative/path" "Short description"
another old text
---SPLIT---
another new text
PATCH2

promptpack -c
```

Viewing complete file contents for debugging:
```bash
promptpack -r relative/path
promptpack -r relative/path
promptpack -c
```

Or specific lines (with line numbers):
```bash
promptpack -n 10,20 relative/path
promptpack -n 66,80 relative/path
promptpack -n 190,250 relative/path
promptpack -c
```

Format for directory creation:
```bash
mkdir -p relative/path/to/folder
```

For removal (soft-delete):
```bash
mv relative/path relative/path_deleted
```

If tree structure is needed:
```bash
tree
```

Important:
- Use promptpack -p for all file changes
- Description max 10 words
- old_text must match EXACTLY (including all whitespace)
- old_text must be unique (appear only once in file)
- All patches in one code block
- Number patches: #patch 1, #patch 2, etc.

Additional notes:
If we use command #reset this implies that all changes hav been reverted back to the original state.
You will disregard all changes made by patches created during the chat session and fall back and start working from the source found in code.txt again.

If we use the command #undo this implies that the last patch was reverted and undone, falling back to code before the patch was applied.

Fallback:
If you find yourself not being able to solve an issue, trying multiple times and coming to the conclusion that you're stuck do not write a patch to restore the code back to the state of code.txt.
Instead let user know that you want to #reset the code and if there are any patches produced in the conversation that are of importance/use, number each patch and instruct user to apply them after resetting the code, for example;
We're not getting anywhere, please #reset the code and apply #patch 2, 9, 12, 13 and 22. Let me know when you are ready and we can proceed.

## Project Structure
""")
        
                
        write_project_tree(out, root)
        out.write("\n")
        for file_path in marked_files:
            rel_path = file_path.relative_to(Path.cwd())
            out.write(f"\n### ./{rel_path}\n\n")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"# Error reading file: {e}\n")
    
    return True

def create_ctags_file(root):
    marked_files = get_marked_files(root)
    
    if not marked_files:
        return False
    
    marked_files = sorted(marked_files, key=lambda x: str(x))
    
    with open('ctags.txt', 'w', encoding='utf-8') as out:
        out.write("""These are all the files of the project listed with Universal Ctags.
Understand the user request, what files are available and what they contain.
Draw conclusions what you need from the project to achieve the users goals.
Once you know what files you need, let the user prepare the package of files for you.
```bash
promptpack -a requiredfile.ext requiredfile2.ext path/requiredfile3.ext
```

Note: In the interactive mode, press F1 for code.txt or F2 for ctags.txt

Here is the complete structure of the project and all the relevant files.
Some files might not be included in the ctags list so you need to draw conclusions on what files do what based on their file names and what the user wants to achieve.
If there are any files not listed in the ctags list but you suspect you also need them, please include them in the 'promptpack -a' command.
If you for some reason later on find you need additional files from the project, you can always ask the user for a new 'promptpack -a' with the additional files you require.

## Project Structure
""")

                
        write_project_tree(out, root)
        for file_path in marked_files:
            try:
                rel_path = file_path.relative_to(Path.cwd())
                result = subprocess.run(
                    ['ctags', '-x', str(rel_path)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if result.stdout:
                    out.write(f"\n### {rel_path}\n")
                    for line in result.stdout.splitlines():
                        parts = line.split(None, 4)
                        if len(parts) >= 5:
                            out.write(
                                f"{parts[0]}\t{parts[1]}\t{parts[2]}\t{parts[4]}\n"
                            )

            except subprocess.CalledProcessError:
                pass
            except Exception as e:
                out.write(f"\n### {file_path.relative_to(Path.cwd())}\n")
                out.write(f"# Error running ctags: {e}\n")
    
    return True

def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    
    root = build_tree(".")
    if not root:
        return None
    
    selected_idx = 0
    scroll_offset = 0
    
    while True:
        height, width = stdscr.getmaxyx()
        visible_nodes = flatten_visible_tree(root)
        
        display_height = height - 2
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + display_height:
            scroll_offset = selected_idx - display_height + 1
        
        draw_tree(stdscr, root, selected_idx, scroll_offset)
        key = stdscr.getch()
        

        if key == ord('q') or key == ord('Q'):
            return None
        elif key == curses.KEY_F1:  # F1 för code.txt
            marked_files = get_marked_files(root)
            if marked_files:
                save_promptpack(marked_files)
                create_code_file(root)
                return ('code', len(marked_files))
            else:
                return ('code', 0)
        elif key == curses.KEY_F2:  # F2 för ctags.txt
            marked_files = get_marked_files(root)
            if marked_files:
                save_promptpack(marked_files)
                create_ctags_file(root)
                return ('ctags', len(marked_files))
            else:
                return ('ctags', 0)
        elif key == curses.KEY_F12:
            show_patch_history(stdscr)
        elif key == curses.KEY_UP:
            selected_idx = max(0, selected_idx - 1)
        elif key == curses.KEY_DOWN:
            selected_idx = min(len(visible_nodes) - 1, selected_idx + 1)
        elif key == curses.KEY_RIGHT:
            if selected_idx < len(visible_nodes):
                node, _ = visible_nodes[selected_idx]
                if node.is_dir and not node.expanded:
                    node.toggle_expand()
        elif key == curses.KEY_LEFT:
            if selected_idx < len(visible_nodes):
                node, _ = visible_nodes[selected_idx]
                if node.is_dir and node.expanded:
                    node.toggle_expand()
        elif key == ord(' '):
            if selected_idx < len(visible_nodes):
                node, _ = visible_nodes[selected_idx]
                node.toggle_mark()
                marked_files = get_marked_files(root)
                save_promptpack(marked_files)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Interactive directory navigator')
    parser.add_argument('-q', '--quick', action='store_true', 
                        help='Create code.txt directly from .promptpack without interactive mode')
    parser.add_argument('-a', '--add', nargs='+', metavar='FILE',
                        help='Add specified files to .promptpack and create code.txt')

    parser.add_argument('-p', '--patch', nargs=2, metavar=('FILE', 'DESC'),
                        help='Apply patch reading old/new text from stdin (format: OLD_TEXT\n---SPLIT---\nNEW_TEXT)')
    parser.add_argument('-r', '--read', metavar='FILE',
                        help='Read file and copy to clipboard')
    parser.add_argument('-n', '--lines', nargs=2, metavar=('RANGE', 'FILE'),
                        help='Read specific lines (e.g., 10,20) and copy to clipboard')
    parser.add_argument('-c', '--clear', action='store_true',
                        help='Copy clipboard.tmp to clipboard and remove the file')
    args = parser.parse_args()
    
    if args.clear:
        if CLIPBOARD_TMP_FILE.exists():
            if copy_clipboard_tmp_to_clipboard():
                try:
                    CLIPBOARD_TMP_FILE.unlink()
                    print("✅ Removed clipboard.tmp")
                    sys.exit(0)
                except Exception as e:
                    print(f"✅ File copied but could not remove: {e}")
                    sys.exit(0)
            else:
                print("❌ Could not copy to clipboard (install xclip, xsel, or pbcopy)")
                sys.exit(1)
        else:
            print("❌ clipboard.tmp not found")
            sys.exit(1)
    
    if args.read:
        success, message = read_file_to_clipboard(args.read)
        print(message)
        if success and copy_clipboard_tmp_to_clipboard():
            pass
        sys.exit(0 if success else 1)
    
    if args.lines:
        line_range, filepath = args.lines
        success, message = read_lines_to_clipboard(line_range, filepath)
        print(message)
        if success and copy_clipboard_tmp_to_clipboard():
            pass
        sys.exit(0 if success else 1)
    
    if args.patch:
        filepath, description = args.patch
        
        # Read from stdin
        stdin_content = sys.stdin.read()
        
        # Split on ---SPLIT---
        parts = stdin_content.split('---SPLIT---')
        if len(parts) != 2:
            print("❌ Error: stdin must contain OLD_TEXT---SPLIT---NEW_TEXT")
            sys.exit(1)
        
        old_text = parts[0]
        new_text = parts[1]
        
        success, message = apply_patch(filepath, description, old_text, new_text)
        
        if success:
            print(f"✅ {message}")
            if copy_clipboard_tmp_to_clipboard():
                pass
            sys.exit(0)
        else:
            print(f"❌ {message}")
            sys.exit(1)
    
    check_ctags()
    
    if args.add:
        cwd = Path.cwd().resolve()
        new_files = set()
        
        for file_str in args.add:
            file_path = Path(file_str).resolve()
            if not file_path.exists():
                print(f"❌ File not found: {file_str}")
                continue
            if not file_path.is_file():
                print(f"❌ Not a file: {file_str}")
                continue
            if not is_text_file(file_path):
                print(f"❌ Not a text file: {file_str}")
                continue
            new_files.add(file_path)
        
        if not new_files:
            print("❌ No valid files to add!")
            sys.exit(1)
        
        existing_paths = set()
        if PROMPTPACK_FILE.exists():
            with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        path = Path(line)
                        if path.exists():
                            existing_paths.add(path.resolve())
        
        all_paths = existing_paths | new_files
        with open(PROMPTPACK_FILE, 'w', encoding='utf-8') as f:
            for path in sorted(all_paths):
                f.write(f"{path}\n")
        
        print(f"✅ Added {len(new_files)} file(s) to .promptpack")
        
        root = build_tree(".", load_marks=False)
        if not root:
            print("❌ Could not read directory structure!")
            sys.exit(1)
        
        mark_from_promptpack(root, new_files)
        marked_files = get_marked_files(root)
        
        if not marked_files:
            print("❌ No valid files found!")
            sys.exit(1)
        
        create_code_file(root)
        
        try:
            with open('code.txt', 'r', encoding='utf-8') as f:
                content = f.read()
            total_tokens = calculate_tokens(content)
            file_size = len(content)
            
            print(f"✅ code.txt created!")
            print(f"\nIncluded {len(marked_files)} files")
            print(f"File size: {file_size:,} bytes")
            print(f"Tokensize: {total_tokens:,} tokens")
            print(f"\nModel capacity:")
            
            models = {
                'DeepSeek': 128000,
                'Grok': 128000,
                'GPT-4': 32768,
                'GPT-5': 128000,
                'Claude': 200000,
                'Qwen': 128000
            }
            
            for model, max_tokens in models.items():
                pct = (total_tokens / max_tokens) * 100
                status = '✅' if total_tokens <= max_tokens else '🔴'
                print(f"{status} {pct:5.1f}%\t{model}")
                
        except Exception as e:
            print(f"❌ Error reading code.txt: {e}")
            sys.exit(1)
    
    elif args.quick:
        promptpack_paths = load_promptpack()
        
        if not promptpack_paths:
            print("❌ No files in .promptpack!")
            sys.exit(1)
        
        root = build_tree(".", load_marks=False)
        if not root:
            print("❌ Could not read directory structure!")
            sys.exit(1)
        
        mark_from_promptpack(root, promptpack_paths)
        
        marked_files = get_marked_files(root)
        if not marked_files:
            print("❌ No valid files found from .promptpack!")
            sys.exit(1)
        
        create_code_file(root)
        
        try:
            with open('code.txt', 'r', encoding='utf-8') as f:
                content = f.read()
            total_tokens = calculate_tokens(content)
            file_size = len(content)
            
            print(f"✅ code.txt created!")
            print(f"\nIncluded {len(marked_files)} files")
            print(f"File size: {file_size:,} bytes")
            print(f"Tokensize: {total_tokens:,} tokens")
            print(f"\nModel capacity:")
            
            models = {
                'DeepSeek': 128000,
                'Grok': 128000,
                'GPT-4': 32768,
                'GPT-5': 128000,
                'Claude': 200000,
                'Qwen': 128000
            }
            
            for model, max_tokens in models.items():
                pct = (total_tokens / max_tokens) * 100
                status = '✅' if total_tokens <= max_tokens else '🔴'
                print(f"{status} {pct:5.1f}%\t{model}")
                
        except Exception as e:
            print(f"❌ Error reading code.txt: {e}")
            sys.exit(1)
    else:
        result = curses.wrapper(main)
        
        if result is not None:
            file_type, file_count = result
            
            if file_count == 0:
                print("❌ No files marked!")
            else:
                filename = f"{file_type}.txt"
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    file_size = len(content)
                    total_tokens = calculate_tokens(content)
                    
                    print(f"✅ {filename} created!")
                    print(f"\nIncluded {file_count} files")
                    print(f"File size: {file_size:,} bytes")
                    print(f"Tokensize: {total_tokens:,} tokens")
                    print(f"\nModel capacity:")
                    
                    models = {
                        'DeepSeek': 128000,
                        'Grok': 128000,
                        'GPT-4': 32768,
                        'GPT-5': 128000,
                        'Claude': 200000,
                        'Qwen': 128000
                    }
                    
                    for model, max_tokens in models.items():
                        pct = (total_tokens / max_tokens) * 100
                        status = '✅' if total_tokens <= max_tokens else '🔴'
                        print(f"{status} {pct:5.1f}%\t{model}")
                        
                except Exception as e:
                    print(f"❌ Error reading {filename}: {e}")
