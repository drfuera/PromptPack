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

import ast
import re
import fnmatch

PROMPTPACK_FILE = Path.home() / '.promptpack'
PATCH_HISTORY_FILE = Path('patch.json')
CLIPBOARD_TMP_FILE = Path('clipboard.tmp')
TEXT_CHECK_BYTES = 8192

def tidy_file(pattern):
    """Remove whitespace-only lines and reduce multiple empty lines to max 1"""
    import glob

    # Expand wildcard pattern
    matches = glob.glob(pattern, recursive=False)

    if not matches:
        return False, f"No files found matching pattern: {pattern}"

    results = []
    success_count = 0
    error_count = 0

    for filepath in matches:
        filepath = Path(filepath)

        if not filepath.is_file():
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Count original whitespace
            original_whitespace = sum(len(line) - len(line.rstrip()) for line in lines)
            original_lines = len(lines)

            tidied = []
            prev_empty = False
            removed_lines = 0

            for line in lines:
                stripped = line.rstrip()  # Remove trailing whitespace

                if not stripped:  # Line is empty or whitespace-only
                    if not prev_empty:  # Only add ONE empty line
                        tidied.append('')
                        prev_empty = True
                    else:
                        removed_lines += 1
                else:
                    tidied.append(stripped)
                    prev_empty = False

            # Write back with newlines
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(tidied))
                if tidied and tidied[-1]:  # Add final newline if file is not empty
                    f.write('\n')

            rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath
            stats = f"Removed {removed_lines} duplicate empty lines, {original_whitespace} trailing whitespace chars"
            results.append(f"✅ Tidied {rel_path} | {stats}")
            success_count += 1

        except Exception as e:
            results.append(f"❌ Error tidying {filepath}: {e}")
            error_count += 1

    summary = f"\n✅ Tidied {success_count} file(s)" + (f", ❌ {error_count} error(s)" if error_count > 0 else "")
    full_message = '\n'.join(results) + summary

    return error_count == 0, full_message

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
    """Read specific lines and copy to clipboard"""
    filepath = Path(filepath)

    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg

    try:
        start, end = map(int, line_range.split(','))

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Auto-adjust if end exceeds file length
        if end > len(lines):
            overflow = end - len(lines)
            start = max(1, start - overflow)
            end = len(lines)

        if start < 1 or start > end:
            error_msg = f"Invalid range {start},{end} (file has {len(lines)} lines)"
            return False, error_msg

        rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath
        header = f"\n------ {rel_path} ------\n"
        selected_with_numbers = header
        for i, line in enumerate(lines[start-1:end], start=start):
            selected_with_numbers += f"{i}: {line}"

        success_msg = f"✅ Read lines {start}-{end} from {rel_path}"
        append_to_clipboard_tmp(selected_with_numbers)
        return True, success_msg

    except ValueError:
        error_msg = f"Invalid range format: {line_range} (use: start,end)"
        return False, error_msg
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        return False, error_msg

def search_and_read_lines(search_string, offset_range, filepath):
    """Search for string and show lines with offset. Supports wildcards (* ?) and regex (prefix with 'regex:')"""
    filepath = Path(filepath)

    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg

    # Check if regex mode
    use_regex = search_string.startswith('regex:')
    if use_regex:
        search_string = search_string[6:]  # Remove 'regex:' prefix
        try:
            pattern = re.compile(search_string)
        except re.error as e:
            error_msg = f"❌ Invalid regex pattern: {e}"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

        def match_func(line):
            return pattern.search(line) is not None
    else:
        # Check if wildcards are used
        has_wildcards = '*' in search_string or '?' in search_string
        if has_wildcards:
            def match_func(line):
                return fnmatch.fnmatch(line, f"*{search_string}*")

        else:
            # Literal search - accept any characters
            def match_func(line):
                return search_string in line

    try:
        # Parse offset range (e.g., "10,30" means 10 lines before, 30 lines after)
        before, after = map(int, offset_range.split(','))
        before = abs(before)  # Make sure it's positive

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Find all occurrences using match function
        match_lines = []
        for i, line in enumerate(lines, start=1):
            if match_func(line):
                match_lines.append(i)

        if not match_lines:
            error_msg = f"String '{search_string}' not found in {filepath}"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

        # Use first match but note if not unique
        match_line = match_lines[0]
        is_unique = len(match_lines) == 1

        # Calculate start and end lines (before is negative offset, after is positive)
        start = max(1, match_line - before)
        end = min(len(lines), match_line + after)

        rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath

        search_type = "regex" if use_regex else ("wildcard" if has_wildcards else "literal")
        uniqueness_info = "" if is_unique else f" | Search pattern is not unique, has {len(match_lines)} hits"
        header = f"\n------ {rel_path} (found '{search_string}' [{search_type}] at line {match_line}{uniqueness_info}) ------\n"
        selected_with_numbers = header

        for i, line in enumerate(lines[start-1:end], start=start):
            selected_with_numbers += f"{i}: {line}"

        # Add other hit locations if not unique
        if not is_unique:
            selected_with_numbers += "\n"
            for idx, hit_line in enumerate(match_lines[1:], start=2):
                selected_with_numbers += f"Hit line number #{idx}: {hit_line}\n"

        uniqueness_note = "" if is_unique else f" (not unique: {len(match_lines)} occurrences)"
        success_msg = f"✅ Found '{search_string}' [{search_type}] at line {match_line}{uniqueness_note}, showing lines {start}-{end} from {rel_path}"
        append_to_clipboard_tmp(selected_with_numbers)
        return True, success_msg

    except ValueError:
        error_msg = f"Invalid offset format: {offset_range} (use: before,after, e.g., 10,30)"
        return False, error_msg
    except Exception as e:
        error_msg = f"Error searching file: {e}"
        return False, error_msg

def file_search(search_term, pattern):
    """
    Search for text in files matching wildcard pattern. Supports wildcards (* ?) and regex (prefix with 'regex:')
    Returns: (success: bool, message: str)
    """
    import glob


    # Check if regex mode
    use_regex = search_term.startswith('regex:')
    if use_regex:
        search_term = search_term[6:]  # Remove 'regex:' prefix
        try:
            regex_pattern = re.compile(search_term)
        except re.error as e:
            error_msg = f"❌ Invalid regex pattern: {e}"
            return False, error_msg

        def match_func(line):
            return regex_pattern.search(line) is not None
    else:
        # Check if wildcards are used
        has_wildcards = '*' in search_term or '?' in search_term
        if has_wildcards:
            def match_func(line):
                return fnmatch.fnmatch(line, f"*{search_term}*")
        else:
            # Literal search - accept any characters
            def match_func(line):
                return search_term in line

    # Make pattern recursive if it doesn't already contain **
    if '**' not in pattern:
        # Split pattern into directory and file parts
        if '/' in pattern:
            parts = pattern.rsplit('/', 1)
            pattern = f"{parts[0]}/**/{parts[1]}"
        else:
            pattern = f"**/{pattern}"

    # Expand wildcard pattern recursively
    matches = glob.glob(pattern, recursive=True)

    if not matches:
        error_msg = f"❌ No files found matching pattern: {pattern}"
        return False, error_msg

    # Filter to only text files
    text_files = []
    for filepath in matches:
        filepath = Path(filepath)
        if filepath.is_file() and is_text_file(filepath):
            text_files.append(filepath)

    if not text_files:
        error_msg = f"❌ No text files found matching pattern: {pattern}"
        return False, error_msg

    # Search in each file
    results = []
    total_hits = 0

    for filepath in sorted(text_files):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Find all occurrences in this file
            file_hits = []
            for line_num, line in enumerate(lines, start=1):
                if match_func(line):
                    file_hits.append((line_num, line.rstrip()))

            if file_hits:
                rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath
                results.append({
                    'file': rel_path,
                    'hits': file_hits,
                    'count': len(file_hits)
                })
                total_hits += len(file_hits)

        except Exception as e:
            # Skip files that can't be read
            continue

    if not results:
        error_msg = f"❌ No matches found for '{search_term}' in {len(text_files)} file(s)"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    # Format output - compact list format
    output = ""
    for result in results:
        for line_num, line_text in result['hits']:
            output += f"{result['file']}:{line_num}: {line_text}\n"

    append_to_clipboard_tmp(output)
    return True, ""

def read_file_to_clipboard(filepath):
    """Read file and copy to clipboard"""
    filepath = Path(filepath)

    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath
        header = f"\n------ {rel_path} ------\n"
        content_with_header = header + content

        success_msg = f"✅ Read {len(content)} bytes from {rel_path}"
        append_to_clipboard_tmp(content_with_header)
        return True, success_msg

    except Exception as e:
        error_msg = f"Error reading file: {e}"
        return False, error_msg

def append_to_clipboard_tmp(message):
    """Append message to clipboard.tmp"""
    try:
        with open(CLIPBOARD_TMP_FILE, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
        return True
    except Exception as e:
        print(f"Warning: Could not write to clipboard.tmp: {e}")
        return False

def copy_clipboard_tmp_to_clipboard():
    """Copy contents of clipboard.tmp to clipboard"""
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
    """Copy text to clipboard"""
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
    """Load patch history from JSON"""
    if not PATCH_HISTORY_FILE.exists():
        return []
    try:
        with open(PATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load patch history: {e}")
        return []

def save_patch_history(history):
    """Save patch history to JSON"""
    try:
        with open(PATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving patch history: {e}")
        return False

def get_next_patch_id():
    """Get next available patch ID"""
    history = load_patch_history()
    if not history:
        return 1
    return max(p['id'] for p in history) + 1

def tidy_text(text):
    """
    Normalize text by removing trailing whitespace and reducing multiple empty lines to max 1.
    Used for matching during patching to be immune to whitespace variations.
    Returns: normalized text
    """
    lines = text.splitlines(keepends=True)
    tidied = []
    prev_empty = False

    for line in lines:
        stripped = line.rstrip()  # Remove trailing whitespace

        if not stripped:  # Line is empty or whitespace-only
            if not prev_empty:  # Only add ONE empty line
                tidied.append('')
                prev_empty = True
        else:
            tidied.append(stripped)
            prev_empty = False

    return '\n'.join(tidied)

def fix_indentation_errors(content):

    """
    Fixes ONLY indentation errors by analyzing Python structure.
    Does NOT change code logic, ONLY whitespace at the beginning of lines.
    Returns: (fixed_content: str, was_fixed: bool)
    """

    lines = content.splitlines(keepends=True)
    fixed_lines = []
    indent_stack = [0]  # Stack to keep track of indent levels

    for i, line in enumerate(lines):
        stripped = line.lstrip()

        # Keep empty lines and comments as-is
        if not stripped or stripped.startswith('#'):
            fixed_lines.append(line)
            continue

        # Count current indent
        current_indent = len(line) - len(stripped)

        # Check if previous line ended with :
        if fixed_lines:
            prev_line = fixed_lines[-1].rstrip()
            if prev_line.endswith(':'):
                # Expect increased indent
                expected_indent = indent_stack[-1] + 4
                indent_stack.append(expected_indent)
            else:
                # Check if we should decrease indent (dedent)
                # If current indent is less than stack, pop
                while len(indent_stack) > 1 and current_indent < indent_stack[-1]:
                    indent_stack.pop()

                expected_indent = indent_stack[-1]
        else:
            expected_indent = 0

        # Apply correct indent
        fixed_line = ' ' * expected_indent + stripped
        fixed_lines.append(fixed_line)

    fixed_content = ''.join(fixed_lines)
    return fixed_content, fixed_content != content

def validate_and_fix_python_syntax(filepath, content):
    """
    Validates Python syntax and fixes indentation errors automatically.
    Returns: (fixed_content: str, was_fixed: bool, error_msg: str)
    """

    if not str(filepath).endswith('.py'):
        return content, False, ""

    # Test original first
    try:
        ast.parse(content)
        return content, False, ""
    except IndentationError:
        # Try to fix indentation errors
        try:
            fixed_content, was_fixed = fix_indentation_errors(content)

            # Verify that the fix works
            ast.parse(fixed_content)
            return fixed_content, True, ""

        except (IndentationError, SyntaxError) as e:
            return content, False, f"Could not auto-fix: {e.msg}"
    except SyntaxError as e:
        return content, False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return content, False, ""

def apply_patch(filepath, description, old_text, new_text):
    """
    Apply a patch and save in history
    Returns: (success: bool, message: str)
    """

    filepath = Path(filepath).resolve()

    if not filepath.exists():
        rel_path = Path(filepath).relative_to(Path.cwd())
        error_msg = f"File not found: {rel_path}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    words = description.split()
    if len(words) > 10:

        rel_path = filepath.relative_to(Path.cwd())
        file_col = f"{rel_path}".ljust(40)
        desc_col = f"{description}".ljust(50)
        error_msg = f"❌ {file_col} {desc_col} Description too long ({len(words)} words, max 10)"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # Try exact match first
        used_flexible_whitespace = False
        used_tidy_matching = False

        if old_text in original_content:
            count = original_content.count(old_text)

            if count > 1:
                rel_path = filepath.relative_to(Path.cwd())
                file_col = f"{rel_path}".ljust(40)
                desc_col = f"{description}".ljust(50)
                error_msg = f"❌ {file_col} {desc_col} Old text appears {count} times in file (must be unique)"
                append_to_clipboard_tmp(error_msg)
                return False, error_msg
            actual_old_text = old_text

        else:
            # Try whitespace-agnostic matching
            used_flexible_whitespace = True
            pattern = re.sub(r'\s+', '\x00WHITESPACE\x00', old_text)
            pattern = re.escape(pattern)
            pattern = pattern.replace('\x00WHITESPACE\x00', r'\s+')
            matches = list(re.finditer(pattern, original_content))

            if len(matches) == 0:
                # Try tidy matching as last resort
                used_tidy_matching = True
                tidied_old = tidy_text(old_text)
                tidied_content = tidy_text(original_content)

                if tidied_old in tidied_content:
                    count = tidied_content.count(tidied_old)

                    if count > 1:
                        rel_path = filepath.relative_to(Path.cwd())
                        file_col = f"{rel_path}".ljust(40)
                        desc_col = f"{description}".ljust(50)
                        error_msg = f"❌ {file_col} {desc_col} Old text appears {count} times in file after tidy (must be unique)"
                        append_to_clipboard_tmp(error_msg)
                        return False, error_msg

                    # Find actual position in original content by matching tidied sections
                    tidied_lines = tidied_content.split('\n')
                    search_lines = tidied_old.split('\n')

                    # Find where tidied match occurs
                    for i in range(len(tidied_lines) - len(search_lines) + 1):
                        if '\n'.join(tidied_lines[i:i+len(search_lines)]) == tidied_old:
                            # Map back to original content
                            original_lines = original_content.splitlines(keepends=True)
                            tidy_to_original_map = []
                            tidy_idx = 0

                            for orig_idx, line in enumerate(original_lines):
                                stripped = line.rstrip()
                                if stripped or tidy_idx >= len(tidied_lines) or tidied_lines[tidy_idx]:
                                    tidy_to_original_map.append(orig_idx)
                                    tidy_idx += 1

                            start_orig = tidy_to_original_map[i] if i < len(tidy_to_original_map) else 0
                            end_orig = tidy_to_original_map[min(i + len(search_lines), len(tidy_to_original_map) - 1)]
                            actual_old_text = ''.join(original_lines[start_orig:end_orig + 1])
                            break
                    else:
                        rel_path = filepath.relative_to(Path.cwd())
                        file_col = f"{rel_path}".ljust(40)
                        desc_col = f"{description}".ljust(50)
                        error_msg = f"❌ {file_col} {desc_col} Old text not found in file (even with tidy matching)"
                        append_to_clipboard_tmp(error_msg)
                        return False, error_msg
                else:
                    rel_path = filepath.relative_to(Path.cwd())
                    file_col = f"{rel_path}".ljust(40)
                    desc_col = f"{description}".ljust(50)
                    error_msg = f"❌ {file_col} {desc_col} Old text not found in file (even with flexible whitespace and tidy)"
                    append_to_clipboard_tmp(error_msg)
                    return False, error_msg

            elif len(matches) > 1:

                rel_path = filepath.relative_to(Path.cwd())
                file_col = f"{rel_path}".ljust(40)
                desc_col = f"{description}".ljust(50)
                error_msg = f"❌ {file_col} {desc_col} Old text appears {len(matches)} times in file (must be unique)"
                append_to_clipboard_tmp(error_msg)

                return False, error_msg

            else:
                # Use the actual text from file (with correct whitespace)
                actual_old_text = matches[0].group(0)

        # Apply tidy to new_text if tidy matching was used
        if used_tidy_matching:
            new_text = tidy_text(new_text)

        new_content = original_content.replace(actual_old_text, new_text)

        # Validate and auto-fix Python syntax
        validated_content, was_fixed, error_msg = validate_and_fix_python_syntax(filepath, new_content)

        # If validation failed, abort the patch

        if error_msg:
            rel_path = filepath.relative_to(Path.cwd())
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(30)
            full_error = f"❌ {file_col} {desc_col} {error_msg}"
            append_to_clipboard_tmp(full_error)
            return False, full_error

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(validated_content)

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

        rel_path = filepath.relative_to(Path.cwd())

        # Format output with column alignment
        icon = "🔧" if was_fixed else "🧩"
        file_col = f"{rel_path}".ljust(40)

        indicators = []
        if used_flexible_whitespace:
            indicators.append("flexible whitespace")
        if used_tidy_matching:
            indicators.append("tidy matching")
        if was_fixed:
            indicators.append("indentation auto-fixed")

        indicator_str = f" ({', '.join(indicators)})" if indicators else ""
        desc_col = f"{description}".ljust(50)

        success_msg = f"{icon} {file_col} {desc_col} Applied successfully{indicator_str}"
        return True, success_msg

    except Exception as e:
        rel_path = filepath.relative_to(Path.cwd())
        error_msg = f"{rel_path}\t\t'{description}': Error: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

def unapply_patch(patch_id):
    """
    Reverse a patch
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
        rel_path = Path(patch['filepath']).relative_to(Path.cwd())
        return False, f"File not found: {rel_path}"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if patch['new_text'] not in content:
            return False, f"Cannot unpatch: new text not found in file"

        content = content.replace(patch['new_text'], patch['old_text'])

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        patch['applied'] = False
        patch['unpatch_error'] = False
        save_patch_history(history)

        success_msg = f"Patch #{patch_id} unapplied successfully"
        copy_to_clipboard(success_msg)
        return True, success_msg

    except Exception as e:
        patch['unpatch_error'] = True
        save_patch_history(history)
        error_msg = f"Error: {e}"
        copy_to_clipboard(error_msg)
        return False, error_msg

def reapply_patch(patch_id):
    """
    Reapply a patch
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
        rel_path = Path(patch['filepath']).relative_to(Path.cwd())
        return False, f"File not found: {rel_path}"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if patch['old_text'] not in content:
            return False, f"Cannot reapply: old text not found in file"

        content = content.replace(patch['old_text'], patch['new_text'])

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        patch['applied'] = True
        patch['unpatch_error'] = False
        save_patch_history(history)

        success_msg = f"Patch #{patch_id} reapplied successfully"
        copy_to_clipboard(success_msg)
        return True, success_msg

    except Exception as e:
        patch['unpatch_error'] = True
        save_patch_history(history)
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

def write_project_tree(out, marked_files):
    """Write simple list of marked files with relative paths"""
    for file_path in marked_files:
        rel_path = file_path.relative_to(Path.cwd())
        out.write(f"{rel_path}\n")

def show_patch_history(stdscr):
    """Show patch history and allow unpatch/repatch"""
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

        title = "Patch History - ↑↓: Navigate | PgUp/PgDn: Jump | Delete: Toggle | q: Back"
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
            if patch.get('unpatch_error', False):
                attr |= curses.color_pair(3)  # Red for errors
            elif patch['applied']:
                attr |= curses.color_pair(1)  # Green for applied

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
        elif key == curses.KEY_PPAGE:  # Page Up
            selected = max(0, selected - display_height)
            scroll = max(0, scroll - display_height)
        elif key == curses.KEY_NPAGE:  # Page Down
            selected = min(len(history) - 1, selected + display_height)
            if selected >= scroll + display_height:
                scroll = selected - display_height + 1
        elif key == curses.KEY_DC:  # Delete key
            patch = history[selected]

            stdscr.clear()
            stdscr.addstr(0, 0, "Processing...", curses.A_BOLD)
            stdscr.refresh()

            if patch['applied']:
                success, msg = unapply_patch(patch['id'])
            else:
                success, msg = reapply_patch(patch['id'])

            history = load_patch_history()

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

def create_code_file(root, structure_files=None):
    marked_files = get_marked_files(root)

    if not marked_files:
        return False

    marked_files = sorted(marked_files, key=lambda x: str(x))

    # Use all files from .promptpack for structure if provided
    if structure_files is None:
        structure_files = marked_files
    else:
        structure_files = sorted(structure_files, key=lambda x: str(x))

    with open('code.txt', 'w', encoding='utf-8') as out:

        out.write("""The following instructions apply if command #patch is given:
Analyze the attached text document with collected source code which is only a compilation, not a target file.
Interpretation of target file should be done via headers in the form ### ./relative/path.

If a file exists in the project structure below but is not included in this document, and you need to see it to complete the task, ask for that file before proceeding and it will be given to you.

Return patch commands using the promptpack -p format with stdin that make exact text replacements in files.
For each change needed, use the promptpack patch command.

THIS FILE INCLUDES THE FULL CONTENT OF:
""")

        # Write the actual file list
        for file_path in structure_files:
            rel_path = file_path.relative_to(Path.cwd())
            out.write(f"{rel_path}\n")

        out.write("""
BEFORE WE START:
List #patch, #undo, #reset, #done and #outsource, #ask with a short description of what these commands do in a tidy table to show the user what commands are available.

IMPORTANT FOR AI:
- ALL files below contain COMPLETE and CURRENT source code.
- NEVER ask for files you already have! ALWAYS search this document first using Ctrl+F or text search.
- Before using promptpack -r/-n/-s, verify the file is NOT already in this document.
- If you need to reference specific code, search within this document - the full source is here.
- Only use promptpack -r/-n/-s if you need files NOT included in this code.txt or if they have substantially changed since code.txt was created.
- Always put all promptpack commands in same bash as 'promptpack -c' depends on it.
- Each command is run separately and we temporarily store the result of them.
- By ensuring 'promptpack -c' is added to the end of each bash window using promptpack command, we make sure all result data is copied to clipboard and the tmp file is removed.

PATCH ERROR HANDLING:
When patches fail, error messages are automatically copied to clipboard.tmp.
CRITICAL RULES for handling failed patches:
- ONLY fix patches that failed - do NOT recreate successful patches.
- ALWAYS search this document first - you have the full source code already.
- Common failures: text not found (already changed), text not unique (be more specific), whitespace issues.
- To fix: Search this document for the current code, then create NEW patch with correct old_text.
- NEVER use -r/-n/-s for files you already have in this document - search here first!

RULES:
- Description must be max 10 words.
- Old_text must match EXACTLY (including all whitespace and newlines).
- Old_text must be unique in the file (appear only once).
- Use ---SPLIT--- to separate old and new text.
- stdin handles all special characters safely (quotes, newlines, etc.).

PATCH BEST PRACTICES:
- Use MINIMUM old_text needed for unique match - don't include unnecessary context lines.
- Example: Instead of matching 10 lines, find 1-3 unique lines that only appear once.
- Shorter old_text = less risk of whitespace/formatting mismatches.
- Before writing patch, verify old_text appears EXACTLY ONCE by searching this document.
- If old_text appears multiple times, make it more specific by including unique surrounding code.

FORMAT FOR PATCHING FILES:
```bash
cat <<'PATCH' | promptpack -p "relative/path" "Short description"
exact old text here
with all whitespace preserved
---SPLIT---
exact new text here
with all whitespace preserved
PATCH

cat <<'PATCH' | promptpack -p "relative/path" "Short description"
exact old text here
with all whitespace preserved
---SPLIT---
exact new text here
with all whitespace preserved
PATCH

promptpack -c
```

CREATE NEW FILES WITH:
```bash
cat <<'EOF' > relative/path
code goes here
EOF

[ $? -eq 0 ] && echo -e "✨ relative/path created successfully" || echo -e "❌ error creating relative/path"
```

SEARCH IN FILES (with filename wildcard pattern):
```bash
# Search for text in files matching a pattern. Always searches recursively in all subdirectories.
# Supports literal search, wildcards (*?), and regex (prefix with "regex:")
# Results show: relative/path:line_number: line_content

# Literal search
promptpack -fs "search_term" "*.py"
promptpack -fs "class Player" "terrain*.py"

# Wildcard search
promptpack -fs "def *init*" "*.py"

# Regex search
promptpack -fs "regex:def\s+\w+\(" "*.py"
promptpack -fs "regex:^class\s+Player" "terrain*.py"

promptpack -c
```

VIEW COMPLETE FILES:
```bash
# This is the preferred way if you already have code.txt if you require any additional files that you already do not have.
# code.txt always contains overhead, which you already have if you are reading this.
promptpack -r relative/path
promptpack -r relative/path
promptpack -c
```

READ SPECIFIC LINES (with search):
```bash
# You should always ask for as many files/search strings as you know you need.
# Supports literal search, wildcards (*?), and regex (prefix with "regex:")
# Format: promptpack -s "search_pattern" before,after relative/path

# Literal search - grab 10 lines before and 20 lines after match
promptpack -s "_function_to_search_for" 10,20 relative/path

# Wildcard search - find any init function
promptpack -s "*init*" 5,15 relative/path

# Regex search - find function definitions with parameters
promptpack -s "regex:def\s+\w+\(" 10,20 relative/path

# Regex search - find class declarations
promptpack -s "regex:^class\s+\w+" 15,30 relative/path

promptpack -c
```

READ SPECIFIC LINEES (with line numbers):
```bash
# You should always ask for as many files/lines as you know you need.
promptpack -n 10,20 relative/path
promptpack -n 190,250 relative/path
promptpack -c
```

DIRECTORY CREATION:
```bash
mkdir -p relative/path/to/folder
```

REMOVAL OF FILES (soft-delete):
```bash
mv relative/path relative/path_deleted
```

IMPORTANT:
- Use promptpack -p for all file changes
- Description max 10 words
- old_text must match EXACTLY (including all whitespace)
- old_text must be unique (appear only once in file)
- All patches in one bash/code block
- Before asking for a file, always first check if you already got it with
- When asking for lines from a files, batch as many as you know you need
- ALL FILES YOU ASKED FOR WITH 'promptpack -a' ARE INCLUDED IN THIS FILE! YOU WILL NEVER ASK FOR -r, -n OR -s ON FILES YOU GOT ALREADY!

ADDITIONAL NOTES:
If we use command #reset this implies that all changes hav been reverted back to the original state.
You will disregard all changes made by patches created during the chat session and fall back and start working from the source found in code.txt again.
If we use the command #undo this implies that the last patch was reverted and undone, falling back to code before the patch was applied.

Sometimes the user might ask questions, and you might take the questions as an invitation to start creating new patches.
If you see the command #ask in, the user is strictly asking questions and you are not expected to write any code at this moment.

GETTING STUCK:
You might get stuck in reasoning/trying to find a solution to a problem.
The user can then trigger, or you can suggest to the user to #outsource the current problem you are working on.
If #outsource command is given you will write prompt for another AI, describing first what you are doing, what the problem is you are having and what result you are expecting to get.
The prompt should ask for a well structured analysis of the code.
End with a 'promptpack -a' command outside the AI prompt where are the files of interest are included, giving the AI all the code it needs to do the analysis.

FALLBACK:
If you find yourself not being able to solve an issue, trying multiple times and coming to the conclusion that you're stuck do not write a patch to restore the code back to the state of code.txt.
Instead let user know that you want to #reset the code and if there are any patches produced in the conversation that are of importance/use, number each patch and instruct user to apply them after resetting the code, for example;
We're not getting anywhere, please #reset the code and apply #patch 2, 9, 12, 13 and 22. Let me know when you are ready and we can proceed.

ENDING:
If the command #done is given it tells you that the conversation is very near its limit and context window is running out.
We don't want to loose work so we need to wrap up!
You need to summarize the whole conversation in the users language and title it "PROMPTPACK Summary":
Start by describing what the project is, what the issue is and what goals its trying to achieve.
If the current session was started with a "PROMPTPACK Summary" you need to first include the list of previously summarized conversations.
Do not summarize the conversation history from previous summary, as this is already summarized.
After adding the previous chat history, continue summarizing every message in this current conversation between you and the user.
All summarized conversation history should be one unified log as if it were one long conversation.
All summary should aid AI to not go in circles trying to find the goal. Example:
User: Implement dynamic shadows in this OpenGL 3D engine.
AI:   Used X and Y to do Z.

User: Shadows are not visible.
AI:   Bug: Z-coordinate was negative (`-(world.offset_y * sx)`), which created a double negation. Fixed by removing the minus sign.

User: Still having same issue.
AI:   Discovered that worldOffset was set in shadow_renderer.py but NEVER used in shadow_pass.vert. Added the offset to the vertex shader.

Summarize what files you have been working with and their relative path.
Create a promptpack -a command with all the files the next session needs to start with in order to pick up where we leave this conversation.
End with notes and thoughts that are specially important to you for this session that can help the next conversation to get a head start.
Never end summary thinking that issues are corrected. Always assume that when #done is called, we are only wrapping up in order to be able to continue in new context window.

## Project Structure
""")

        write_project_tree(out, structure_files)
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
IMPORTANT:
ALL FILES YOU ASK FOR WITH 'promptpack -a' WILL BE INCLUDED IN THE TXT FILE!
YOU WILL NEVER ASK FOR -r, -n OR -s ON FILES YOU GOT ALREADY!

Here is the complete structure of the project and all the relevant files.
Some files might not be included in the ctags list so you need to draw conclusions on what files do what based on their file names and what the user wants to achieve.
If there are any files not listed in the ctags list but you suspect you also need them, please include them in the 'promptpack -a' command.
If you for some reason later on find you need additional files from the project, you can always ask the user for a new 'promptpack -a' with the additional files you require.

## Project Structure
""")

        write_project_tree(out, marked_files)
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
    curses.init_pair(3, curses.COLOR_RED, -1)

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

    parser.add_argument('-s', '--search', nargs=3, metavar=('STRING', 'OFFSET', 'FILE'),
                        help='Search for string and read lines with offset. Supports wildcards (*?), regex (prefix with "regex:"). Example: "_function" "10,30" file.py or "regex:def\\s+\\w+" "5,15" file.py')

    parser.add_argument('-fs', '--file-search', nargs=2, metavar=('STRING', 'PATTERN'),
                        help='Search for string in files matching wildcard pattern. Supports wildcards (*?) and regex (prefix with "regex:"). Examples: -fs "def main" "*.py" or -fs "regex:class\\s+\\w+" "*.py"')

    parser.add_argument('-t', '--tidy', nargs='+', metavar='PATTERN',
                        help='Remove whitespace-only lines and reduce multiple empty lines to max 1. Supports wildcards (*.py, world*.py, etc.)')
    parser.add_argument('-c', '--clear', action='store_true',
                        help='Copy clipboard.tmp to clipboard and remove the file')
    args = parser.parse_args()

    if args.tidy:
        success_messages = []
        error_count = 0
        total_success = True

        for pattern in args.tidy:
            success, message = tidy_file(pattern)
            if not success:
                error_count += 1
                total_success = False
            success_messages.append(message)

        for msg in success_messages:
            print(msg)

        if error_count > 0:
            print(f"\n❌ Failed to tidy {error_count} pattern(s)")
        sys.exit(0 if total_success else 1)

    if args.clear:
        if CLIPBOARD_TMP_FILE.exists():
            if copy_clipboard_tmp_to_clipboard():
                try:
                    CLIPBOARD_TMP_FILE.unlink()
                    sys.exit(0)
                except Exception as e:
                    print(f"✅ File copied but could not remove: {e}")
                    sys.exit(0)
            else:
                print("❌ Could not copy to clipboard (install xclip, xsel, or pbcopy)")
                sys.exit(1)
        else:
            sys.exit(0)

    if args.read:
        success, message = read_file_to_clipboard(args.read)
        print(message)
        sys.exit(0 if success else 1)

    if args.lines:
        line_range, filepath = args.lines
        success, message = read_lines_to_clipboard(line_range, filepath)
        print(message)
        sys.exit(0 if success else 1)

    if args.search:
        search_string, offset_range, filepath = args.search
        success, message = search_and_read_lines(search_string, offset_range, filepath)
        print(message)
        sys.exit(0 if success else 1)

    if args.file_search:
        search_term, pattern = args.file_search
        success, message = file_search(search_term, pattern)

        # Print results from clipboard.tmp if it exists
        if success and CLIPBOARD_TMP_FILE.exists():
            try:
                with open(CLIPBOARD_TMP_FILE, 'r', encoding='utf-8') as f:
                    print(f.read(), end='')
            except:
                pass
        elif not success:
            print(message)

        sys.exit(0 if success else 1)

    if args.patch:
        filepath, description = args.patch

        # Read from stdin
        stdin_content = sys.stdin.read()

        # Split on ---SPLIT---
        parts = stdin_content.split('---SPLIT---')
        if len(parts) != 2:
            print(f"❌ [{filepath}] '{description}': Error: stdin must contain OLD_TEXT---SPLIT---NEW_TEXT")
            sys.exit(1)

        old_text = parts[0]
        new_text = parts[1]

        success, message = apply_patch(filepath, description, old_text, new_text)

        if success:
            print(f"✅ {message}")
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

        # Mark new files for content inclusion
        mark_from_promptpack(root, new_files)
        marked_files = get_marked_files(root)

        if not marked_files:
            print("❌ No valid files found!")
            sys.exit(1)

        # Filter all_paths to only include files from current project
        current_project_files = set()
        for path in all_paths:
            try:
                path.relative_to(cwd)
                current_project_files.add(path)
            except ValueError:
                pass

        # Create code.txt with current_project_files in structure, but only marked_files content
        create_code_file(root, current_project_files)

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
