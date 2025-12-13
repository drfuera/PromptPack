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

PROMPTPACK_FILE = Path.home() / '.promptpack'
TEXT_CHECK_BYTES = 8192

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
        for unit in ['B  ', 'KB ', 'MB ', 'GB ']:
            if size < 1024.0:
                return f"{size:6.1f}{unit}"
            size /= 1024.0
        return f"{size:6.1f}TB "
    
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

def draw_tree(stdscr, root, selected_idx, scroll_offset):
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    
    visible_nodes = flatten_visible_tree(root)
    
    title = "↑↓: Navigate | ←→: Collapse/Expand | Space: Mark | Enter: Create code.txt | q/Q: Quit"
    stdscr.addstr(0, 0, title[:width-1], curses.A_REVERSE)
    
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
        out.write("""The following instructions apply to future code unless otherwise requested:
Analyze the attached text document with collected source code which is only a compilation, not a target file.
Interpretation of target file should be done via headers in the form ### ./relative/path.

If a file exists in the project structure below but is not included in this document, and you need to see it to complete the task, ask for that file before proceeding.

Return Python commands (bash heredoc format) that make exact text replacements in the files.
For each file to be changed, create a Python script that:
1. Reads the entire file to a string
2. Uses .replace() to replace exact text strings
3. Writes back the entire content

Format:
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

If it's a new file to the project, create it with format:
```bash
cat <<'EOF' > relative/path
NEW_FILE_CONTENT
EOF
[ $? -eq 0 ] && echo -e "✅ relative/path" || echo -e "🔴 relative/path"
```

If errors occur and we need to troubleshoot:
```bash
python3 <<'EOF'
spec={'relative/path':(1,5),'relative/path':(5,20)}
for p,(a,b) in spec.items():
    print(f'==> {p} <==')
    L=open(p).readlines()
    for i in range(a,b):
        if i<len(L): print(f'{i+1}: {L[i]!r}')
EOF
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
- Use .replace() with EXACT text strings including newlines (\\n)
- Preserve all indentation and whitespace exactly
- No explanations, only heredoc/command
- All heredoc/command in one code block
- Text in replace() must match original EXACTLY (including all spaces and newlines)

## Project Structure
""")
        
        def write_tree(node, prefix="", is_last=True):
            if node.parent is None:
                out.write(f"{node.name}/\n")
            else:
                connector = "└── " if is_last else "├── "
                out.write(f"{prefix}{connector}{node.name}{'/' if node.is_dir else ''}\n")
                
            if node.is_dir and node.expanded:
                children = [c for c in node.children]
                for idx, child in enumerate(children):
                    extension = "    " if is_last else "│   "
                    new_prefix = prefix + extension if node.parent else ""
                    write_tree(child, new_prefix, idx == len(children) - 1)
        
        write_tree(root)
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
        elif key == ord('\n') or key == 10:
            marked_files = get_marked_files(root)
            if marked_files:
                save_promptpack(marked_files)
                create_code_file(root)
                return len(marked_files)
            else:
                return 0
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
    args = parser.parse_args()
    
    if args.quick:
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
            if result == 0:
                print("❌ No files marked!")
            else:
                try:
                    with open('code.txt', 'r', encoding='utf-8') as f:
                        content = f.read()
                    total_tokens = calculate_tokens(content)
                    file_size = len(content)
                    
                    print(f"✅ code.txt created!")
                    print(f"\nIncluded {result} files")
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
