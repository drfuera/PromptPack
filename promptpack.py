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
import hashlib
import traceback
from datetime import datetime

import ast
import re
import fnmatch

PROMPTPACK_FILE = Path.home() / '.promptpack'
PATCH_HISTORY_FILE = Path('patch.json')
SUMMARY_HISTORY_FILE = Path('summary.json')
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

def compute_file_hash(filepath):
    """SHA256 hash of file, read in 1MB chunks so huge files don't sit fully in memory."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def load_promptpack():
    """Load cached entries for files under the current project.
    Line format: HASH|TOKENS|ABSPATH. Old bare-path lines are still accepted,
    with hash/tokens set to None so they get recomputed once."""
    if not PROMPTPACK_FILE.exists():
        return {}

    try:
        cwd = Path.cwd().resolve()
        entries = {}

        with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line.strip():
                    continue

                parts = line.split('|', 2)
                if len(parts) == 3:
                    file_hash, tokens_str, path_str = parts
                    try:
                        tokens = int(tokens_str)
                    except ValueError:
                        file_hash, tokens, path_str = None, None, line
                else:
                    file_hash, tokens, path_str = None, None, line

                path = Path(path_str.strip())
                if not path.is_absolute():
                    continue

                abs_path = path.resolve()

                try:
                    abs_path.relative_to(cwd)
                    if abs_path.exists():
                        entries[abs_path] = {'hash': file_hash, 'tokens': tokens}
                except (ValueError, OSError):
                    pass

        return entries
    except:
        return {}

def save_promptpack(marked_files):
    """Persist marked files with content-hash + token cache so unchanged
    files never get re-tokenized. Returns total tokens for marked_files."""
    try:
        cwd = Path.cwd().resolve()
        old_cache = load_promptpack()

        existing_other_projects = []
        if PROMPTPACK_FILE.exists():
            with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    line = raw_line.rstrip('\n')
                    if not line.strip():
                        continue

                    parts = line.split('|', 2)
                    path_str = parts[2] if len(parts) == 3 else line
                    path = Path(path_str.strip())
                    if not path.is_absolute():
                        continue

                    abs_path = path.resolve()

                    try:
                        abs_path.relative_to(cwd)
                    except ValueError:
                        if abs_path.exists():
                            existing_other_projects.append(line)

        total_tokens = 0
        new_lines = []
        for fp in marked_files:
            resolved = fp.resolve()
            try:
                file_hash = compute_file_hash(resolved)
                cached = old_cache.get(resolved)
                if cached and cached['hash'] == file_hash and cached['tokens'] is not None:
                    tokens = cached['tokens']
                else:
                    content = resolved.read_text(encoding='utf-8', errors='ignore')
                    tokens = calculate_tokens(content)
            except Exception:
                file_hash, tokens = '', 0

            total_tokens += tokens
            new_lines.append(f"{file_hash}|{tokens}|{resolved}")

        with open(PROMPTPACK_FILE, 'w', encoding='utf-8') as f:
            for line in sorted(existing_other_projects):
                f.write(f"{line}\n")
            for line in sorted(new_lines):
                f.write(f"{line}\n")

        return total_tokens

    except Exception as e:
        append_to_clipboard_tmp(f"⚠️ Warning: Could not save .promptpack: {e}")
        return 0


def read_lines_to_clipboard(line_range, filepath):
    """Read specific lines and copy to clipboard"""
    filepath = Path(filepath)

    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    try:
        start, end = map(int, line_range.split(','))

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Auto-adjust if end exceeds file length
        if end > len(lines):
            end = len(lines)



        rel_path = filepath.relative_to(Path.cwd()) if filepath.is_absolute() else filepath

        if start < 1 or start > end:
            error_msg = f"❌ {rel_path}: Invalid range {start},{end} (file has {len(lines)} lines)"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg
        header = f"\n------ {rel_path} ------\n"
        selected_with_numbers = header
        for i, line in enumerate(lines[start-1:end], start=start):
            selected_with_numbers += f"{i}: {line}"

        success_msg = f"✅ Read lines {start}-{end} from {rel_path}"
        append_to_clipboard_tmp(selected_with_numbers)
        return True, success_msg



    except ValueError:
        error_msg = f"Invalid range format: {line_range} (use: start,end)"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg



# Unambiguous regex chars: escaped meta-chars, groups, quantifiers — never in literal searches
_REGEX_HINT = re.compile(r'\\[|sSwWdDbBtnr]|\(\?|(?<![*?])[+{]')

def _grep_to_python_regex(s):
    """Convert grep-style regex escapes to Python: \| → |"""
    return re.sub(r'\\\|', '|', s)

def _resolve_search(s):
    """Return (pattern, use_regex, auto_promoted).
    - explicit 'regex:' prefix  → regex, not auto
    - unambiguous regex escapes → regex, auto (silent)
    - wildcards (* ?)           → glob, not regex
    - else                      → literal
    """
    if s.startswith('regex:'):
        return _grep_to_python_regex(s[6:]), True, False
    if _REGEX_HINT.search(s):
        return _grep_to_python_regex(s), True, True   # auto-promote silently
    return s, False, False     # glob or literal, decided by caller

def search_and_read_lines(search_string, offset_range, filepath):
    """Search for string and show lines with offset. Supports wildcards (* ?) and regex (prefix with 'regex:')"""
    filepath = Path(filepath)


    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg


    search_string, use_regex, auto_promoted = _resolve_search(search_string)
    has_wildcards = not use_regex and ('*' in search_string or '?' in search_string)

    if use_regex:
        try:
            pattern = re.compile(search_string, re.IGNORECASE)
        except re.error as e:
            error_msg = f"❌ Invalid regex pattern: {e}"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg
        def match_func(line):
            return pattern.search(line) is not None
    elif has_wildcards:
        def match_func(line):
            return fnmatch.fnmatch(line.lower(), f"*{search_string.lower()}*")
    else:
        def match_func(line):
            return search_string.lower() in line.lower()

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
            if has_wildcards:
                error_msg += f"\n⚠️  If this was a regex pattern, prefix with 'regex:' — e.g. regex:{search_string}"
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
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    except Exception as e:
        error_msg = f"Error searching file: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

def file_search(search_term, pattern):
    """
    Search for text in files matching wildcard pattern. Supports wildcards (* ?) and regex (prefix with 'regex:')
    Returns: (success: bool, message: str)
    """
    import glob



    search_term, use_regex, auto_promoted = _resolve_search(search_term)
    has_wildcards = not use_regex and ('*' in search_term or '?' in search_term)

    if use_regex:
        try:
            regex_pattern = re.compile(search_term, re.IGNORECASE)

        except re.error as e:
            error_msg = f"❌ Invalid regex pattern: {e}"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg
        def match_func(line):
            return regex_pattern.search(line) is not None
    elif has_wildcards:
        def match_func(line):
            return fnmatch.fnmatch(line.lower(), f"*{search_term.lower()}*")
    else:
        def match_func(line):
            return search_term.lower() in line.lower()

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
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    # Filter to only text files
    text_files = []
    for filepath in matches:
        filepath = Path(filepath)
        if filepath.is_file() and is_text_file(filepath):
            text_files.append(filepath)


    if not text_files:
        error_msg = f"❌ No text files found matching pattern: {pattern}"
        append_to_clipboard_tmp(error_msg)
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
    return True, f"✅ Found {total_hits} match(es) in {len(results)} file(s)"


def read_file_to_clipboard(filepath):
    """Read file and copy to clipboard"""
    filepath = Path(filepath)

    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        append_to_clipboard_tmp(error_msg)
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
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

def append_to_clipboard_tmp(message):
    """Append message to clipboard.tmp"""
    try:
        with open(CLIPBOARD_TMP_FILE, 'a', encoding='utf-8') as f:
            f.write(message if message.endswith('\n') else message + '\n')
        return True
    except Exception as e:
        print(f"Warning: Could not write to clipboard.tmp: {e}")
        return False

def log_error_to_file(context, detail):
    """Append a timestamped error entry to promptpack_error.log for debugging.
    Never raises — logging must not itself break the calling operation."""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('promptpack_error.log', 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {context}\n{detail}\n\n")
    except Exception:
        pass

def load_summary_history():
    """Load summary history from JSON"""
    if not SUMMARY_HISTORY_FILE.exists():
        return []
    try:
        with open(SUMMARY_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load summary history: {e}")
        return []

def save_summary_history(history):
    """Save summary history to JSON"""
    try:
        with open(SUMMARY_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving summary history: {e}")
        return False

def get_next_summary_id():
    """Get next available summary ID"""
    history = load_summary_history()
    if not history:
        return 1
    return max(s['id'] for s in history) + 1

def append_to_summary_file(text):
    """Save a timestamped summary entry to summary.json.
    Returns: (success: bool, message: str)
    """
    try:
        history = load_summary_history()

        summary_id = get_next_summary_id()
        timestamp = datetime.now().isoformat()
        history.append({
            'id': summary_id,
            'timestamp': timestamp,
            'text': text.strip()
        })
        save_summary_history(history)

        success_msg = f"✅ Summary saved [SUMMARYID {summary_id}]"
        append_to_clipboard_tmp(success_msg)
        return True, success_msg
    except Exception as e:
        error_msg = f"❌ Error writing summary.json: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

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
        if sys.platform == 'win32':
            subprocess.run(['clip'], input=text.encode('utf-16-le'), check=True)
            return True
        elif shutil.which('xclip'):
            subprocess.run(['xclip', '-selection', 'clipboard'],
                         input=text.encode(), check=True)
            subprocess.run(['xclip', '-selection', 'primary'],
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

def _synced_new_text(new_content, validated_content, pos, new_text):
    """After an indentation auto-fix, the text stored in patch history must
    match what actually ends up on disk, or a later undo can't find it.
    fix_indentation_errors only rewrites each line's leading whitespace and
    never changes line count, so remap new_text's line range from
    new_content to the corresponding lines in validated_content. Falls back
    to the original new_text if the mapping can't be verified safely."""
    try:
        start_line = new_content.count('\n', 0, pos)
        new_lines = new_content.splitlines(keepends=True)
        fixed_lines = validated_content.splitlines(keepends=True)
        if len(new_lines) != len(fixed_lines):
            return new_text
        span = new_text.splitlines(keepends=True)
        n = len(span)
        if ''.join(new_lines[start_line:start_line + n]) != new_text:
            return new_text
        return ''.join(fixed_lines[start_line:start_line + n])
    except Exception:
        return new_text

def _delete_anchor(content, start, end, context_chars=60):
    """For a deletion patch (new_text == ''), capture the text immediately
    surrounding the removed span so a later unapply_patch call can locate
    where to reinsert restore_text. Searching the file for an empty string
    at undo time is useless: str.count('') matches at every position
    (len(content)+1 'occurrences'), which is exactly what produced the
    bogus 'not unique' errors for pure-deletion patches. Anchoring on real
    neighboring text instead gives undo something concrete and normally
    unique to search for."""
    before = content[max(0, start - context_chars):start]
    after = content[end:end + context_chars]
    return before, after

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
    desc_truncated = False
    if len(words) > 10:
        description = ' '.join(words[:10])
        desc_truncated = True

    WILDCARD = '***WILDCARD_PROMPTPACK***'
    if WILDCARD in new_text:
        rel_path = filepath.relative_to(Path.cwd())
        file_col = f"{rel_path}".ljust(40)
        desc_col = f"{description}".ljust(50)
        error_msg = f"❌ {file_col} {desc_col} ***WILDCARD_PROMPTPACK*** is not allowed in new_text"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()


        # Wildcard mode: split old_text on placeholder, match prefix + anything + suffix
        if WILDCARD in old_text:
            wc_parts = old_text.split(WILDCARD, 1)
            wc_prefix, wc_suffix = wc_parts[0], wc_parts[1]

            matches = []
            search_start = 0
            while True:
                pre_pos = original_content.find(wc_prefix, search_start)
                if pre_pos == -1:
                    break
                suf_pos = original_content.find(wc_suffix, pre_pos + len(wc_prefix))
                if suf_pos == -1:
                    break
                matches.append((pre_pos, suf_pos + len(wc_suffix)))
                search_start = pre_pos + 1

            rel_path = filepath.relative_to(Path.cwd())
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(50)

            if len(matches) == 0:
                error_msg = f"❌ {file_col} {desc_col} Wildcard prefix/suffix not found in file"
                append_to_clipboard_tmp(error_msg)
                return False, error_msg

            if len(matches) > 1:
                error_msg = f"❌ {file_col} {desc_col} Wildcard match not unique ({len(matches)} occurrences, must be 1)"
                append_to_clipboard_tmp(error_msg)
                return False, error_msg

            wc_start, wc_end = matches[0]

            if new_text.startswith('\n'):
                new_text = new_text[1:]
            if new_text == '':
                delete_anchor_before, delete_anchor_after = _delete_anchor(original_content, wc_start, wc_end)
            else:
                delete_anchor_before, delete_anchor_after = None, None
            new_content = original_content[:wc_start] + new_text + original_content[wc_end:]

            validated_content, was_fixed, err = validate_and_fix_python_syntax(filepath, new_content)
            if err:
                full_error = f"❌ {file_col} {desc_col} {err}"
                append_to_clipboard_tmp(full_error)
                return False, full_error

            if was_fixed:
                new_text = _synced_new_text(new_content, validated_content, wc_start, new_text)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(validated_content)

            history = load_patch_history()
            patch_id = get_next_patch_id()
            history.append({
                'id': patch_id,
                'timestamp': datetime.now().isoformat(),
                'filepath': str(filepath),
                'description': description,

                'old_text': old_text,
                'actual_old_text': original_content[wc_start:wc_end],
                'new_text': new_text,
                'delete_anchor_before': delete_anchor_before,
                'delete_anchor_after': delete_anchor_after,
                'applied': True
            })
            save_patch_history(history)

            icon = "🔧" if was_fixed else "🧩"
            indicators_wc = ["wildcard match"]
            if was_fixed:
                indicators_wc.append("indentation auto-fixed")
            if desc_truncated:
                indicators_wc.append("description truncated to 10 words")
            indicator_str = f" ({', '.join(indicators_wc)})"
            success_msg = f"{icon} {file_col} {desc_col} Applied successfully{indicator_str} [PATCHID {patch_id}]"
            return True, success_msg

        if old_text == '':
            rel_path = filepath.relative_to(Path.cwd())
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(50)
            error_msg = f"❌ {file_col} {desc_col} old_text is empty — nothing to match (use NEW FILE for pure insertions)"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

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
                            prev_was_empty = False

                            for orig_idx, line in enumerate(original_lines):
                                stripped = line.rstrip()
                                if stripped:
                                    tidy_to_original_map.append(orig_idx)
                                    tidy_idx += 1
                                    prev_was_empty = False
                                elif not prev_was_empty:
                                    tidy_to_original_map.append(orig_idx)
                                    tidy_idx += 1
                                    prev_was_empty = True

                            start_orig = tidy_to_original_map[i] if i < len(tidy_to_original_map) else 0
                            if i + len(search_lines) < len(tidy_to_original_map):
                                end_orig = tidy_to_original_map[i + len(search_lines)] - 1
                            else:
                                end_orig = len(original_lines) - 1
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


        if new_text.startswith('\n'):
            new_text = new_text[1:]
        if new_text == '':
            _del_start = original_content.index(actual_old_text)
            delete_anchor_before, delete_anchor_after = _delete_anchor(
                original_content, _del_start, _del_start + len(actual_old_text))
        else:
            delete_anchor_before, delete_anchor_after = None, None
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

        if was_fixed:
            new_text = _synced_new_text(new_content, validated_content, original_content.index(actual_old_text), new_text)

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
            'delete_anchor_before': delete_anchor_before,
            'delete_anchor_after': delete_anchor_after,
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
        if desc_truncated:
            indicators.append("description truncated to 10 words")

        indicator_str = f" ({', '.join(indicators)})" if indicators else ""
        desc_col = f"{description}".ljust(50)

        success_msg = f"{icon} {file_col} {desc_col} Applied successfully{indicator_str} [PATCHID {patch_id}]"
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
        error_msg = f"Patch #{patch_id} not found"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
        return False, error_msg

    if not patch['applied']:
        error_msg = f"Patch #{patch_id} is already unapplied"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
        return False, error_msg

    filepath = Path(patch['filepath'])
    if not filepath.exists():
        rel_path = Path(patch['filepath']).relative_to(Path.cwd())
        error_msg = f"File not found: {rel_path}"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if patch['new_text'] == '':
            if 'delete_anchor_before' not in patch:
                error_msg = "Cannot unpatch: this deletion predates anchor tracking, no safe location to restore text"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
            anchor_before = patch['delete_anchor_before'] or ''
            anchor_after = patch['delete_anchor_after'] or ''
            anchor = anchor_before + anchor_after
            if not anchor:
                error_msg = "Cannot unpatch: deletion has no surrounding context to anchor to"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
            anchor_count = content.count(anchor)
            if anchor_count == 0:
                error_msg = "Cannot unpatch: surrounding context of deletion not found in file"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
            if anchor_count > 1:
                error_msg = f"Cannot unpatch: surrounding context not unique ({anchor_count} occurrences) — unapply in reverse order"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
            restore_text = patch.get('actual_old_text', patch['old_text'])
            insert_at = content.index(anchor) + len(anchor_before)
            content = content[:insert_at] + restore_text + content[insert_at:]
        else:
            new_text_count = content.count(patch['new_text'])
            if new_text_count == 0:
                error_msg = f"Cannot unpatch: new text not found in file"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
            if new_text_count > 1:
                error_msg = f"Cannot unpatch: new_text not unique ({new_text_count} occurrences) — unapply in reverse order"
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg

            restore_text = patch.get('actual_old_text', patch['old_text'])
            content = content.replace(patch['new_text'], restore_text, 1)

        validated_content, was_fixed, syntax_err = validate_and_fix_python_syntax(filepath, content)
        if syntax_err:
            patch['unpatch_error'] = True
            save_patch_history(history)
            error_msg = f"Unapply would produce invalid syntax: {syntax_err}"
            append_to_clipboard_tmp(error_msg)
            log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
            return False, error_msg

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(validated_content)

        patch['applied'] = False
        patch['unpatch_error'] = False
        save_patch_history(history)

        success_msg = f"Patch #{patch_id} unapplied successfully" + (" (indentation auto-fixed)" if was_fixed else "")
        append_to_clipboard_tmp(success_msg)
        return True, success_msg

    except Exception as e:
        patch['unpatch_error'] = True
        save_patch_history(history)
        error_msg = f"Error: {e}"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Undo failed for patch #{patch_id}", f"{error_msg}\n{traceback.format_exc()}")
        return False, error_msg

def unapply_summary(summary_id):
    """
    Mark a summary entry as reverted. This is a historical annotation only
    — it never touches any patch or any code. Undoing actual code changes
    is always explicit and per-patch via unapply_patch()/-u; -us only ever
    affects the summary.json record itself, and never deletes it.
    Returns: (success: bool, message: str)
    """
    history = load_summary_history()
    entry = None
    for s in history:
        if s['id'] == summary_id:
            entry = s
            break
    if not entry:
        error_msg = f"Summary #{summary_id} not found"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Undo summary failed for #{summary_id}", error_msg)
        return False, error_msg
    if entry.get('reverted', False):
        msg = f"Summary #{summary_id} is already marked as reverted"
        append_to_clipboard_tmp(msg)
        return True, msg
    entry['reverted'] = True
    entry['reverted_at'] = datetime.now().isoformat()
    save_summary_history(history)
    success_msg = f"✅ Summary #{summary_id} marked as reverted (no patches touched — use -u <PATCHID> to undo specific code changes)"
    append_to_clipboard_tmp(success_msg)
    return True, success_msg
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
        error_msg = f"Patch #{patch_id} not found"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Reapply failed for patch #{patch_id}", error_msg)
        return False, error_msg

    if patch['applied']:
        error_msg = f"Patch #{patch_id} is already applied"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Reapply failed for patch #{patch_id}", error_msg)
        return False, error_msg

    filepath = Path(patch['filepath'])
    if not filepath.exists():
        rel_path = Path(patch['filepath']).relative_to(Path.cwd())
        error_msg = f"File not found: {rel_path}"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Reapply failed for patch #{patch_id}", error_msg)
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        restore_text = patch.get('actual_old_text', patch['old_text'])
        restore_count = content.count(restore_text)
        if restore_count == 0:
            error_msg = "Cannot reapply: old text not found in file"
            append_to_clipboard_tmp(error_msg)
            log_error_to_file(f"Reapply failed for patch #{patch_id}", error_msg)
            return False, error_msg
        if restore_count > 1:
            error_msg = f"Cannot reapply: old text not unique ({restore_count} occurrences) — reapply in order"
            append_to_clipboard_tmp(error_msg)
            log_error_to_file(f"Reapply failed for patch #{patch_id}", error_msg)
            return False, error_msg

        pos = content.index(restore_text)
        new_content = content.replace(restore_text, patch['new_text'], 1)

        validated_content, was_fixed, error_msg = validate_and_fix_python_syntax(filepath, new_content)
        if error_msg:
            patch['unpatch_error'] = True
            save_patch_history(history)
            full_error = f"Reapply would produce invalid syntax: {error_msg}"
            append_to_clipboard_tmp(full_error)
            log_error_to_file(f"Reapply failed for patch #{patch_id}", full_error)
            return False, full_error

        if was_fixed:
            patch['new_text'] = _synced_new_text(new_content, validated_content, pos, patch['new_text'])

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(validated_content)

        patch['applied'] = True
        patch['unpatch_error'] = False
        save_patch_history(history)

        success_msg = f"Patch #{patch_id} reapplied successfully" + (" (indentation auto-fixed)" if was_fixed else "")
        append_to_clipboard_tmp(success_msg)
        return True, success_msg

    except Exception as e:
        patch['unpatch_error'] = True
        save_patch_history(history)
        error_msg = f"Error: {e}"
        append_to_clipboard_tmp(error_msg)
        log_error_to_file(f"Reapply failed for patch #{patch_id}", f"{error_msg}\n{traceback.format_exc()}")
        return False, error_msg

def format_patch_detail(p):
    """Format one patch entry with full old/new code - the detailed format
    used by -ph when the AI needs to inspect a specific patch closely.
    Returns a list of lines (no trailing separator)."""
    try:
        rel_path = Path(p['filepath']).relative_to(Path.cwd())
    except Exception:
        rel_path = p['filepath']
    try:
        ts = datetime.fromisoformat(p['timestamp'])
        datetime_str = ts.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        datetime_str = p.get('timestamp', 'unknown time')
    old_code = p.get('actual_old_text', p.get('old_text', ''))
    new_code = p.get('new_text', '')
    lines = []
    lines.append(f"[{datetime_str}] PATCH #{p['id']} - {rel_path}")
    lines.append(f"Description: {p.get('description', '')}")
    lines.append("--- REPLACED ---")
    lines.append(old_code if old_code.strip() else "(nothing - pure insertion)")
    lines.append("--- WITH ---")
    lines.append(new_code if new_code.strip() else "(nothing - deletion)")
    return lines
def create_work_log():
    """Build work.txt: a lightweight chronological changelog combining
    summary entries (full text) and patch entries (compact one-liners: date,
    PATCHID, file, description - never the old/new code, to keep this
    document small). Starts with a PATCH TOC section listing every patch
    for quick scanning. Use -ph <PATCHID ...> to fetch full old/new code
    for specific patches once the TOC/summaries make clear which are
    worth a closer look.
    Returns: (success: bool, message: str)
    """
    if not PATCH_HISTORY_FILE.exists() and not SUMMARY_HISTORY_FILE.exists():
        return False, "❌ No patch.json or summary.json found in current directory"
    patches = load_patch_history()
    summaries = load_summary_history()
    entries = []
    for p in patches:
        if not p.get('applied', False):
            continue
        try:
            ts = datetime.fromisoformat(p['timestamp'])
        except Exception:
            continue
        entries.append((ts, 'patch', p))
    for s in summaries:
        try:
            ts = datetime.fromisoformat(s['timestamp'])
        except Exception:
            continue
        entries.append((ts, 'summary', s))
    if not entries:
        return False, "❌ No applied patches or summaries found to log"
    entries.sort(key=lambda e: e[0])
    lines = []
    lines.append("# WORK LOG")
    lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Patch entries are compact (no code). Use 'promptpack -ph PATCHID [PATCHID ...]' for full old/new code.")
    lines.append("")
    lines.append("# PATCH TOC")
    patch_entries = [item for ts, kind, item in entries if kind == 'patch']
    if patch_entries:
        for p in patch_entries:
            try:
                ts = datetime.fromisoformat(p['timestamp'])
                datetime_str = ts.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                datetime_str = p.get('timestamp', 'unknown time')
            try:
                rel_path = Path(p['filepath']).relative_to(Path.cwd())
            except Exception:
                rel_path = p['filepath']
            lines.append(f"{datetime_str}  #{p['id']}  {rel_path}  {p.get('description', '')}")
    else:
        lines.append("(no patches)")
    lines.append("=" * 70)
    for ts, kind, item in entries:
        datetime_str = ts.strftime('%Y-%m-%d %H:%M:%S')
        if kind == 'summary':
            reverted_tag = " [REVERTED]" if item.get('reverted', False) else ""
            lines.append(f"\n[{datetime_str}] SUMMARY [SUMMARYID {item['id']}]{reverted_tag}")
            lines.append(item.get('text', '').strip())
        else:
            p = item
            try:
                rel_path = Path(p['filepath']).relative_to(Path.cwd())
            except Exception:
                rel_path = p['filepath']
            lines.append(f"[{datetime_str}] PATCH #{p['id']} - {rel_path} - {p.get('description', '')}")
        lines.append("-" * 70)
    try:
        with open('work.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True, "✅ work.txt created"
    except Exception as e:
        return False, f"❌ Error writing work.txt: {e}"
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
            dir_children = [child for child in node.children if child.is_dir]

            has_any_children = file_children or dir_children
            all_files_marked = all(child.marked for child in file_children) if file_children else True
            all_dirs_marked = all(child.marked for child in dir_children) if dir_children else True

            if has_any_children and all_files_marked and all_dirs_marked:
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
    """Delegates to save_promptpack, which hashes each file and reuses
    cached tokens when the hash is unchanged (avoids re-tokenizing big files)."""
    return save_promptpack(marked_files)


def write_project_tree(out, marked_files):
    """Write compact directory: file1, file2 grouped structure"""
    from collections import defaultdict
    groups = defaultdict(list)
    for file_path in marked_files:
        rel_path = file_path.relative_to(Path.cwd())
        parent = str(rel_path.parent)
        groups[parent].append(rel_path.name)
    for directory, files in sorted(groups.items()):
        out.write(f"{directory}: {', '.join(files)}\n")

def show_patch_history(stdscr):
    """Show patch history and allow unpatch/repatch"""
    curses.curs_set(0)

    history = load_patch_history()
    history = list(reversed(history))

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


            history = list(reversed(load_patch_history()))

def draw_tree(stdscr, root, selected_idx, scroll_offset, total_tokens):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    visible_nodes = flatten_visible_tree(root)


    title = "↑↓: Navigate | PgUp/PgDn: Jump | ←→: Expand | Space: Mark | i: Import deps | F1: ctags | F12: patches | q: Quit"
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
    status = f"Marked: {len(marked_files)} files | Tokensize: {total_tokens:,} tokens"
    try:
        stdscr.addstr(height - 1, 0, status[:width-1], curses.A_REVERSE)
    except curses.error:
        pass

    stdscr.refresh()


PROMPTPACK_CORE_INSTRUCTIONS = """\
# ABOUT THIS FILE
This is the specification for promptpack, an open-source CLI tool that mediates all file I/O between you and the user's local project.
The user runs the commands you output; you never touch the filesystem directly.
Everything below is the user's own standing preference for how you should operate in this workflow.
Promptpack is a CLI tool that makes life easier when coding. You format the commands, and the user runs them manually. This makes grabbing files, searching in project directory and patching files 100 times easier and faster for the user.

# LANGUAGE
These instructions are written in English, but promptpack itself is
language-agnostic — anyone, in any language, may be on the other end.
Always reply to the user in the language they write to you in. English
here is just the spec language for this instructions file, not a
requirement for your replies.

# ROLE
All file I/O goes through the user's local CLI tool `promptpack`: you write
commands, the user runs them, pastes output back.

Follows directly:
- Never assume/reconstruct file content not shown via promptpack output in
  this conversation.
- Never answer with full file content. Changes = PATCH. Full content only via
  NEW FILE, only for files not already in the project structure.

# WORKFLOW
1. Read the user request and these instructions.
2. Read the ctags list at the bottom to understand the project.
3. Decide which files you need to see or modify.
4. Ask the user to run promptpack commands for those files:
   ~~~
   promptpack -r one/or/more.php files/using/full/path.py
   promptpack -c
   ~~~
5. Files already shown to you in this conversation = complete & current.
   Search the doc/context before asking — never re-request a file you already have.
   Use `-r` / `-n` / `-s` only for files NOT already in this doc.

# FIRST REPLY
List commands in a table: #patch, #undo, #reset, #done, #outsource, #ask, #dumb, #ideas, #name.

# GENERAL RULES
- MANDATORY: every task block (i.e. not a pure repair of a failed patch, and
  not a plain `-u`/`-us` undo — see # UNDO) ends with a --summary heredoc
  before the block's closing -c. promptpack auto-links every patch applied
  since the previous summary — you never pass PATCHIDs yourself. Skipping it
  is a bug, not a shortcut — as required as the -c itself. Before sending
  any bash block, check: does this task need a --summary? If yes, is it
  there?
- All promptpack commands in the same bash block. Only ONE `promptpack -c` — at the very end, after every -p/-f/--summary command. Never one -c per command.
- Always batch as many promptpack commands as possible into one block.
- Claude: never write #patch commands or file contents in artifacts — only in chat messages.
- Description for a patch ≤10 words.
- old_text must be an exact match, and unique in the file.
- Separator between old_text and new_text: `---SPLIT---`
- Regex mode in `-s` / `-fs` needs a `regex:` prefix.
- `--summary` goes right before the block's single closing `-c`. ONE per task,
  never per file/patch. promptpack prepends [YYYY-MM-DD HH:MM] to the text
  automatically — NEVER write your own date/time/timestamp into it, that
  duplicates what's added for you.
- `--summary` text must be verbose and explanatory, not a one-liner: name
  every file touched in the task and what changed in each, then explain WHY
  (the problem solved or goal served). Write it for a reader with zero
  context on this conversation.
- EXCEPTION: debugging patches — adding print/log statements, temporary
  color/highlight markers, or any other diagnostic change made only to
  locate a bug, not to fix it — do NOT get a --summary. Keep patching
  without a summary through as many debugging rounds as it takes. Only the
  patch that applies the actual fix ends the task with --summary, and that
  summary describes the final solution, not the debugging steps taken to
  find it.

# BEST PRACTICES
old_text = minimum unique match (1–3 lines). Shorter = safer.
Verify old_text appears exactly once in the file before patching.

# PATCH FAILURES: SELF-DIAGNOSE FIRST
- A file already shown in this conversation = complete & current. NEVER ask for
  -r/-n/-s of a file you already have, even if a patch against it just failed.
- On "Old text not found" or SyntaxError: stop guessing about overall structure.
  Go straight to the smallest possible old_text (1-3 lines, unique match) taken
  from the file you already have in the conversation.
- If a patch fails twice in a row: switch strategy immediately to the shortest
  possible old_text window (2-3 lines max) — don't ask for more context.
- Assume whitespace/indentation mismatch as the likely cause of a SyntaxError,
  not that the file is unknown or has changed.
- Repair block for a failed patch = NO `--summary`. Just the corrected -p
  command(s) + the block's one closing `-c`. Original task's summary already
  covers it.

# WILDCARD
For old_text >12 lines, use `***WILDCARD_PROMPTPACK***` to skip the middle.
- One wildcard per patch.
- Prefix and suffix each = 2–5 unique lines.
- NEVER put `***WILDCARD_PROMPTPACK***` in new_text — old_text only.

# PATCH
~~~bash
cat <<'PATCH' | promptpack -p "path" "description ≤10 words"
prefix
***WILDCARD_PROMPTPACK***
suffix
---SPLIT---
new_text
PATCH
promptpack -c
~~~
Block not done yet: add the --summary heredoc next (unless this is a pure
repair of a failed patch), then the block's one closing promptpack -c.

# UNDO
Revert a specific patch by its PATCHID — never write a new full patch just to
change something back. The PATCHID is shown in clipboard.tmp right after a
patch is applied, e.g. `[PATCHID 12]`.
~~~bash
promptpack -u 12
promptpack -c
~~~
No `--summary` needed for a plain undo — the original task's summary already
covers it. If undo fails because the new text isn't unique, undo the more
recent overlapping patches first (highest PATCHID down), then retry.

# UNDO SUMMARY
Marks a summary entry as reverted — a historical annotation only. Does NOT
touch any patches or code; `-u` is for undoing patches, `-us` is only for
marking a summary's own record. To undo the code changes a summary
described, find the relevant PATCHIDs (via -w/work.txt or -ph) and undo
each one explicitly with `-u`. The summary.json entry itself is never
deleted — only flagged.
~~~bash
promptpack -us 4
promptpack -c
~~~
No `--summary` needed — the original entry already covers it.

# NEW FILE
~~~bash
cat <<'NEWFILE' | promptpack -f "path"
code
NEWFILE
promptpack -c
~~~
Block not done yet: add the --summary heredoc next (unless this is a pure
repair of a failed patch), then the block's one closing promptpack -c.

# SUMMARY
Purpose: a running changelog in summary.json, written by you so a human or a
future AI session understands what happened and why without re-reading
every patch.

Timestamp: promptpack adds it automatically. NEVER include your own
date/time/timestamp in TEXT — it gets added for you.

Content: be verbose and explanatory, not a one-liner. For every file touched
in the task, name the file and describe what changed in it. Then explain WHY
— the problem being solved, the feature being added, or the goal being
served. Write it as if for a reader with zero context on this conversation.
NEWFILE task → describe the file's purpose + why it exists.
PATCH task → describe what changed + why.

Cardinality: exactly ONE `--summary` per task, covering the whole bash block
— even if the block touches several files across several -p/-f commands.
Never one per file, never one per patch.

EXCEPTION: repairing a failed patch (user sent back ❌) → NO summary. Pure
repair of an existing task; the original task's summary already covers it.

EXCEPTION: debugging patches → NO summary. If a patch is purely diagnostic —
print/log statements, temporary color/highlight markers, or any other change
made only to locate a bug rather than fix it — skip --summary for it, no
matter how many debugging rounds it takes. Once the actual bug is found and
fixed, that fixing patch gets the task's one --summary, and the summary text
covers only the final solution (what was wrong and what fixed it) — it does
not list or describe the debugging steps that led there.
~~~bash
cat <<'SUMMARY' | promptpack --summary
what changed in each file + why — spans as many lines as needed
SUMMARY
~~~
Reads from stdin like NEW FILE — safe for verbose, multi-line text (no
shell-quoting issues from quotes, backticks, or `$`). Runs after all -p/-f
for the task, right before the block's one closing `promptpack -c`. Reports
back `[SUMMARYID N]`. Note the ID if you might want to mark this summary
reverted later (see # UNDO SUMMARY) — that never affects any patch.

# SEARCH (recursive, literal/*?/regex:, output: path:line:content)
~~~bash
promptpack -fs "term" "*.cs"
promptpack -fs "regex:pattern" "*.cs"
promptpack -c
~~~

# VIEW
~~~bash
promptpack -r path
promptpack -c
~~~

# READ BY SEARCH (before,after)
~~~bash
promptpack -s "term" 10,20 path
promptpack -c
~~~

# READ BY LINES
~~~bash
promptpack -n 10,20 path
promptpack -c
~~~

# MKDIR / DELETE
~~~bash
mkdir -p path
mv path path_deleted
~~~

# EXEC (optional timeout seconds)
~~~bash
promptpack -e "cmd"
promptpack -e 15 "cmd"
promptpack -c
~~~

# WORK LOG (chronological changelog, no code embedded)
~~~bash
promptpack -w
promptpack -c
~~~
Combines summary.json + patch.json into work.txt: a PATCH TOC (date,
PATCHID, file, description) at the top, followed by the full chronological
log (summaries in full, patches as compact one-line entries). Never embeds
patch code, so it stays cheap to read in full via `promptpack -r work.txt`.
Use it to get oriented before diving into specifics.

# PATCH HISTORY (fetch full old/new code for specific patches)
~~~bash
promptpack -ph 12 15 18
promptpack -c
~~~
Given one or more PATCHIDs, returns each patch's full detail (date, file,
description, old code replaced, new code it became) to clipboard.tmp. Use
this only for PATCHIDs identified as relevant from work.txt's TOC, dates,
descriptions, or summary text — never request patch.json directly, it can
be very large. Missing IDs are reported without failing the ones found.

# PATCH ERRORS
- Failed patches → `clipboard.tmp`.
- Fix ONLY the failed patches. All others = already applied.
- Search the doc first. Common causes: text not found, not unique, whitespace mismatch.
- Fix: find the current code in the doc → build a new patch with correct old_text.
- Never use `-r` / `-n` / `-s` for files already in the doc.

# COMMANDS
- `#reset` = revert all patches, back to original state.
- `#undo` = revert last patch only, via `promptpack -u <last PATCHID>` (see # UNDO).
- `#ask` = questions only, no code.
- `#dumb` = rewrite last message in plain non-technical terms.
- `#outsource` = write a prompt for another AI: what you're doing, the problem, expected result, request structured analysis. End with `promptpack -r` of relevant files.
- `#ideas` = list alternative solutions/ideas for the current problem, no code.
- `#name` = suggest a short (3–8 word) internal codename for "this version" —
  a fun but specific label summarizing the code or problem currently being
  worked on. For versioning/reference only; never written into code or files
  unless the user explicitly asks.
- `#done` = context limit reached. Write "PROMPTPACK Summary" in the user's language:
  - Project description, issue, goals.
  - If started from a previous summary: include it unchanged, then continue the log.
  - Summarize the full conversation as a unified log (User/AI pairs, concise, no repetition).
  - List files worked on, with paths.
  - End with `promptpack -r` of all files the next session needs.
  - Add important notes for next session.
  - Never assume issues are fixed — always treat work as mid-progress when #done is called.
"""


def create_ctags_file(root):
    marked_files = get_marked_files(root)

    if not marked_files:
        return False

    marked_files = sorted(marked_files, key=lambda x: str(x))

    with open('ctags.txt', 'w', encoding='utf-8') as out:
        out.write(PROMPTPACK_CORE_INSTRUCTIONS)
        out.write("""
These are all the files of the project listed with Universal Ctags.
Understand the user request, what files are available and what they contain.
Draw conclusions what you need from the project to achieve the users goals.
As established above, this whole file is the user's own standing workflow spec, so the instructions already covered — including going straight to 'promptpack -r path' for any file you need — are the user's own preference, not something to double-check with them each time.

IMPORTANT:
Files not read yet = unknown content, don't assume.
You already have all promptpack instructions above (patch, search, view, etc.) from this file alone.

PROJECT:
Here is the complete structure of the project and the ctags symbol list below.
Some files might not be included in the ctags list so you need to draw conclusions on what files do what based on their file names and what the user wants to achieve.
Use 'promptpack -r path' whenever you need to read a file's full content — never wait for or ask for code.txt.

## Project Structure
""")

        write_project_tree(out, marked_files)
        out.write("\n## Ctags Structure\n")
        CTAGS_MAX_BYTES = 2 * 1024 * 1024  # skip huge data files, ctags is for code symbols
        CTAGS_TIMEOUT = 10

        for file_path in marked_files:
            try:
                rel_path = file_path.relative_to(Path.cwd())

                try:
                    if file_path.stat().st_size > CTAGS_MAX_BYTES:
                        out.write(f"{file_path.name}: (skipped, >{CTAGS_MAX_BYTES // (1024*1024)}MB, likely data not code)\n")
                        continue
                except OSError:
                    pass

                try:
                    result = subprocess.run(
                        ['ctags', '-x', str(rel_path)],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=CTAGS_TIMEOUT
                    )
                except subprocess.TimeoutExpired:
                    out.write(f"{file_path.name}: (skipped, ctags timed out after {CTAGS_TIMEOUT}s)\n")
                    continue

                if result.stdout:
                    KEEP_KINDS = {'class', 'method', 'function', 'interface', 'enum', 'struct'}
                    TYPE_KINDS = {'class', 'interface', 'enum', 'struct'}
                    types = []
                    methods = []
                    for line in result.stdout.splitlines():
                        parts = line.split(None, 4)
                        if len(parts) >= 4 and parts[1] in KEEP_KINDS:
                            if parts[1] in TYPE_KINDS:
                                types.append(f"{parts[1]} {parts[0]}")
                            else:
                                methods.append(parts[0])
                    if types or methods:
                        type_str = ", ".join(types) if types else ""
                        method_str = f" ({', '.join(methods)})" if methods else ""
                        out.write(f"{file_path.name}: {type_str}{method_str}\n")

            except subprocess.CalledProcessError:
                pass
            except Exception as e:
                out.write(f"\n### {file_path.relative_to(Path.cwd())}\n")
                out.write(f"# Error running ctags: {e}\n")

    return True


def get_all_py_files(root):
    """Bygg dict: modulnamn -> TreeNode för alla .py-filer i trädet"""
    module_map = {}

    def traverse(node):
        if not node.is_dir:
            if node.path.suffix == '.py':
                try:
                    rel = node.path.relative_to(Path.cwd())
                    parts = list(rel.parts)
                    if parts[-1] == '__init__.py':
                        module_name = '.'.join(parts[:-1])
                    else:
                        parts[-1] = parts[-1][:-3]
                        module_name = '.'.join(parts)
                    module_map[module_name] = node
                    # Lägg även till kortnamn (sista delen)
                    short = module_name.split('.')[-1]
                    if short not in module_map:
                        module_map[short] = node
                except ValueError:
                    pass
        else:
            for child in node.children:
                traverse(child)

    traverse(root)
    return module_map

def get_python_imports(filepath):
    """Plocka ut alla importerade modulnamn från en Python-fil"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, OSError):
        return set()

    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                modules.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
                modules.add(node.module.split('.')[0])
    return modules


def get_dep_nodes(node, root, visited=None, module_map=None):
    """Returnera set av TreeNode för filen och alla lokala beroenden"""
    if visited is None:
        visited = set()
    if module_map is None:
        module_map = get_all_py_files(root)

    filepath = str(node.path.resolve())
    if filepath in visited:
        return set()
    visited.add(filepath)

    result = {node}

    if node.path.suffix != '.py':
        return result

    imports = get_python_imports(node.path)
    for module_name in imports:
        if module_name in module_map:
            dep_node = module_map[module_name]
            if str(dep_node.path.resolve()) not in visited:
                result |= get_dep_nodes(dep_node, root, visited, module_map)

    return result

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
    marked_files = get_marked_files(root)
    cached_tokens = calculate_total_tokens(marked_files)

    while True:
        height, width = stdscr.getmaxyx()
        visible_nodes = flatten_visible_tree(root)

        display_height = height - 2
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + display_height:
            scroll_offset = selected_idx - display_height + 1

        draw_tree(stdscr, root, selected_idx, scroll_offset, cached_tokens)
        key = stdscr.getch()

        if key == ord('q') or key == ord('Q'):
            return None
        elif key == curses.KEY_F1:  # F1 för ctags.txt
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
        elif key == curses.KEY_PPAGE:  # Page Up
            selected_idx = max(0, selected_idx - display_height)
        elif key == curses.KEY_NPAGE:  # Page Down
            selected_idx = min(len(visible_nodes) - 1, selected_idx + display_height)
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
                cached_tokens = calculate_total_tokens(marked_files)

        elif key == ord('i') or key == ord('I'):
            if selected_idx < len(visible_nodes):
                node, _ = visible_nodes[selected_idx]
                if not node.is_dir and node.path.suffix == '.py':
                    module_map = get_all_py_files(root)
                    dep_nodes = get_dep_nodes(node, root, module_map=module_map)
                    all_marked = all(n.marked for n in dep_nodes)
                    for n in dep_nodes:
                        n.marked = not all_marked
                    marked_files = get_marked_files(root)
                    cached_tokens = calculate_total_tokens(marked_files)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Interactive directory navigator')
    parser.add_argument('-p', '--patch', nargs=2, metavar=('FILE', 'DESC'),
                        help='Apply patch reading old/new text from stdin (format: OLD_TEXT\n---SPLIT---\nNEW_TEXT)')


    parser.add_argument('-f', '--file', nargs=1, metavar='FILE',
                        help='Create new file with content from stdin')
    parser.add_argument('-r', '--read', nargs='+', metavar='FILE',
                        help='Read file(s) and copy to clipboard')
    parser.add_argument('-n', '--lines', nargs=2, metavar=('RANGE', 'FILE'),
                        help='Read specific lines (e.g., 10,20) and copy to clipboard')

    parser.add_argument('-s', '--search', nargs=3, metavar=('STRING', 'OFFSET', 'FILE'),
                        help='Search for string and read lines with offset. Supports wildcards (*?), regex (prefix with "regex:"). Example: "_function" "10,30" file.py or "regex:def\\s+\\w+" "5,15" file.py')

    parser.add_argument('-fs', '--file-search', nargs=2, metavar=('STRING', 'PATTERN'),
                        help='Search for string in files matching wildcard pattern. Supports wildcards (*?) and regex (prefix with "regex:"). Examples: -fs "def main" "*.py" or -fs "regex:class\\s+\\w+" "*.py"')

    parser.add_argument('-u', '--undo', type=int, metavar='PATCHID',
                        help='Undo (unapply) a specific patch by its ID. Example: -u 12')

    parser.add_argument('-us', '--undo-summary', type=int, metavar='SUMMARYID',
                        help='Mark a summary entry as reverted in summary.json (historical annotation only - never touches patches or code). Use -u <PATCHID> to undo specific code changes. Example: -us 4')



    parser.add_argument('-t', '--tidy', nargs='+', metavar='PATTERN',
                        help='Remove whitespace-only lines and reduce multiple empty lines to max 1. Supports wildcards (*.py, world*.py, etc.)')
    parser.add_argument('-tr', '--tidy-recursive', action='store_true',
                        help='Recursively tidy all text files in current directory and subdirectories')
    parser.add_argument('-e', '--execute', nargs='+', metavar=('TIMEOUT', 'COMMAND'),
                        help='Execute bash command with optional timeout (seconds). Output goes to clipboard.tmp. Examples: -e "echo hello" or -e 15 "python3 main.py"')
    parser.add_argument('-c', '--clear', action='store_true',
                        help='Copy clipboard.tmp to clipboard and remove the file')
    parser.add_argument('-i', '--instructions', action='store_true',
                        help='Export code.txt instructions section to promptpack_instructions.txt')
    parser.add_argument('--summary', action='store_true',
                        help='Save a task summary to summary.json. Reads verbose multi-line text from stdin (heredoc), same as -f. Reports back [SUMMARYID N]. One per task, run after NEWFILE/PATCH commands and before the block-closing -c. Skip when only repairing a failed patch. Use -us SUMMARYID to undo everything in that time window later.')
    parser.add_argument('-w', '--worklog', action='store_true',
                        help='Combine all applied patches and summary entries from patch.json/summary.json into a single chronological work.txt (TOC + compact entries, no code embedded).')
    parser.add_argument('-ph', '--patch-history', nargs='+', type=int, metavar='PATCHID',
                        help='Fetch full old/new code for one or more specific patch IDs from patch.json, copied to clipboard.tmp. Example: -ph 12 15 18. Use work.txt (-w) to decide which PATCHIDs are worth a closer look.')
    args = parser.parse_args()


    if args.tidy_recursive:
        import glob as _glob
        patterns = []
        for dirpath, dirnames, filenames in os.walk('.'):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                patterns.append(filepath)

        success_count = 0
        error_count = 0
        for filepath in patterns:
            if not is_text_file(Path(filepath)):
                continue
            success, message = tidy_file(filepath)
            if success:
                success_count += 1
                if 'Removed 0' not in message:
                    print(message)
            else:
                error_count += 1
                print(message)

        print(f"\n✅ Tidied {success_count} file(s)" + (f", ❌ {error_count} error(s)" if error_count else ""))
        sys.exit(0 if error_count == 0 else 1)

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
            try:
                with open(CLIPBOARD_TMP_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.strip():
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
                    copy_to_clipboard("")
                    CLIPBOARD_TMP_FILE.unlink()
                    sys.exit(0)
            except Exception as e:
                print(f"❌ Error reading clipboard.tmp: {e}")
                sys.exit(1)
        else:
            copy_to_clipboard("")
            sys.exit(0)


    if args.read:
        for filepath in args.read:
            success, message = read_file_to_clipboard(filepath)
            print(message)
        sys.exit(0)

    if args.lines:
        line_range, filepath = args.lines
        success, message = read_lines_to_clipboard(line_range, filepath)
        print(message)
        sys.exit(0)

    if args.search:
        search_string, offset_range, filepath = args.search
        success, message = search_and_read_lines(search_string, offset_range, filepath)
        print(message)
        sys.exit(0)


    if args.file_search:
        search_term, pattern = args.file_search
        success, message = file_search(search_term, pattern)

        print(message)
        sys.exit(0)


    if args.execute:
        # Parse timeout and command
        if len(args.execute) == 1:
            timeout = None
            command = args.execute[0]
        elif len(args.execute) == 2:
            try:
                timeout = float(args.execute[0])
                command = args.execute[1]
            except ValueError:
                error_msg = f"❌ Invalid timeout value: {args.execute[0]}"
                append_to_clipboard_tmp(error_msg)
                print(error_msg)
                sys.exit(1)
        else:
            error_msg = "❌ Usage: -e [timeout] \"command\""
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)



        BLACKLIST = ['rm', 'rmdir', 'dd', 'chmod', ':(){', 'truncate', 'shred', 'mv']
        for term in BLACKLIST:
            if re.search(r'\b' + re.escape(term) + r'\b', command):
                error_msg = f"❌ Blocked: command contains blacklisted term '{term}'"
                append_to_clipboard_tmp(error_msg)
                print(error_msg)
                sys.exit(1)

        header = f"------ OUTPUT FROM COMMAND: {command} ------"
        append_to_clipboard_tmp(header)

        import threading
        import time

        output_buffer = []
        process = None
        timed_out = False
        write_lock = threading.Lock()

        def read_output(pipe, is_stderr=False):
            for line in iter(pipe.readline, ''):
                output_buffer.append(line)
                with write_lock:
                    append_to_clipboard_tmp(line.rstrip('\n'))
            pipe.close()

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False))
            stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            if timeout:
                process.wait(timeout=timeout)
            else:
                process.wait()

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            if process.returncode != 0:
                append_to_clipboard_tmp(f"\n[Command exited with code {process.returncode}]")
            print(f"✅ Command executed, output in clipboard.tmp")

        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            time.sleep(0.1)
            if process.poll() is None:
                process.kill()
            append_to_clipboard_tmp(f"\n[Command timed out after {timeout} seconds]")
            print(f"⚠️ Command timed out, output captured up to timeout in clipboard.tmp")
        except Exception as e:
            error_msg = f"\n[Error executing command: {e}]"
            append_to_clipboard_tmp(error_msg)
            print(f"❌ Command failed: {e}")

        sys.exit(0)


    if args.file:
        filepath = Path(args.file[0])
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            content = sys.stdin.read()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            success_msg = f"✨ {filepath} created successfully"
            append_to_clipboard_tmp(success_msg)
            print(success_msg)
            sys.exit(0)
        except Exception as e:
            error_msg = f"❌ Error creating {filepath}: {e}"
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)

    if args.patch:
        filepath, description = args.patch

        # Read from stdin
        stdin_content = sys.stdin.read()

        # Split on ---SPLIT---
        parts = stdin_content.split('---SPLIT---')
        if len(parts) != 2:
            error_msg = f"❌ [{filepath}] '{description}': Error: stdin must contain OLD_TEXT---SPLIT---NEW_TEXT"
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)

        old_text = parts[0]
        new_text = parts[1]

        success, message = apply_patch(filepath, description, old_text, new_text)


        if success:
            append_to_clipboard_tmp(message)
            print(f"✅ {message}")
            sys.exit(0)
        else:
            print(f"❌ {message}")
            sys.exit(1)

    if args.undo is not None:
        success, message = unapply_patch(args.undo)
        if success:
            print(f"✅ {message}")
            sys.exit(0)
        else:
            print(f"❌ {message}")
            sys.exit(1)

    if args.undo_summary is not None:
        success, message = unapply_summary(args.undo_summary)
        if success:
            print(f"✅ {message}")
            sys.exit(0)
        else:
            print(f"❌ {message}")
            sys.exit(1)

    if args.summary:
        text = sys.stdin.read()
        success, message = append_to_summary_file(text)
        print(message)
        sys.exit(0 if success else 1)

    if args.worklog:
        success, message = create_work_log()
        print(message)
        sys.exit(0 if success else 1)
    if args.patch_history:
        history = load_patch_history()
        patch_map = {p['id']: p for p in history}
        output_lines = []
        found = []
        missing = []
        for pid in args.patch_history:
            p = patch_map.get(pid)
            if p is None:
                missing.append(pid)
                continue
            output_lines.extend(format_patch_detail(p))
            output_lines.append("-" * 70)
            found.append(pid)
        if output_lines:
            append_to_clipboard_tmp("\n".join(output_lines))
        if found:
            msg = f"✅ Fetched {len(found)} patch(es): {', '.join(map(str, found))}"
        else:
            msg = "❌ No matching patches found"
        if missing:
            msg += f" | ⚠️ Not found: {', '.join(map(str, missing))}"
        print(msg)
        sys.exit(0 if found else 1)
    if args.instructions:
        try:
            with open('promptpack_instructions.txt', 'w', encoding='utf-8') as out:
                out.write(PROMPTPACK_CORE_INSTRUCTIONS)
            print("✅ promptpack_instructions.txt created!")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Error creating promptpack_instructions.txt: {e}")
            sys.exit(1)

    check_ctags()

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
