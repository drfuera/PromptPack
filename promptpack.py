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
import hmac
import secrets
import tempfile
import textwrap
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPTPACK_FILE = Path(__file__).resolve().parent / 'files.json'
PROMPTPACK_LEGACY_FILES = [Path(__file__).resolve().parent / '.promptpack',   # old line format
                           Path.home() / '.promptpack']

PATCH_HISTORY_FILE = Path('patch.json')
SUMMARY_HISTORY_FILE = Path('summary.json')
CLIPBOARD_TMP_FILE = Path('clipboard.tmp')
TEXT_CHECK_BYTES = 8192

def _rel_path(p):
    """Path relative to the current directory, for display only. Falls back to
    the path itself when it lies outside cwd (absolute path elsewhere, symlink
    pointing out of the project) instead of raising ValueError."""
    p = Path(p)
    try:
        return p.relative_to(Path.cwd())
    except ValueError:
        return p

class HistoryCorruptError(Exception):
    """patch.json / summary.json exists but cannot be read as a JSON list."""

def _atomic_write_text(path, text):
    """Write text so a crash/Ctrl-C can never leave a half-written file:
    write to <name>.tmp, fsync, then os.replace (atomic on the same filesystem)."""
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

def _backup_corrupt_file(path):
    """Keep a copy of an unreadable history file (name carries a content hash,
    so repeated runs do not pile up identical copies). Returns the name or None."""
    try:
        data = path.read_bytes()
        backup = path.with_name(f"{path.name}.corrupt-{hashlib.sha256(data).hexdigest()[:8]}")
        if not backup.exists():
            backup.write_bytes(data)
        return backup.name
    except OSError:
        return None

def _load_json_history(path):
    """Load a history file. [] only when the file does not exist. A file that
    exists but is unreadable raises HistoryCorruptError instead of silently
    returning [] - the next save would overwrite the whole history and PATCHIDs /
    SUMMARYIDs the AI has already seen would be handed out again."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("top-level JSON value is not a list")
        return data
    except OSError as e:
        raise HistoryCorruptError(f"Cannot read {path.name}: {e}. Nothing was changed.")
    except ValueError as e:   # JSONDecodeError and UnicodeDecodeError are ValueErrors
        backup = _backup_corrupt_file(path)
        saved = f" A copy was saved as {backup}." if backup else ""
        raise HistoryCorruptError(
            f"{path.name} is corrupt ({e}). Nothing was changed and no new history was started.{saved} "
            f"Repair {path.name} (a JSON list) or delete it to start a fresh history, then resend the command.")

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

            rel_path = _rel_path(filepath)
            stats = f"Removed {removed_lines} duplicate empty lines, {original_whitespace} trailing whitespace chars"
            results.append(f"✅ 🧹 Tidied {rel_path} | {stats}")
            success_count += 1

        except Exception as e:
            results.append(f"❌ Error tidying {filepath}: {e}")
            error_count += 1

    summary = f"\n✅ 🧹 Tidied {success_count} file(s)" + (f", ❌ {error_count} error(s)" if error_count > 0 else "")
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

def _read_legacy_lines():
    """Old .promptpack line format (HASH|TOKENS|ABSPATH), read once for conversion."""
    entries = {}
    for legacy in PROMPTPACK_LEGACY_FILES:
        if not legacy.exists():
            continue
        try:
            text = legacy.read_text(encoding='utf-8')
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = line.split('|', 2)
            file_hash, tokens, path_str = None, None, line
            if len(parts) == 3:
                try:
                    file_hash, tokens, path_str = parts[0], int(parts[1]), parts[2]
                except ValueError:
                    pass
            entries.setdefault(path_str.strip(), {'hash': file_hash, 'tokens': tokens})
    return entries

def _write_json_cache(files):
    """Write files.json (atomic). Entries are sorted by path so diffs stay small."""
    data = {'version': 1, 'files': dict(sorted(files.items()))}
    _atomic_write_text(PROMPTPACK_FILE, json.dumps(data, indent=2, ensure_ascii=False) + '\n')

def _read_files_cache():
    """The "files" section of files.json: {absolute path: {"hash", "tokens"}}. When files.json
    does not exist yet, the old .promptpack files are converted once and written as files.json."""
    if PROMPTPACK_FILE.exists():
        try:
            with open(PROMPTPACK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        files = data.get('files') if isinstance(data, dict) else None
        return files if isinstance(files, dict) else {}
    legacy = _read_legacy_lines()
    if legacy:
        try:
            _write_json_cache(legacy)
        except OSError:
            pass
    return legacy

def load_promptpack():
    """Cached entries for files under the current project: {absolute Path: {'hash', 'tokens'}}."""
    try:
        cwd = Path.cwd().resolve()
        entries = {}
        for path_str, info in _read_files_cache().items():
            path = Path(path_str)
            if not path.is_absolute() or not isinstance(info, dict):
                continue
            abs_path = path.resolve()
            try:
                abs_path.relative_to(cwd)
            except ValueError:
                continue
            if abs_path.exists():
                entries[abs_path] = {'hash': info.get('hash'), 'tokens': info.get('tokens')}
        return entries
    except Exception:
        return {}

def save_promptpack(marked_files):
    """Write the marked files to files.json with content hash and token count, so unchanged
    files never get re-tokenized. Entries for other projects are kept. Returns total tokens."""
    try:
        cwd = Path.cwd().resolve()
        old_cache = load_promptpack()

        merged = {}
        for path_str, info in _read_files_cache().items():
            path = Path(path_str)
            if not path.is_absolute():
                continue
            abs_path = path.resolve()
            try:
                abs_path.relative_to(cwd)
            except ValueError:
                if abs_path.exists():
                    merged[path_str] = info

        total_tokens = 0
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
            merged[str(resolved)] = {'hash': file_hash, 'tokens': tokens}

        _write_json_cache(merged)
        return total_tokens

    except Exception as e:
        append_to_clipboard_tmp(f"⚠️ Warning: Could not save files.json: {e}")
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



        rel_path = _rel_path(filepath)

        if start < 1 or start > end:
            error_msg = f"❌ {rel_path}: Invalid range {start},{end} (file has {len(lines)} lines)"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg
        header = f"\n------ {rel_path} ------\n"
        selected_with_numbers = header
        for i, line in enumerate(lines[start-1:end], start=start):
            selected_with_numbers += f"{i}: {line}"

        success_msg = f"📄 Read lines {start}-{end} from {rel_path}"
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
_STRONG_REGEX_HINT = re.compile(r'\\[|sSwWdDbBtnr]|\(\?')
# '+' and '{' are ambiguous: they are just as common in code ("a + b", "i += 1", "n++")
_WEAK_REGEX_HINT = re.compile(r'(?<![*?])[+{]')
_REGEX_HINT = re.compile(_STRONG_REGEX_HINT.pattern + '|' + _WEAK_REGEX_HINT.pattern)

def _grep_to_python_regex(s):
    """Convert grep-style regex escapes to Python: \| → |"""
    return re.sub(r'\\\|', '|', s)

def _resolve_search(s):
    """Return (pattern, use_regex, auto_promoted).
    - explicit 'regex:' prefix  → regex, not auto
    - unambiguous regex escapes → regex, auto (see _search_strategies)
    - wildcards (* ?)           → glob, not regex
    - else                      → literal
    """
    if s.startswith('regex:'):
        return _grep_to_python_regex(s[6:]), True, False
    if _REGEX_HINT.search(s):
        return _grep_to_python_regex(s), True, True   # auto-promote silently
    return s, False, False     # glob or literal, decided by caller

def _search_strategies(raw):
    """Ordered list of (search_type, shown_string, match_func) to try for a -s/-fs
    search string; the first strategy that finds anything wins. Raises re.error
    for an invalid explicit 'regex:' pattern.
    - 'regex:' prefix            -> regex only
    - strong regex escapes (\\s \\d (?: ...) -> regex first, literal text as fallback
    - only '+' / '{' (ambiguous)  -> LITERAL first, regex as fallback, so searching
                                    for "i += 1" or "a + b" finds that exact text
    - wildcards (* ?)            -> glob;  anything else -> literal"""
    pattern, use_regex, auto = _resolve_search(raw)
    low = raw.lower()
    literal = ('literal', raw, lambda line: low in line.lower())
    if use_regex:
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error:
            if not auto:
                raise
            return [literal]
        regex = ('regex', pattern, lambda line: rx.search(line) is not None)
        if not auto:
            return [regex]
        return [literal, regex] if not _STRONG_REGEX_HINT.search(raw) else [regex, literal]
    if '*' in pattern or '?' in pattern:
        wl = pattern.lower()
        return [('wildcard', pattern, lambda line: fnmatch.fnmatch(line.lower(), f"*{wl}*"))]
    return [literal]

def search_and_read_lines(search_string, offset_range, filepath):
    """Search for string and show lines with offset. Supports wildcards (* ?) and regex (prefix with 'regex:')"""
    filepath = Path(filepath)


    if not filepath.exists():
        error_msg = f"File not found: {filepath}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg


    try:
        strategies = _search_strategies(search_string)
    except re.error as e:
        error_msg = f"❌ Invalid regex pattern: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg
    first_string = strategies[0][1]
    has_wildcards = strategies[0][0] == 'wildcard'

    try:
        # Parse offset range (e.g., "10,30" means 10 lines before, 30 lines after)
        before, after = map(int, offset_range.split(','))
        before = abs(before)  # Make sure it's positive

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Find all occurrences; ambiguous patterns are tried as literal text AND as regex
        match_lines = []
        for search_type, search_string, match_func in strategies:
            match_lines = [i for i, line in enumerate(lines, start=1) if match_func(line)]
            if match_lines:
                break

        if not match_lines:
            error_msg = f"String '{first_string}' not found in {filepath}"
            if len(strategies) > 1:
                error_msg += " (tried as literal text and as regex; prefix with 'regex:' to force regex)"
            if has_wildcards:
                error_msg += f"\n⚠️  If this was a regex pattern, prefix with 'regex:' — e.g. regex:{first_string}"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

        # Use first match but note if not unique
        match_line = match_lines[0]
        is_unique = len(match_lines) == 1

        # Calculate start and end lines (before is negative offset, after is positive)
        start = max(1, match_line - before)
        end = min(len(lines), match_line + after)

        rel_path = _rel_path(filepath)

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
        success_msg = f"🔍 Found '{search_string}' [{search_type}] at line {match_line}{uniqueness_note}, showing lines {start}-{end} from {rel_path}"
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



    try:
        strategies = _search_strategies(search_term)
    except re.error as e:
        error_msg = f"❌ Invalid regex pattern: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg
    search_term = strategies[0][1]

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

    # Search in each file; ambiguous patterns are tried as literal text AND as regex
    def _scan(match_func):
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
                    rel_path = _rel_path(filepath)
                    results.append({
                        'file': rel_path,
                        'hits': file_hits,
                        'count': len(file_hits)
                    })
                    total_hits += len(file_hits)

            except Exception as e:
                # Skip files that can't be read
                continue
        return results, total_hits

    results, total_hits = [], 0
    for _type, _shown, match_func in strategies:
        results, total_hits = _scan(match_func)
        if results:
            break

    if not results:
        error_msg = f"⚠️ No matches found for '{search_term}' in {len(text_files)} file(s)"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    # Format output - compact list format
    output = ""
    for result in results:
        for line_num, line_text in result['hits']:
            output += f"{result['file']}:{line_num}: {line_text}\n"

    append_to_clipboard_tmp(output)
    return True, f"🔍 Found {total_hits} match(es) in {len(results)} file(s)"


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

        rel_path = _rel_path(filepath)
        header = f"\n------ {rel_path} ------\n"
        content_with_header = header + content


        success_msg = f"📄 Read {len(content)} bytes from {rel_path}"
        append_to_clipboard_tmp(content_with_header)
        return True, success_msg

    except Exception as e:
        error_msg = f"Error reading file: {e}"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

def append_to_clipboard_tmp(message):
    """Append message to clipboard.tmp"""
    buffer_path = os.environ.get('PROMPTPACK_MCP_BUFFER')
    if buffer_path:
        # MCP mode: the server collects this command's output instead of clipboard.tmp
        with open(buffer_path, 'a', encoding='utf-8') as f:
            f.write(message if message.endswith('\n') else message + '\n')
        return True
    try:
        with open(CLIPBOARD_TMP_FILE, 'a', encoding='utf-8') as f:
            f.write(message if message.endswith('\n') else message + '\n')
        return True
    except Exception as e:
        print(f"Warning: Could not write to clipboard.tmp: {e}")
        return False

def err_note(message):
    """Append a terminal-only notice that the error is saved in clipboard.tmp"""
    if os.environ.get('PROMPTPACK_MCP_BUFFER'):
        return message     # MCP mode: the result goes back to the AI, not to clipboard.tmp
    return f"{message}\n   ↳ error saved to clipboard.tmp - run promptpack -c"

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
    """Load summary history from JSON (raises HistoryCorruptError if unreadable)"""
    return _load_json_history(SUMMARY_HISTORY_FILE)

def save_summary_history(history):
    """Save summary history to JSON (atomic)"""
    try:
        _atomic_write_text(SUMMARY_HISTORY_FILE, json.dumps(history, indent=2, ensure_ascii=False))
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

def append_to_summary_file(text, about, rating):
    """Save a timestamped summary entry to summary.json.
    Returns: (success: bool, message: str)
    """
    try:
        history = load_summary_history()

        about = (about or '').strip()
        body = text.strip()
        if not about or not body:
            error_msg = "❌ Summary NOT saved: both parts are required: promptpack --summary 'about text' (1-2 dense sentences, as the argument) plus the verbose text via heredoc on stdin. Resend the --summary command."
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

        summary_id = get_next_summary_id()
        timestamp = datetime.now().isoformat()
        claimed = set()
        for prev in history:
            claimed.update(prev.get('patch_ids', []))
        patch_ids = sorted(p['id'] for p in load_patch_history() if p['id'] not in claimed)
        history.append({
            'id': summary_id,
            'timestamp': timestamp,
            'text': body,
            'about': about,
            'rating': rating,
            'patch_ids': patch_ids
        })
        save_summary_history(history)

        success_msg = f"💾 Summary saved [SUMMARYID {summary_id}] (rating {rating}, {len(patch_ids)} patch(es) linked)"
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
    """Load patch history from JSON (raises HistoryCorruptError if unreadable)"""
    return _load_json_history(PATCH_HISTORY_FILE)

def save_patch_history(history):
    """Save patch history to JSON (atomic)"""
    try:
        _atomic_write_text(PATCH_HISTORY_FILE, json.dumps(history, indent=2, ensure_ascii=False))
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

def _scan_code_lines(content):
    """Classify each physical line of Python source with a small scanner
    (tokenize cannot be used: it raises on the very indentation errors we repair).
    Returns one (protected, ends_stmt, last_sig) tuple per line:
      protected - line starts inside a (triple-)quoted string, inside brackets or
                  after a backslash continuation: its leading whitespace is data
                  or alignment, never block structure
      ends_stmt - a logical statement ends on this physical line
      last_sig  - last significant character of the code on the line
                  (comments excluded), '' if none"""
    info = []
    state = None        # None, or the quote string ("'", '"', "'''", '"""') we are inside
    depth = 0
    cont = False
    for line in content.splitlines(keepends=True):
        protected = state is not None or depth > 0 or cont
        cont = False
        last_sig = ''
        esc_nl = False
        j, L = 0, len(line)
        while j < L:
            ch = line[j]
            if state is not None:
                if ch == '\\':
                    if j + 1 >= L or line[j + 1] in '\r\n':
                        esc_nl = True
                    j += 2
                    continue
                if line.startswith(state, j):
                    j += len(state)
                    state = None
                    last_sig = '"'
                    continue
                j += 1
                continue
            if ch == '#':
                break
            if ch in '\'"':
                q = ch * 3 if line.startswith(ch * 3, j) else ch
                state = q
                j += len(q)
                continue
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth = max(0, depth - 1)
            if ch == '\\' and line[j + 1:].strip('\r\n') == '':
                cont = True
                j += 1
                continue
            if not ch.isspace():
                last_sig = ch
            j += 1
        if state is not None and len(state) == 1 and not esc_nl:
            state = None            # unterminated single-line string: syntax error anyway
        info.append((protected, state is None and depth == 0 and not cont, last_sig))
    return info

def _guess_indent_unit(lines, info, span):
    """Indent width used by the file itself (taken from lines outside the patch
    span that open a block); 4 if it cannot be determined."""
    counts = {}
    prev_indent, prev_opener = None, False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        protected, ends_stmt, last_sig = info[i]
        if not stripped.strip() or (not protected and stripped.startswith('#')):
            continue
        cur = len(line) - len(stripped)
        if (not protected and prev_opener and prev_indent is not None and cur > prev_indent
                and not (span[0] <= i < span[1])):
            counts[cur - prev_indent] = counts.get(cur - prev_indent, 0) + 1
        if not protected:
            prev_indent = cur
        prev_opener = ends_stmt and last_sig == ':'
    return max(counts, key=counts.get) if counts else 4

def fix_indentation_errors(content, span=None):
    """
    Repairs indentation errors in the lines the patch just wrote.
    span = (first_line_index, end_line_index_exclusive) of the patched lines;
    without a span nothing is changed.
    ONLY leading whitespace of lines inside the span is touched. Lines outside the
    span, blank lines, comments, string/docstring bodies, lines inside brackets and
    backslash continuations are never modified. Files indented with tabs are not
    handled (nothing is changed, so the caller reports the syntax error).
    Returns: (fixed_content: str, was_fixed: bool)
    """
    if span is None or span[0] >= span[1]:
        return content, False

    lines = content.splitlines(keepends=True)
    info = _scan_code_lines(content)
    for i, line in enumerate(lines):
        if not info[i][0] and '\t' in line[:len(line) - len(line.lstrip())]:
            return content, False

    unit = _guess_indent_unit(lines, info, span)
    out = list(lines)
    stack = [0]
    prev_opener = False

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        protected, ends_stmt, last_sig = info[i]
        if not stripped.strip() or (not protected and stripped.startswith('#')):
            continue
        if protected:
            prev_opener = ends_stmt and last_sig == ':'
            continue

        cur = len(line) - len(stripped)
        if span[0] <= i < span[1]:
            if prev_opener:
                target = stack[-1] + unit
                stack.append(target)
            else:
                while len(stack) > 1 and cur < stack[-1]:
                    stack.pop()
                target = stack[-1]
            if cur != target:
                out[i] = ' ' * target + stripped
        else:
            # outside the patch: what is on disk is the truth, only track it
            if prev_opener:
                if cur > stack[-1]:
                    stack.append(cur)
            else:
                while len(stack) > 1 and cur < stack[-1]:
                    stack.pop()
        prev_opener = ends_stmt and last_sig == ':'

    fixed_content = ''.join(out)
    return fixed_content, fixed_content != content

def validate_and_fix_python_syntax(filepath, content, span=None):
    """
    Validates Python syntax and fixes indentation errors in the patched lines (span).
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
            fixed_content, was_fixed = fix_indentation_errors(content, span)

            # Verify that the fix works
            ast.parse(fixed_content)
            return fixed_content, True, ""

        except (IndentationError, SyntaxError) as e:
            return content, False, f"Could not auto-fix: {e.msg}"
    except SyntaxError as e:
        return content, False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return content, False, ""

def _line_span(content, pos, text):
    """(first_line_index, end_line_index_exclusive) of the lines that `text`,
    inserted at character offset `pos`, occupies in `content`."""
    start = content.count('\n', 0, pos)
    return (start, start + len(text.splitlines()))

def _changed_lines(before, after):
    return sum(1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b)

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

def _flexible_pattern(old_text, new_text=''):
    """Regex for whitespace-agnostic matching of old_text (or None).
    Whitespace BETWEEN tokens matches any whitespace run. Whitespace at the very
    start/end of old_text must not become a greedy \\s+: that used to swallow the
    blank lines and indentation of the neighbouring lines. Instead a trailing
    newline consumes only the rest of that line plus one line break. Extra blank
    lines at the end of old_text are consumed only when new_text ends with blank
    lines too (or deletes the text), so a stray empty line in old_text cannot
    delete the blank line between two functions. Leading indentation consumes the
    file's real indentation of that line."""
    m = re.match(r'(\s*)(.*?)(\s*)\Z', old_text, re.S)
    lead, core, trail = m.groups()
    if not core:
        return None
    body = r'\s+'.join(re.escape(part) for part in re.split(r'\s+', core))
    lead_indent = lead.rsplit('\n', 1)[-1]
    prefix = r'(?:(?<![^\n])[ \t]*)?' if lead_indent else ''
    nl = trail.count('\n')
    if nl:
        new_nl = new_text[len(new_text.rstrip()):].count('\n')
        blanks = nl - 1 if not new_text.strip() else max(0, min(nl, new_nl) - 1)
        suffix = r'[ \t]*(?:\n|\Z)' + (r'(?:[ \t]*\n){0,%d}' % blanks if blanks else '')
    elif trail:
        suffix = r'[ \t]*'
    else:
        suffix = ''
    return prefix + body + suffix

# split in two on purpose: promptpack refuses the literal marker in a patch's new_text,
# and this file is itself patched with promptpack
_WILDCARD_MARK = '***WILDCARD_' + 'PROMPTPACK***'

_CTX_CHARS = 80     # how much text on each side of a patch is remembered

def _record_context(content, new_text, hint):
    """(ctx_before, ctx_after): the text directly around new_text as it now sits in
    `content`, at the occurrence closest to offset `hint`. (None, None) if new_text
    is empty or not found."""
    if not new_text:
        return None, None
    best = None
    i = content.find(new_text)
    while i != -1:
        if best is None or abs(i - hint) < abs(best - hint):
            best = i
        i = content.find(new_text, i + 1)
    if best is None:
        return None, None
    end = best + len(new_text)
    return content[max(0, best - _CTX_CHARS):best], content[end:end + _CTX_CHARS]

def _locate_patch(content, patch):
    """Offsets where patch['new_text'] sits in `content` together with the text that
    surrounded it when it was applied. Either side is enough, so a neighbouring
    patch that changed one side does not hide it; identical text somewhere else is
    not accepted. Entries without recorded context (older history) fall back to a
    guarded plain search."""
    new = patch['new_text']
    cb, ca = patch.get('ctx_before'), patch.get('ctx_after')
    found = []
    if not cb and not ca:
        # Older entry without recorded context: the position cannot be checked, but if
        # the text this patch replaced is back in the file (and new_text does not
        # contain it) the patch is gone - git checkout or a manual edit.
        old = patch.get('actual_old_text') or patch.get('old_text', '')
        if old and _WILDCARD_MARK not in old and old not in new and old in content:
            return found
    i = content.find(new)
    while i != -1:
        if not cb and not ca:
            found.append(i)
        else:
            ok_b = bool(cb) and content[max(0, i - len(cb)):i] == cb
            ok_a = bool(ca) and content[i + len(new):i + len(new) + len(ca)] == ca
            if ok_b or ok_a:
                found.append(i)
        i = content.find(new, i + 1)
    return found

def _patch_still_in_effect(prev, content):
    """Is an 'applied' history entry really still present in the file? False when
    the file was restored or edited outside promptpack (git checkout, manual edit)."""
    new = prev.get('new_text', '')
    if new:
        return bool(_locate_patch(content, prev))
    old = prev.get('actual_old_text') or prev.get('old_text', '')
    if not old or _WILDCARD_MARK in old:
        return True     # cannot tell
    return old not in content

def apply_patch(filepath, description, old_text, new_text):
    """
    Apply a patch and save in history
    Returns: (success: bool, message: str)
    """

    filepath = Path(filepath).resolve()

    if not filepath.exists():
        rel_path = _rel_path(Path(filepath))
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
        rel_path = _rel_path(filepath)
        file_col = f"{rel_path}".ljust(40)
        desc_col = f"{description}".ljust(50)
        error_msg = f"❌ {file_col} {desc_col} ***WILDCARD_PROMPTPACK*** is not allowed in new_text"
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # Fail-safe: reject a patch identical to one that is already applied
        _norm_new = new_text[1:] if new_text.startswith('\n') else new_text
        _hist = load_patch_history()
        _stale = False
        for _prev in _hist:
            if (_prev.get('applied')
                    and _prev.get('filepath') == str(filepath)
                    and _prev.get('old_text') == old_text
                    and _prev.get('new_text') in (new_text, _norm_new)):
                if not _patch_still_in_effect(_prev, original_content):
                    # file was restored/edited outside promptpack: this entry is stale
                    # and must not lock the same patch out forever
                    _prev['applied'] = False
                    _prev['stale'] = True
                    _stale = True
                    continue
                _rel = _rel_path(filepath)
                error_msg = (f"❌ {str(_rel).ljust(40)} {description.ljust(50)} "
                             f"Duplicate patch: identical patch already applied "
                             f"[PATCHID {_prev['id']}] - undo it first with -u if you want to reapply")
                append_to_clipboard_tmp(error_msg)
                return False, error_msg
        if _stale:
            save_patch_history(_hist)


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

            rel_path = _rel_path(filepath)
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

            validated_content, was_fixed, err = validate_and_fix_python_syntax(
                filepath, new_content, _line_span(new_content, wc_start, new_text))
            if err:
                full_error = f"❌ {file_col} {desc_col} {err}"
                append_to_clipboard_tmp(full_error)
                return False, full_error

            if validated_content == original_content:
                full_error = f"❌ {file_col} {desc_col} Patch changes nothing: the matched text already equals new_text (file left untouched)"
                append_to_clipboard_tmp(full_error)
                return False, full_error

            if was_fixed:
                new_text = _synced_new_text(new_content, validated_content, wc_start, new_text)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(validated_content)

            ctx_before, ctx_after = _record_context(validated_content, new_text, wc_start)
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
                'ctx_before': ctx_before,
                'ctx_after': ctx_after,
                'delete_anchor_before': delete_anchor_before,
                'delete_anchor_after': delete_anchor_after,
                'applied': True
            })
            save_patch_history(history)

            icon = "🔧" if was_fixed else "🧩"
            indicators_wc = ["wildcard match"]
            if was_fixed:
                indicators_wc.append(f"indentation auto-fixed: {_changed_lines(new_content, validated_content)} line(s)")
            if desc_truncated:
                indicators_wc.append("description truncated to 10 words")
            indicator_str = f" ({', '.join(indicators_wc)})"
            success_msg = f"{icon} {file_col} {desc_col} Applied successfully{indicator_str} [PATCHID {patch_id}]"
            return True, success_msg

        if old_text == '':
            rel_path = _rel_path(filepath)
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(50)
            error_msg = f"❌ {file_col} {desc_col} old_text is empty — nothing to match (use NEW FILE for pure insertions)"
            append_to_clipboard_tmp(error_msg)
            return False, error_msg

        # Try exact match first
        used_flexible_whitespace = False
        used_tidy_matching = False
        match_start = None

        if old_text in original_content:
            count = original_content.count(old_text)

            if count > 1:
                rel_path = _rel_path(filepath)
                file_col = f"{rel_path}".ljust(40)
                desc_col = f"{description}".ljust(50)
                error_msg = f"❌ {file_col} {desc_col} Old text appears {count} times in file (must be unique)"
                append_to_clipboard_tmp(error_msg)
                return False, error_msg
            actual_old_text = old_text
            match_start = original_content.index(old_text)

        else:
            # Try whitespace-agnostic matching
            used_flexible_whitespace = True
            pattern = _flexible_pattern(old_text, new_text)
            matches = list(re.finditer(pattern, original_content)) if pattern else []

            if len(matches) == 0:
                # Try tidy matching as last resort
                used_tidy_matching = True
                tidied_old = tidy_text(old_text)
                tidied_content = tidy_text(original_content)

                if tidied_old in tidied_content:
                    count = tidied_content.count(tidied_old)

                    if count > 1:
                        rel_path = _rel_path(filepath)
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
                        rel_path = _rel_path(filepath)
                        file_col = f"{rel_path}".ljust(40)
                        desc_col = f"{description}".ljust(50)
                        error_msg = f"❌ {file_col} {desc_col} Old text not found in file (even with tidy matching)"
                        append_to_clipboard_tmp(error_msg)
                        return False, error_msg
                else:
                    rel_path = _rel_path(filepath)
                    file_col = f"{rel_path}".ljust(40)
                    desc_col = f"{description}".ljust(50)
                    error_msg = f"❌ {file_col} {desc_col} Old text not found in file (even with flexible whitespace and tidy)"
                    append_to_clipboard_tmp(error_msg)
                    return False, error_msg

            elif len(matches) > 1:

                rel_path = _rel_path(filepath)
                file_col = f"{rel_path}".ljust(40)
                desc_col = f"{description}".ljust(50)
                error_msg = f"❌ {file_col} {desc_col} Old text appears {len(matches)} times in file (must be unique)"
                append_to_clipboard_tmp(error_msg)

                return False, error_msg

            else:
                # Use the actual text from file (with correct whitespace)
                actual_old_text = matches[0].group(0)
                match_start = matches[0].start()

        if match_start is None:
            # tidy matching found the text; locate it by position
            match_start = original_content.find(actual_old_text)
            if match_start == -1:
                rel_path = _rel_path(filepath)
                file_col = f"{rel_path}".ljust(40)
                desc_col = f"{description}".ljust(50)
                error_msg = f"❌ {file_col} {desc_col} Old text matched only after tidy but could not be located in the file"
                append_to_clipboard_tmp(error_msg)
                return False, error_msg

        # Apply tidy to new_text if tidy matching was used
        if used_tidy_matching:
            new_text = tidy_text(new_text)


        if new_text.startswith('\n'):
            new_text = new_text[1:]
        if new_text == '':
            delete_anchor_before, delete_anchor_after = _delete_anchor(
                original_content, match_start, match_start + len(actual_old_text))
        else:
            delete_anchor_before, delete_anchor_after = None, None
        new_content = original_content[:match_start] + new_text + original_content[match_start + len(actual_old_text):]

        # Validate and auto-fix Python syntax (only the patched lines may be re-indented)
        validated_content, was_fixed, error_msg = validate_and_fix_python_syntax(
            filepath, new_content, _line_span(new_content, match_start, new_text))

        # If validation failed, abort the patch

        if error_msg:
            rel_path = _rel_path(filepath)
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(30)
            full_error = f"❌ {file_col} {desc_col} {error_msg}"
            append_to_clipboard_tmp(full_error)
            return False, full_error

        # A patch that leaves the file byte-identical is not a success
        if validated_content == original_content:
            rel_path = _rel_path(filepath)
            file_col = f"{rel_path}".ljust(40)
            desc_col = f"{description}".ljust(50)
            full_error = f"❌ {file_col} {desc_col} Patch changes nothing: the matched text already equals new_text (file left untouched)"
            append_to_clipboard_tmp(full_error)
            return False, full_error

        if was_fixed:
            new_text = _synced_new_text(new_content, validated_content, match_start, new_text)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(validated_content)

        ctx_before, ctx_after = _record_context(validated_content, new_text, match_start)
        history = load_patch_history()
        patch_id = get_next_patch_id()

        patch_entry = {
            'id': patch_id,
            'timestamp': datetime.now().isoformat(),
            'filepath': str(filepath),
            'description': description,
            'old_text': old_text,
            'actual_old_text': actual_old_text,
            'new_text': new_text,
            'ctx_before': ctx_before,
            'ctx_after': ctx_after,
            'delete_anchor_before': delete_anchor_before,
            'delete_anchor_after': delete_anchor_after,
            'applied': True
        }

        history.append(patch_entry)
        save_patch_history(history)

        rel_path = _rel_path(filepath)

        # Format output with column alignment
        icon = "🔧" if was_fixed else "🧩"
        file_col = f"{rel_path}".ljust(40)

        indicators = []
        if used_flexible_whitespace:
            indicators.append("flexible whitespace")
        if used_tidy_matching:
            indicators.append("tidy matching")
        if was_fixed:
            indicators.append(f"indentation auto-fixed: {_changed_lines(new_content, validated_content)} line(s)")
        if desc_truncated:
            indicators.append("description truncated to 10 words")

        indicator_str = f" ({', '.join(indicators)})" if indicators else ""
        desc_col = f"{description}".ljust(50)

        success_msg = f"{icon} {file_col} {desc_col} Applied successfully{indicator_str} [PATCHID {patch_id}]"
        return True, success_msg

    except HistoryCorruptError as e:
        error_msg = str(e)
        append_to_clipboard_tmp(error_msg)
        return False, error_msg

    except Exception as e:
        rel_path = _rel_path(filepath)
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
        rel_path = _rel_path(Path(patch['filepath']))
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
            fix_span = _line_span(content, insert_at, restore_text)
        else:
            _positions = _locate_patch(content, patch)
            new_text_count = len(_positions)
            if new_text_count == 0 and patch['new_text'] in content:
                error_msg = ("Cannot unpatch: the new text exists but not at this patch's original position "
                             "(the file was restored or edited outside promptpack, or later patches changed "
                             "the lines on both sides) - nothing was changed. Re-send the patch if the file "
                             "was restored, otherwise unapply the later patches first")
                append_to_clipboard_tmp(error_msg)
                log_error_to_file(f"Undo failed for patch #{patch_id}", error_msg)
                return False, error_msg
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
            _pos = _positions[0]
            content = content[:_pos] + restore_text + content[_pos + len(patch['new_text']):]
            fix_span = _line_span(content, _pos, restore_text)

        validated_content, was_fixed, syntax_err = validate_and_fix_python_syntax(filepath, content, fix_span)
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
    success_msg = f"🏷️ Summary #{summary_id} marked as reverted (no patches touched — use -u <PATCHID> to undo specific code changes)"
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
        rel_path = _rel_path(Path(patch['filepath']))
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

        validated_content, was_fixed, error_msg = validate_and_fix_python_syntax(
            filepath, new_content, _line_span(new_content, pos, patch['new_text']))
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
        rel_path = _rel_path(Path(p['filepath']))
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
                rel_path = _rel_path(Path(p['filepath']))
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
                rel_path = _rel_path(Path(p['filepath']))
            except Exception:
                rel_path = p['filepath']
            lines.append(f"[{datetime_str}] PATCH #{p['id']} - {rel_path} - {p.get('description', '')}")
        lines.append("-" * 70)
    try:
        with open('work.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True, "📜 work.txt created"
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
        rel_path = _rel_path(file_path)
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

        title = "Patch History - ↑↓: Navigate | PgUp/PgDn: Jump | Delete: Toggle | Esc: Back"
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

        if key == 27:
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


    title = "↑↓: Navigate | PgUp/PgDn: Jump | ←→: Expand | Space: Mark | i: Import deps | F1: ctags | F6: MCP | F12: patches | Esc: Quit"
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
List commands in a table: #patch, #undo, #reset, #done, #outsource, #ask, #dumb, #ideas, #audit, #optimize, #name.

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
- `--summary` takes the ABOUT text as its quoted argument: 1-2 sentences,
  an extremely dense digest of the whole task (files + what + why). A future
  AI sees only this line in the # WORKLOG section of ctags.txt and uses it to
  decide whether to fetch the full text, so it must reflect the summary
  accurately. Keep it plain prose inside double quotes: no double quotes,
  backticks or `$` in it (the shell would interpret them). The verbose text
  goes in the heredoc on stdin. Without both parts the summary is rejected
  and not saved: resend it.
- `--summary` text must be verbose and explanatory, not a one-liner: name
  every file touched in the task and what changed in each, then explain WHY
  (the problem solved or goal served). Write it for a reader with zero
  context on this conversation.
- `--summary` ALSO requires `--rating N` (1, 2 or 3): your judgment of how much
  this task matters for the code and future development. 3 = architecture, data
  format, workflow rules or a decision future work must respect (rare, roughly
  1 task in 8); 2 = new feature or noticeable behavior change; 1 = bugfix,
  docs, cosmetics or small refactor without behavior change. A future AI sees
  only the # WORKLOG section, which keeps old tasks by rating, so rate honestly;
  when unsure between two levels, pick the lower. Without it the summary is
  rejected and not saved: resend it.
- EXCEPTION: debugging patches — adding print/log statements, temporary
  color/highlight markers, or any other diagnostic change made only to
  locate a bug, not to fix it — do NOT get a --summary. Keep patching
  without a summary through as many debugging rounds as it takes. Only the
  patch that applies the actual fix ends the task with --summary, and that
  summary describes the final solution, not the debugging steps taken to
  find it.

# BEST PRACTICES
old_text = whole lines, never a fragment. Always start at the beginning of a line
and end at the end of a line, copied exactly (indentation and trailing text
included) from the file as shown in this conversation. Use 1–3 whole lines that
are unique together. A partial line (just a word, a tag, or a label inside a
line) is NOT a safe match, even if it looks unique.
Verify old_text appears exactly once in the file before patching.
To change one word on a line, still put the whole line in old_text and the whole
corrected line in new_text.

# PATCH FAILURES: SELF-DIAGNOSE FIRST
- A file already shown in this conversation = complete & current. NEVER ask for
  -r/-n/-s of a file you already have, even if a patch against it just failed.
- On "Old text not found" or SyntaxError: stop guessing about overall structure.
  Go straight to old_text made of whole lines (1-3 lines, unique together) taken
  exactly from the file you already have in the conversation, with the original
  indentation.
- If a patch fails twice in a row: switch to a single whole line with exact
  indentation, copied from the file in this conversation. Never shrink old_text
  to a fragment of a line. If you do not have the exact line (the file was not
  shown, or may have changed since), run `promptpack -n <lines> path` to see it
  and then patch the whole line.
- Assume whitespace/indentation mismatch as the likely cause of a SyntaxError,
  not that the file is unknown or has changed. Do not blame special characters
  (å, ä, ö, ≈ etc.) without evidence.
- "Patch changes nothing" = old_text and new_text give the same file (blank
  lines you want kept must also appear in new_text). Send a new_text that
  really differs, or drop the patch.
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
Undo only works where the patch really sits: if the file was restored or
edited outside promptpack (git checkout, manual edit), undo refuses with
"not at this patch's original position" and changes nothing. Do not retry -u
then: re-send the patch instead — the stale history entry no longer blocks it.

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

ABOUT argument: the quoted argument of --summary, 1-2 sentences, as
information-dense as possible (token-cheap, but precise enough that a reader
knows what the task was). It is stored separately as the `about` field and
listed in # WORKLOG of ctags.txt. The heredoc holds only the verbose text.
Plain prose only: no double quotes, backticks or `$` inside it.

RATING argument: `--rating N` after the about text, N = 1, 2 or 3, required. It
grades how much the task matters for the code and for future development, and
decides how long the task stays visible in # WORKLOG (rating 3 stays longest,
rating 1 drops out first). Judge it by: would a future AI that sees only
# WORKLOG make a mistake or redo work if this task were missing?
  3 = architecture, data format, workflow rules, public interface, or a
      decision that future work must respect. Rare.
  2 = new feature or a noticeable behavior change.
  1 = bugfix, docs, cosmetics, small refactor without behavior change.
When unsure between two levels, choose the lower. A bugfix is normally 1,
unless it reveals something future work must know.

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
cat <<'SUMMARY' | promptpack --summary "dense 1-2 sentence about of the task (files, what, why)" --rating 2
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
It grows large on long projects: prefer the # WORKLOG section at the bottom
of this file plus `-log`. Use `-completelog` (see # COMPLETE LOG) when you need
the whole compact history, and -w only when you need every summary in full.

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

# LOG FETCH (full text of specific summaries)
~~~bash
promptpack -log 53 54 55
promptpack -c
~~~
The # WORKLOG section at the bottom of this file is a filtered, chronological
view of the work, one line each: `ID LOG R<n>:about` = a task summary with its
impact rating 1-3, `ID PATCH:description` = a patch. Recent tasks come with
their patch lines, right before the LOG that closes their task; older tasks
are kept only if rated high and show their patch IDs as `[P41-43]` (a range =
every ID in it). Tasks that were filtered out leave gaps in the LOG numbering.
Use it for overview; usually only the last few LOGs matter. To read a summary
in full, fetch it with -log (space- or
comma-separated IDs, several at once for efficiency). To see a patch's code,
use -ph with the PATCH ID. LOG and PATCH IDs are separate number series.
Missing IDs are reported without failing the ones found.

# COMPLETE LOG (every task and patch, unfiltered)
~~~bash
promptpack -completelog
promptpack -c
~~~
The # WORKLOG section in this file is filtered by rating and age. This command
prints the same format with nothing left out: every LOG with its rating and
every PATCH line. It can be long, so use it only when the filtered view is not
enough, for example when a topic is not covered by the LOGs you can see or you
need the history behind an old decision. Then fetch details with -log / -ph.

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
- `#audit` = structured bug and risk review of code (formerly `#test`, still accepted as an alias).
- `#optimize` = structured, language-independent performance review of code, from HTML to C#, GUI to network. Work from evidence: no change is recommended on a hunch alone.
  - Shared rules for #audit and #optimize:
    - Report only. Never write patches while reviewing; patch afterwards, and only after the user okays it. No --summary, since nothing is patched.
    - Fully autonomous: no questions, no waiting for approval between steps, never ask the user to run something or paste output back. When something is unclear, make a reasonable assumption, state it in one line and continue.
    - Modes (`full` is a reserved word, never a target name):
      - `<cmd>` = the patches you wrote in this session plus directly affected code (callers and callees of the changed functions). You may read one or two clearly relevant include or import files, but do not wander further.
      - `<cmd> <target>` = a named function, class or file, changed in this session or not, plus directly affected code.
      - `<cmd> full` = the whole codebase, never in one reply. Plan from the ctags list, prioritize risky parts (#audit: parsing, file I/O, shell; #optimize: likely hot paths), one module per round over several rounds, and state what was reviewed and what was not reached. End every round with one line naming the next module, so a plain 'continue' resumes.
    - Locate and fetch: in session mode use the [PATCHID n] lines in output the user pasted back. Only if the session was restarted via #done, take the patch IDs under the latest LOG lines in # WORKLOG and fetch them with `promptpack -ph <IDs>`. Collect everything needed into ONE promptpack block: current code with -r/-n (even if shown earlier, because indentation may have been auto-corrected when patching) and -fs searches for callers and callees. Skip the block if everything is already in the conversation. This is the only round trip; afterwards run to the final report.
    - STEP 1 = pure reasoning, passes 1-7 in this fixed order, each using the results of the earlier ones. Skip a pass only with a one-line reason, never silently. STEP 2 = pass 8, always mandatory.
    - Every finding: file and line, status VERIFIED or SUSPECTED, plus the fields listed per command. Speculation is always SUSPECTED. A pass without findings says so explicitly.
    - Pass 8 runs in your own environment (code execution tool, sandbox or shell) on copies of the code you were shown. Without one, do not ask the user to run anything: hand-trace concrete values, keep unconfirmed findings SUSPECTED and write 'not executed' (#audit) or 'not measured' (#optimize). Never invent numbers. If something is missing (GPU, display, database, network, hardware), check the pure-logic parts you can isolate and state what stays unchecked.
  - #audit
    - Mindset: review as if someone else wrote the code. Trace real values through it instead of writing 'looks correct'.
    - Extra finding fields: severity (bug = wrong result or data loss / risk / minor remark). A bug needs a concrete input that triggers it.
    - Passes:
      1. Scope: files, functions, and the callers and callees found by the fetch.
      2. Requirements (mandatory in session mode): did the change do exactly what was asked, no more and no less? If not, report it, skip passes 3-7, still run pass 8. In target and full mode compare the code with its purpose (docstring, README, function name) or skip with a stated reason.
      3. Design by Contract: preconditions, postconditions and invariants of each changed function. Passes 4-6 build on them.
      4. Boundary analysis: probe the edges of those contracts (empty, None, one element, extreme values, Unicode, missing files) with concrete values.
      5. Pre-mortem: assume this crashes in a month. Build 3-5 realistic failures from the suspicions in 3-4, plus failure paths (error halfway through, leftover state, resources not closed).
      6. OWASP/CWE/CERT, only if the code touches input, files, paths, shell or parsing: input validation, injection and shell quoting, paths, secrets, resource and error handling, starting from the input sources found in 3.
      7. Consistency and design: project patterns and error handling, names, needless complexity, unused imports, leftover debug prints; in session mode, does the summary match what the patches really do?
      8. Verification: syntax check, linter (pyflakes/ruff or equivalent), existing tests, and a small reproduction for every SUSPECTED bug. Final report: each finding VERIFIED or dropped.
  - #optimize
    - Core model: total cost = how many times something runs x what each run costs, on some resource (CPU, memory, disk, network, GPU, locks or waiting, perceived latency). Every pass reduces one of the two factors or the resource.
    - Extra finding fields: category (algorithmic / redundant work / memory and I/O / concurrency / domain-specific), expected gain (high / medium / low, with the measured figure once available), risk (low / medium / high). VERIFIED = measured or proven by a trace or count (e.g. call count).
    - Passes:
      1. Goal and metric: what should improve (frame time, latency, throughput, memory, startup, size, battery) and for which input size. If the user gave none, pick the most plausible and state it as an assumption.
      2. Domain and toolchain: identify language, runtime, framework and domain(s) (GUI/TUI, graphics, game loop, web front-end or back-end, database, network, CLI/batch, embedded) from files, imports and ctags. Pick matching measurement tools. Every domain claim must be tied to a concrete line of code.
      3. Resource analysis: where does the cost go? Find the hot path (loops, per-frame, per-request or per-event code, anything called N times) and rank candidates by expected share of total cost (Amdahl: a 2% part is not worth a change). Hotspot hypotheses are SUSPECTED until measured.
      4. Workload and complexity: per hotspot, how often and on how much data? Check Big-O in time and memory, nested loops, repeated scans where a map, set or index fits, repeated sorting, work that grows with history. Trace n = 10, 10000, 1000000.
      5. The eight levers, per hotspot, cheapest and safest first: (a) remove the work; (b) do it less often (cache, memoize, dirty flags, debounce); (c) move it out of the hot path (hoist, precompute, init once); (d) do it in bulk (batching, buffering, instancing, fewer round trips); (e) do it lazily (on demand, paging, streaming); (f) do it cheaper (better algorithm or structure, fewer allocations and copies, built-ins, vectorized or native libraries); (g) do it concurrently or off the critical thread, only for a proven bottleneck; (h) do it approximately (lower precision, resolution or level of detail) when exactness is not required.
      6. Domain bottlenecks: apply the typical problems of the domains from pass 2 (N+1 queries, missing indexes, draw calls, state changes, per-frame uploads, UI-thread blocking, redundant redraws, GC pressure, boxing, render-blocking resources, layout thrashing, connection reuse, serialization, compression). Report only what this code actually shows.
      7. Cost and risk: per candidate, expected gain, risk of changed behavior, added complexity. Reject marginal or unmeasurable gains. Flag existing optimizations that are premature or counterproductive.
      8. Measurement: baseline first, then profiler or timer on the isolated hotspot with realistic sizes and call counts, complexity check by timing at n and 10n, memory where relevant. Where possible test the candidate on the same inputs and confirm identical output. Unconfirmed gains are dropped or stay SUSPECTED.
    - Final report: candidates ranked by gain divided by risk, each with status, measured or estimated figure and the change in one sentence (no patch code), then what was not reviewed. After the user okays: one optimization per patch task, behavior unchanged; if the gain turns out marginal after patching, recommend #undo.
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


WORKLOG_RECENT = 50  # newest tasks: always shown, every rating, with patch lines
WORKLOG_MID = 25     # older tasks rated 2-3
WORKLOG_LONG = 25    # older tasks rated 3

def _compress_ids(ids):
    """[41, 42, 43, 47] -> '41-43,47'"""
    ids = sorted(set(ids))
    parts = []
    i = 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        parts.append(str(ids[i]) if i == j else f"{ids[i]}-{ids[j]}")
        i = j + 1
    return ','.join(parts)

def build_worklog_lines(complete=False):
    """Worklog for ctags.txt (and -completelog). Returns (note, lines).
    Tiers: the newest WORKLOG_RECENT summaries always (every rating, with
    their patch lines), plus the newest WORKLOG_MID older ones rated 2-3 and
    the newest WORKLOG_LONG older ones rated 3 (patch IDs compressed into a
    range on the LOG line). Reverted summaries are never kept in the older
    tiers. complete=True filters nothing. A patch belongs to the summary that
    claimed it (summary['patch_ids']); applied patches no summary has claimed
    yet are work in progress and come last."""
    patches = {p['id']: p for p in load_patch_history() if p.get('applied', False)}
    summaries = sorted(load_summary_history(), key=lambda s: s['id'])
    claimed = set()
    for s in summaries:
        claimed.update(s.get('patch_ids', []))

    def rating_of(s):
        return s['rating'] if s.get('rating') in (1, 2, 3) else 2

    total = len(summaries)
    if complete:
        recent, older = summaries, []
    else:
        recent = summaries[max(0, total - WORKLOG_RECENT):]
        older = summaries[:max(0, total - WORKLOG_RECENT)]
    live = [s for s in older if not s.get('reverted', False)]
    mid = [s for s in live if rating_of(s) >= 2][-WORKLOG_MID:]
    long_term = [s for s in live if rating_of(s) == 3][-WORKLOG_LONG:]
    detail_ids = {s['id'] for s in recent}
    compact_ids = {s['id'] for s in mid} | {s['id'] for s in long_term}

    lines = []
    for s in summaries:
        sid = s['id']
        compact = sid not in detail_ids
        if compact and sid not in compact_ids:
            continue
        own = [pid for pid in sorted(s.get('patch_ids', [])) if pid in patches]
        pid_tag = ''
        if compact:
            if own:
                pid_tag = f" [P{_compress_ids(own)}]"
        else:
            for pid in own:
                desc = ' '.join(str(patches[pid].get('description', '')).split())
                lines.append(f"{pid} PATCH:{desc}")
        tag = ' [REVERTED]' if s.get('reverted', False) else ''
        about = ' '.join((s.get('about') or '(no about)').split())
        lines.append(f"{sid} LOG R{rating_of(s)}{pid_tag}:{about}{tag}")
    for pid in sorted(patches):
        if pid not in claimed:
            desc = ' '.join(str(patches[pid].get('description', '')).split())
            lines.append(f"{pid} PATCH:{desc}")

    omitted = total - len(detail_ids | compact_ids)
    if complete:
        note = f"Complete, unfiltered: all {total} tasks with all their patches."
    elif omitted > 0:
        note = (f"Filtered view: the latest {WORKLOG_RECENT} tasks (all ratings, with patch lines) "
                f"+ up to {WORKLOG_MID} older tasks rated 2-3 + up to {WORKLOG_LONG} older tasks rated 3. "
                f"{omitted} older task(s) were omitted, so LOG IDs have gaps. "
                f"Everything, unfiltered: promptpack -completelog")
    else:
        note = (f"Nothing omitted yet: all {total} task{'s' if total != 1 else ''} shown. Older tasks get filtered "
                f"by rating once there are more than {WORKLOG_RECENT}.")
    return note, lines

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
Use 'promptpack -r path' whenever you need to read a file's full content.

## Project Structure
""")

        write_project_tree(out, marked_files)
        out.write("\n## Ctags Structure\n")
        CTAGS_MAX_BYTES = 2 * 1024 * 1024  # skip huge data files, ctags is for code symbols
        CTAGS_TIMEOUT = 10

        for file_path in marked_files:
            try:
                rel_path = _rel_path(file_path)

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
                out.write(f"\n### {_rel_path(file_path)}\n")
                out.write(f"# Error running ctags: {e}\n")

        worklog_note, worklog_lines = build_worklog_lines()
        if worklog_lines:
            out.write("\n# WORKLOG\n")
            out.write("Chronological. `ID LOG R<n>:` = task summary with impact rating 1-3 (3 = most important; full text: promptpack -log ID ...), `ID PATCH:` = patch (full code: promptpack -ph ID ...). Patches come before the LOG that closes their task; older LOGs list their patch IDs as `[P41-43]` instead of separate lines (a range means every ID in it). LOG and PATCH IDs are separate number series.\n")
            out.write(worklog_note + "\n")
            out.write("\n".join(worklog_lines) + "\n")

    return True


def get_all_py_files(root):
    """Bygg dict: modulnamn -> TreeNode för alla .py-filer i trädet"""
    module_map = {}

    def traverse(node):
        if not node.is_dir:
            if node.path.suffix == '.py':
                try:
                    rel = _rel_path(node.path)
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

# ---------------------------------------------------------------------------
# MCP server (promptpack --mcp): an HTTP server on 127.0.0.1 that AI clients
# reach through the MCP tools protocol. It exposes one tool, `promptpack`,
# which runs promptpack's own CLI in a child process, so every command behaves
# exactly as it does in the terminal. Output is logged in the terminal.
# ---------------------------------------------------------------------------

MCP_CONFIG_FILE = Path(__file__).resolve().parent / 'mcp.json'
MCP_DEFAULT_PORT = 47829
MCP_CMD_TIMEOUT = 300   # seconds allowed for one promptpack command
MCP_LOG_MAX_BYTES = 2 * 1024       # output the terminal shows per command, the AI always gets all of it
MCP_PROTOCOL_VERSIONS = ['2025-06-18', '2025-03-26', '2024-11-05']
MCP_NOTICE = (
    "You are connected to promptpack through MCP. Do not ask the user to run promptpack "
    "commands: call the tool `promptpack` with `commands`, a list where each item has "
    "`args` (the promptpack arguments as strings, e.g. [\"-r\", \"main.py\"]) and, for "
    "commands that read stdin (-p, -f, --summary), `stdin` (the text you would otherwise pipe in). "
    "Several commands can go in one call and run in order. -c is not needed: results come back "
    "in the tool result. The project spec below is the user's standing workflow; follow it, "
    "except that wherever it tells you to ask the user to run commands, to paste output back or to "
    "end with -c, you call the tool yourself instead. Start working with the tool right away "
    "(for example -r on the files you need) instead of asking the user to do it."
)


def load_mcp_config(exit_on_error=True):
    """Read mcp.json (port and access token) next to promptpack.py. Created with
    defaults and a random token on first use. Other keys are kept as they are,
    so later settings (OpenRouter) can live in the same file."""
    config = {}
    if MCP_CONFIG_FILE.exists():
        try:
            with open(MCP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError("top-level JSON value is not an object")
        except (OSError, ValueError) as e:
            if not exit_on_error:
                raise
            print(f"❌ {MCP_CONFIG_FILE.name} is unreadable: {e}")
            print("   Repair the file, or delete it to get a new port and token.")
            sys.exit(1)
    changed = False
    if not isinstance(config.get('port'), int):
        config['port'] = MCP_DEFAULT_PORT
        changed = True
    if not isinstance(config.get('token'), str) or not config['token']:
        config['token'] = secrets.token_urlsafe(24)
        changed = True
    if changed:
        _atomic_write_text(MCP_CONFIG_FILE, json.dumps(config, indent=2, ensure_ascii=False) + '\n')
    return config


def build_mcp_instructions(root):
    """Text sent to the AI when it connects: MCP_NOTICE plus ctags.txt, the same
    file F1 creates. It is regenerated now so the structure is current."""
    ctags_text = ''
    marked_files = get_marked_files(root) if root is not None else []
    if marked_files:
        try:
            if create_ctags_file(root) and Path('ctags.txt').exists():
                ctags_text = Path('ctags.txt').read_text(encoding='utf-8')
        except HistoryCorruptError as e:
            ctags_text = f"(ctags.txt not created: {e})"
    # ctags.txt opens with "# ABOUT THIS FILE", written for a chat where the user runs the
    # commands. MCP_NOTICE replaces that part, so everything from "# LANGUAGE" on is sent.
    cut = ctags_text.find('# LANGUAGE')
    if cut >= 0:
        ctags_text = ctags_text[cut:]
    else:
        # Empty folder, nothing marked or ctags.txt failed: the full spec is still sent,
        # only the file list and the worklog are missing.
        core = PROMPTPACK_CORE_INSTRUCTIONS
        note = ctags_text or ("(The project is empty or no files are marked, so there is no file list "
                              "or worklog yet. Create new files with -f. Files marked with Space in "
                              "promptpack are included after a restart of promptpack --mcp.)")
        ctags_text = core[max(0, core.find('# LANGUAGE')):] + "\n" + note
    return MCP_NOTICE + "\n\n" + ctags_text


class _MCPHandler(BaseHTTPRequestHandler):
    """HTTP side of the MCP server: one JSON-RPC message per POST to /mcp."""
    server_version = 'promptpack-mcp'

    def log_message(self, format, *args):
        pass    # the server prints its own log, see _MCPServer.say

    def _reply(self, code, payload=None):
        body = b'' if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        self._reply(405, {'error': 'use POST /mcp'})

    def do_POST(self):
        srv = self.server
        if self.path.split('?', 1)[0] != '/mcp':
            self._reply(404, {'error': 'not found'})
            return
        origin = self.headers.get('Origin', '')
        if origin and not origin.startswith(('http://127.0.0.1', 'http://localhost')):
            srv.say(f"✖ rejected request from origin {origin}")
            self._reply(403, {'error': 'origin not allowed'})
            return
        given = self.headers.get('Authorization', '').encode('utf-8')
        if not hmac.compare_digest(given, f"Bearer {srv.token}".encode('utf-8')):
            srv.say("✖ rejected request with a missing or wrong token")
            self._reply(401, {'error': 'unauthorized'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            msg = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            self._reply(400, {'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32700, 'message': 'Parse error'}})
            return
        if not isinstance(msg, dict):
            self._reply(400, {'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32600, 'message': 'Expected one JSON-RPC message'}})
            return
        response = srv.handle_rpc(msg)
        if response is None:
            self._reply(202)
        else:
            self._reply(200, response)


class _MCPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token, instructions):
        super().__init__(address, _MCPHandler)
        self.token = token
        self.instructions = instructions
        # Tool calls run one at a time: they write patch.json and summary.json.
        self.lock = threading.Lock()

    def say(self, text):
        mcp_log(text)

    @staticmethod
    def _rpc_error(mid, code, message):
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}

    def handle_rpc(self, msg):
        method = msg.get('method', '')
        mid = msg.get('id')
        if mid is None:
            self.say(f"· notification {method}")
            return None
        params = msg.get('params') or {}
        try:
            if method == 'initialize':
                result = self._initialize(params)
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': [self._tool_definition()]}
            elif method == 'tools/call':
                result = self._call_tool(params)
            else:
                return self._rpc_error(mid, -32601, f"Method not found: {method}")
        except Exception as e:
            self.say(f"✖ {method} failed: {e}")
            return self._rpc_error(mid, -32603, str(e))
        return {'jsonrpc': '2.0', 'id': mid, 'result': result}

    def _initialize(self, params):
        requested = params.get('protocolVersion')
        version = requested if requested in MCP_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSIONS[0]
        self.say(f"→ client connected (protocol {version})")
        return {
            'protocolVersion': version,
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'promptpack', 'version': '1.0'},
            'instructions': self.instructions,
        }

    @staticmethod
    def _tool_definition():
        return {
            'name': 'promptpack',
            'description': ('Run promptpack commands in the project folder. Several commands can go in one call; '
                            'they run in order and every result is returned. Same arguments as the terminal CLI.'),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'commands': {
                        'type': 'array',
                        'minItems': 1,
                        'items': {
                            'type': 'object',
                            'properties': {
                                'args': {'type': 'array', 'items': {'type': 'string'},
                                         'description': 'promptpack arguments, e.g. ["-r", "main.py"]'},
                                'stdin': {'type': 'string',
                                          'description': 'text for commands that read stdin (-p, -f, --summary)'},
                            },
                            'required': ['args'],
                        },
                    },
                },
                'required': ['commands'],
            },
        }

    def _call_tool(self, params):
        if params.get('name') != 'promptpack':
            raise ValueError(f"unknown tool: {params.get('name')}")
        commands = (params.get('arguments') or {}).get('commands')
        if not isinstance(commands, list) or not commands:
            raise ValueError("'commands' must be a non-empty list")
        with self.lock:
            texts = [self._run_command(item) for item in commands]
        return {'content': [{'type': 'text', 'text': '\n\n'.join(texts)}]}

    def _run_command(self, item):
        return run_promptpack_command(item, self.say)


OPENROUTER_API = 'https://openrouter.ai/api/v1'
OPENROUTER_REQUEST_TIMEOUT = 600   # seconds to wait for one model answer
OPENROUTER_MODELS_TIMEOUT = 30     # seconds to wait for the model list
OPENROUTER_MAX_STEPS = 40          # tool-call rounds allowed for one user message
CONTEXT_WARN_FRACTION = 0.80   # trim old tool results once the conversation reaches this share of the window
CONTEXT_TRIM_FRACTION = 0.60   # trimming stops at this share of the window
MODELS_MAX_AGE = 24 * 3600     # re-fetch the OpenRouter model list when older than this (seconds)
MCP_SECURITY_NOTE = ("⚠️  The AI can run shell commands in this project (-e). The -e blacklist is a minimal "
                     "guard, not a security boundary: only connect an AI you trust.")


def save_mcp_config(config):
    """Write mcp.json (atomic). It can hold an API key, so where the system supports it
    the file is made readable by its owner only."""
    _atomic_write_text(MCP_CONFIG_FILE, json.dumps(config, indent=2, ensure_ascii=False) + '\n')
    try:
        os.chmod(MCP_CONFIG_FILE, 0o600)
    except OSError:
        pass


def mcp_ready(config):
    """(ok, problem): may promptpack --mcp start with this config? A mode must be
    chosen (F6) and its requirements met."""
    mode = config.get('mode')
    if mode == 'claude_desktop':
        return True, ''
    if mode == 'openrouter':
        if not config.get('openrouter_key'):
            return False, "OpenRouter needs an API key. Run promptpack, press F6, choose OpenRouter and enter the key."
        if not config.get('openrouter_model'):
            return False, "OpenRouter needs a model. Run promptpack, press F6, choose OpenRouter and pick a model."
        return True, ''
    return False, ("No MCP mode is chosen. Run promptpack, press F6, choose Claude Desktop or OpenRouter, "
                   "then start promptpack --mcp again.")


_ANSI = {'cyan': '\x1b[36m', 'green': '\x1b[32m', 'yellow': '\x1b[33m',
         'red': '\x1b[31m', 'dim': '\x1b[2m', 'reset': '\x1b[0m'}
_CURSES_PAIR = {'cyan': 4, 'green': 5, 'yellow': 6, 'red': 7}
SPINNER_FRAMES = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
SPINNER_INTERVAL = 0.08   # seconds per frame

def _log_kind(text):
    """Which colour a log line gets, from its leading symbol. None = plain."""
    body = re.sub(r'^\[\d{2}:\d{2}:\d{2}\] ', '', text)
    if body.startswith(('✖', '❌')):
        return 'red'
    if body.startswith('→'):
        return 'cyan'
    if body.startswith('←'):
        return 'green'
    if body.startswith('⚙'):
        return 'yellow'
    if body.startswith(('·', '⏳')):
        return 'dim'
    return None

def mcp_log(text):
    stamp = datetime.now().strftime('%H:%M:%S')
    kind = _log_kind(text)
    if kind and sys.stdout.isatty():
        # ANSI colour only for a real terminal; the curses chat view colours by attribute instead
        colour = _ANSI['dim'] if kind == 'dim' else _ANSI[kind]
        print(f"{_ANSI['dim']}[{stamp}]{_ANSI['reset']} {colour}{text}{_ANSI['reset']}", flush=True)
    else:
        print(f"[{stamp}] {text}", flush=True)


def run_promptpack_command(item, say):
    """Run one {"args": [...], "stdin": "..."} item as a promptpack child process, exactly as
    the terminal CLI would, and return the result as text. say(text) logs one line."""
    args = item.get('args') if isinstance(item, dict) else None
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        say(f"✖ invalid command rejected: {str(item)[:160]}")
        return '✖ invalid command: expected {"args": [strings], "stdin": string}'
    shown = 'promptpack ' + ' '.join(args)
    if args in (['-c'], ['--clear']):
        say(f"→ {shown} (skipped: not needed in MCP mode)")
        return f"$ {shown}\n(skipped: -c is not needed, results are returned directly)"
    if '--mcp' in args or '--mcp-bridge' in args:
        say(f"✖ refused: {shown}")
        return f"$ {shown}\n✖ refused: the MCP server cannot be started through the tool"
    say(f"→ {shown}")
    fd, buffer_path = tempfile.mkstemp(prefix='promptpack_mcp_', suffix='.txt')
    os.close(fd)
    env = dict(os.environ, PROMPTPACK_MCP_BUFFER=buffer_path, PYTHONIOENCODING='utf-8')
    buffered, console, code = '', '', None
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), *args],
            input=str(item.get('stdin') or ''), capture_output=True, text=True,
            encoding='utf-8', errors='replace', env=env, timeout=MCP_CMD_TIMEOUT)
        console, code = proc.stdout + proc.stderr, proc.returncode
        with open(buffer_path, 'r', encoding='utf-8', errors='replace') as f:
            buffered = f.read()
    except subprocess.TimeoutExpired:
        console = f"✖ timed out after {MCP_CMD_TIMEOUT} seconds"
        code = -1
    finally:
        try:
            os.unlink(buffer_path)
        except OSError:
            pass
    # The command's messages are printed and also buffered. A console line is shown
    # only when its text (without the leading emoji) is not already in the buffer.
    extra = [line for line in console.splitlines()
             if line.strip() and re.sub(r'^[^A-Za-z0-9]+', '', line.strip()) not in buffered]
    body = '\n'.join(part for part in (buffered.strip('\n'), '\n'.join(extra).strip('\n')) if part)
    say(f"← exit {code}")
    if body:
        print(_clip(body, MCP_LOG_MAX_BYTES, 'terminal'), flush=True)
    return f"$ {shown}\n{body}\n[exit {code}]"


def _openrouter_request(path, key=None, payload=None, timeout=OPENROUTER_REQUEST_TIMEOUT):
    """GET (no payload) or POST JSON to OpenRouter and return the decoded JSON.
    Raises RuntimeError with a readable message on any failure."""
    headers = {'Content-Type': 'application/json', 'X-Title': 'PromptPack'}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(OPENROUTER_API + path, data=data, headers=headers,
                                 method='POST' if payload is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            err = json.loads(raw.decode('utf-8', 'replace')).get('error')
            detail = (err.get('message') if isinstance(err, dict) else str(err)) or str(err)
        except (ValueError, AttributeError):
            detail = raw[:200].decode('utf-8', 'replace')
        raise RuntimeError(f"OpenRouter answered HTTP {e.code}: {detail}")
    except OSError as e:
        raise RuntimeError(f"cannot reach OpenRouter: {e}")
    try:
        return json.loads(raw.decode('utf-8'))
    except ValueError:
        raise RuntimeError("OpenRouter sent an answer that is not JSON")


def _price_per_million(value):
    """OpenRouter prices are USD per token, as text. Returns USD per million tokens,
    or None when unknown or variable (negative, as for the auto router)."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price * 1000000 if price >= 0 else None


def _fmt_price(price):
    if price is None:
        return 'var'
    if price == 0:
        return 'free'
    return f"${price:.2f}" if price >= 0.01 else f"${price:.4f}"


def _fmt_context(tokens):
    if not tokens:
        return '?'
    return f"{tokens // 1000}K" if tokens < 1000000 else f"{tokens / 1000000:.1f}M"


def fetch_openrouter_models():
    """Download the model list and keep the models that can call tools (free and paid).
    Sorted free first, then by name. Raises RuntimeError if the list cannot be fetched."""
    data = _openrouter_request('/models', timeout=OPENROUTER_MODELS_TIMEOUT)
    if not isinstance(data, dict):
        raise RuntimeError("unexpected model list from OpenRouter")
    models = []
    for m in data.get('data') or []:
        if not isinstance(m, dict) or not m.get('id'):
            continue
        if 'tools' not in (m.get('supported_parameters') or []):
            continue
        pricing = m.get('pricing') or {}
        price_in = _price_per_million(pricing.get('prompt'))
        price_out = _price_per_million(pricing.get('completion'))
        models.append({
            'id': m['id'],
            'name': m.get('name') or m['id'],
            'description': ' '.join(str(m.get('description') or '').split())[:400],
            'context': m.get('context_length') or 0,
            'prompt': price_in,
            'completion': price_out,
            'free': str(m['id']).endswith(':free') or (price_in == 0 and price_out == 0),
        })
    models.sort(key=lambda m: (not m['free'], m['name'].lower()))
    return models


def _fmt_count(n):
    """1234 -> 1.2K, 2500000 -> 2.50M, small numbers as they are."""
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}K" if n < 1000000 else f"{n / 1000000:.2f}M"


def _join_row(left, right, width):
    """One header row: left text, right text flush to the right edge. When the two do not
    fit, the left text is cut so the right text still shows."""
    if len(left) + len(right) <= width:
        return left.ljust(width - len(right)) + right
    return left[:max(0, width - len(right) - 1)] + ' ' + right


class _MCPHeader:
    """Pinned two-row header for promptpack --mcp, drawn with ANSI escape codes. The rows
    below it form a scroll region, so the log and the chat scroll under the header without
    touching it. Does nothing when stdout is not a terminal. In OpenRouter mode row 2 shows
    the token usage and cost of the session, taken from the usage OpenRouter sends with every
    answer (estimated from the model's prices when an answer has no cost). Claude Desktop does
    not report usage to an MCP server, so there row 2 holds a note instead."""

    def __init__(self, title, note=''):
        self.title = title
        self.note = note
        self.prices = None      # (USD per million tokens in, out) of the model, or None
        self.context = 0        # context window of the model, in tokens
        self.free = False
        self.requests = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.last_in = 0        # prompt size of the latest request = how full the context is
        self.cost = 0.0
        self.estimated = False  # part of the cost is calculated from prices, not reported
        self.cost_unknown = False
        self.active = False
        self._size = None
        self._lock = threading.Lock()

    def set_model(self, info):
        """info: a model entry from the cached OpenRouter list (or None)."""
        if not info:
            return
        price_in, price_out = info.get('prompt'), info.get('completion')
        if price_in is not None and price_out is not None:
            self.prices = (price_in, price_out)
        self.context = info.get('context') or 0
        self.free = bool(info.get('free'))

    def _lines(self, width):
        line1 = _join_row(f" PromptPack MCP | {self.title}", f"{Path.cwd()} ", width)
        if self.note:
            return line1, _join_row(" " + self.note, "Ctrl+C: Stop ", width)
        if self.free:
            cost = 'free ($0)'
        else:
            cost = f"{'~' if self.estimated else ''}${self.cost:.4f}{'+' if self.cost_unknown else ''}"
        ctx = _fmt_count(self.last_in) + (f"/{_fmt_context(self.context)}" if self.context else '')
        # "billed in" is the whole context sent with each request, so it grows faster than the chat
        line2 = (f" Billed in: {_fmt_count(self.tokens_in)} | Out: {_fmt_count(self.tokens_out)} | "
                 f"Context now: {ctx} | Cost: {cost} | Requests: {self.requests}")
        return line1, _join_row(line2, "Ctrl+C: Stop ", width)

    def start(self):
        if not sys.stdout.isatty() or os.environ.get('TERM') == 'dumb':
            return
        if shutil.get_terminal_size((80, 24)).lines < 6:
            return
        if sys.platform == 'win32':
            os.system('')   # switches the Windows console to ANSI mode
        self.active = True
        self._size = None
        sys.stdout.write("\x1b[2J\x1b[H")
        self.draw()
        sys.stdout.write("\x1b[3;1H")   # first line of the scrolling area
        sys.stdout.flush()

    def draw(self):
        if not self.active:
            return
        with self._lock:
            size = shutil.get_terminal_size((80, 24))
            width, height = size.columns, size.lines
            if height < 6:
                return
            line1, line2 = self._lines(width)
            out = ["\x1b7"]                      # save the cursor
            if self._size != (width, height):    # first draw or the window was resized
                out.append(f"\x1b[3;{height}r")
                self._size = (width, height)
            out.append(f"\x1b[1;1H\x1b[7m{line1.ljust(width)[:width]}\x1b[0m")
            out.append(f"\x1b[2;1H\x1b[7m{line2.ljust(width)[:width]}\x1b[0m")
            out.append("\x1b8")                  # restore the cursor
            sys.stdout.write(''.join(out))
            sys.stdout.flush()

    def add_usage(self, usage):
        """Count one OpenRouter answer. usage is the 'usage' object of the response."""
        if not isinstance(usage, dict):
            usage = {}

        def count(name):
            value = usage.get(name)
            return int(value) if isinstance(value, (int, float)) else 0

        tokens_in, tokens_out = count('prompt_tokens'), count('completion_tokens')
        reported = usage.get('cost')
        with self._lock:
            self.requests += 1
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.last_in = tokens_in
            if isinstance(reported, (int, float)):
                self.cost += float(reported)
            elif self.prices:
                self.cost += (tokens_in * self.prices[0] + tokens_out * self.prices[1]) / 1000000
                self.estimated = True
            else:
                self.cost_unknown = True
        self.draw()

    def stop(self):
        if not self.active:
            return
        self.active = False
        height = shutil.get_terminal_size((80, 24)).lines
        sys.stdout.write(f"\x1b[r\x1b[{height};1H\n")   # remove the scroll region, cursor to the bottom
        sys.stdout.flush()


def _make_mcp_header(config):
    """The header that fits the chosen MCP mode."""
    if config.get('mode') == 'openrouter':
        model = config.get('openrouter_model')
        header = _MCPHeader(f"OpenRouter | {model}")
        header.set_model(next((m for m in config.get('openrouter_models') or [] if m.get('id') == model), None))
        return header
    return _MCPHeader("Claude Desktop", note="Claude Desktop does not report token usage or cost to MCP servers: see the usage in Claude Desktop itself.")


def _lock_terminal_input():
    """Read-only terminal: typed characters are not echoed. Returns a function that
    restores the terminal and throws away anything typed meanwhile. Does nothing
    where termios is missing (Windows) or stdin is not a terminal."""
    try:
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
    except Exception:
        return lambda: None

    def restore():
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
    return restore


def _display_width(text):
    """Columns a string takes in a terminal: wide characters (CJK, most emoji) count 2,
    combining marks and zero-width joiners 0."""
    import unicodedata
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in '\u200b\u200d\ufe0f':
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return width


def _pad_to(text, width, align='l'):
    """Pad text with spaces to width columns; align is l, r or c."""
    gap = max(0, width - _display_width(text))
    if align == 'r':
        return ' ' * gap + text
    if align == 'c':
        return ' ' * (gap // 2) + text + ' ' * (gap - gap // 2)
    return text + ' ' * gap


def _wrap_cell(text, width):
    """Word-wrap one table cell to width columns. Returns a list of lines, at least one."""
    out = []
    for part in text.split('\n'):
        line = ''
        for word in part.split():
            while _display_width(word) > width:   # a word wider than the column is cut
                used = cut = 0
                for ch in word:
                    w = _display_width(ch)
                    if used + w > width and cut:
                        break
                    used += w
                    cut += 1
                if line:
                    out.append(line)
                    line = ''
                out.append(word[:cut])
                word = word[cut:]
            if not word:
                continue
            if not line:
                line = word
            elif _display_width(line) + 1 + _display_width(word) <= width:
                line += ' ' + word
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or ['']


_TABLE_SEP = re.compile(r'^:?-+:?$')


def _split_table_row(line):
    """Cells of a markdown table row like | a | b |, or None when the line is not one."""
    s = line.strip()
    if len(s) < 2 or not (s.startswith('|') and s.endswith('|')):
        return None
    cells = re.split(r'(?<!\\)\|', s)[1:-1]
    return [c.strip().replace('\\|', '|') for c in cells]


def _clean_cell(text):
    """Inline markdown that cannot be shown in a terminal cell is dropped."""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    return re.sub(r'\*\*(.+?)\*\*', r'\1', text)


def _render_table(header, aligns, body, width):
    """Draw a markdown table as an aligned box that fits in width columns. Returns a list of
    (text, is_header_row), or None when it cannot fit even with the narrowest columns."""
    ncols = len(header)
    aligns = (aligns + ['l'] * ncols)[:ncols]
    rows = [[_clean_cell(c) for c in (r + [''] * ncols)[:ncols]] for r in [header] + body]
    widths = [max(1, max(_display_width(line) for row in rows for line in row[c].split('\n')))
              for c in range(ncols)]
    limits = [min(w, 4) for w in widths]
    overhead = 3 * ncols + 1
    while sum(widths) + overhead > width:
        shrinkable = [c for c in range(ncols) if widths[c] > limits[c]]
        if not shrinkable:
            return None
        widest = max(shrinkable, key=lambda c: widths[c])
        widths[widest] -= 1
    wrapped = [[_wrap_cell(cell, widths[c]) for c, cell in enumerate(row)] for row in rows]
    tall = any(len(cell) > 1 for row in wrapped for cell in row)

    def border(left, mid, right):
        return left + mid.join('─' * (w + 2) for w in widths) + right

    out = [(border('┌', '┬', '┐'), False)]
    for r, cells in enumerate(wrapped):
        for k in range(max(len(cell) for cell in cells)):
            parts = [' ' + _pad_to(cell[k] if k < len(cell) else '', widths[c], aligns[c]) + ' '
                     for c, cell in enumerate(cells)]
            out.append(('│' + '│'.join(parts) + '│', r == 0))
        if r == 0 or (tall and r < len(wrapped) - 1):
            out.append((border('├', '┼', '┤'), False))
    out.append((border('└', '┴', '┘'), False))
    return out


def _wrap_lines(lines, width):
    """Turn logical lines [(text, attr)] into display rows [(text, attr)] of at most width
    columns. A markdown table (header row, |---| row, body rows) is drawn as an aligned box."""
    rows = []
    i = 0
    while i < len(lines):
        text, attr = lines[i]
        if _split_table_row(text) is not None:
            j = i
            block = []
            while j < len(lines) and _split_table_row(lines[j][0]) is not None:
                block.append(_split_table_row(lines[j][0]))
                j += 1
            if len(block) >= 2 and all(_TABLE_SEP.match(c) for c in block[1]):
                aligns = ['c' if c.startswith(':') and c.endswith(':') else 'r' if c.endswith(':') else 'l'
                          for c in block[1]]
                drawn = _render_table(block[0], aligns, block[2:], width)
                if drawn is not None:
                    for line, bold in drawn:
                        rows.append((line, curses.A_BOLD if bold else attr))
                    i = j
                    continue
        if not text:
            rows.append(('', attr))
        else:
            for k in range(0, len(text), width):
                rows.append((text[k:k + width], attr))
        i += 1
    return rows


class _ChatView:
    """Full-screen curses view for the OpenRouter chat: the two-row header on top, the chat and
    the log in a scrollable area, one input line at the bottom. While it runs, everything
    written to stdout and stderr (print, mcp_log, command output) goes into the scroll buffer
    instead of the terminal. The model works in a background thread, so scrolling stays
    possible while the AI is busy."""

    MAX_LINES = 20000
    encoding = 'utf-8'

    def __init__(self, header):
        self.header = header
        self.spin = 0           # index into SPINNER_FRAMES while the AI works
        self.lines = []          # logical lines: (text, attr)
        self.partial = ''        # written text that has no newline yet
        self.lock = threading.Lock()
        self.busy = False
        self.offset = 0          # wrapped rows scrolled up from the bottom (0 = follow)
        self.text = ''           # the input line
        self.pos = 0             # cursor position in the input line
        self._rows = []          # wrapped rows of lines[:_wrapped]
        self._wrapped = 0
        self._width = 0
        self._trimmed = False

    # --- file-like side: used as sys.stdout and sys.stderr while the view runs ---
    def isatty(self):
        return False

    def flush(self):
        pass

    def write(self, data):
        if not data:
            return 0
        with self.lock:
            parts = (self.partial + data.replace('\r\n', '\n').replace('\r', '\n')).split('\n')
            self.partial = parts.pop()
            for part in parts:
                self._add(part)
        return len(data)

    def _add(self, text):
        attr = curses.A_NORMAL
        body = re.sub(r'^\[\d{2}:\d{2}:\d{2}\] ', '', text)
        kind = _log_kind(text)
        if text.startswith('you>') or body.startswith('ai>'):
            attr = curses.A_BOLD
        elif kind in _CURSES_PAIR:
            attr = curses.color_pair(_CURSES_PAIR[kind])
        elif kind == 'dim' or text.startswith('['):
            attr = curses.A_DIM
        self.lines.append((text.expandtabs(4), attr))
        if len(self.lines) > self.MAX_LINES:
            del self.lines[:self.MAX_LINES // 10]
            self._trimmed = True

    # --- drawing ---
    def _wrap(self, width):
        """Wrap new lines into rows of at most width characters (cached)."""
        with self.lock:
            if width != self._width or self._trimmed:
                self._rows, self._wrapped, self._width, self._trimmed = [], 0, width, False
            fresh = self._wrapped == 0
            before = len(self._rows)
            self._rows.extend(_wrap_lines(self.lines[self._wrapped:], width))
            self._wrapped = len(self.lines)
            if self.offset and not fresh:
                self.offset += len(self._rows) - before   # keep the view still while scrolled up

    def _draw(self, stdscr):
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        if height < 6 or width < 24:
            _put(stdscr, 0, 0, "Window too small")
            stdscr.refresh()
            return
        line1, line2 = self.header._lines(width)
        _put(stdscr, 0, 0, line1.ljust(width - 1)[:width - 1], curses.A_REVERSE)
        _put(stdscr, 1, 0, line2.ljust(width - 1)[:width - 1], curses.A_REVERSE)
        body_h = height - 4
        self._wrap(width - 1)
        total = len(self._rows)
        self.offset = max(0, min(self.offset, max(0, total - body_h)))
        end = total - self.offset
        for i, (text, attr) in enumerate(self._rows[max(0, end - body_h):end]):
            _put(stdscr, 2 + i, 0, text, attr)
        if self.offset:
            status = f" ↑ scrolled up, {self.offset} rows below | End: back to the bottom"
        else:
            status = " PgUp/PgDn, Up/Down or the mouse wheel scroll | Home: top | End: bottom"
        if self.busy:
            frame = SPINNER_FRAMES[self.spin % len(SPINNER_FRAMES)]
            status = f" {frame} the AI is working |" + status
        _put(stdscr, height - 2, 0, status, curses.A_DIM)
        label = "you> "
        room = max(1, width - len(label) - 2)
        shown = self.text.replace('\n', '⏎')
        first = max(0, self.pos - room + 1)
        _put(stdscr, height - 1, 0, label + shown[first:first + room], curses.A_BOLD)
        try:
            stdscr.move(height - 1, min(width - 2, len(label) + self.pos - first))
        except curses.error:
            pass
        stdscr.refresh()

    # --- main loop ---
    def _work(self, on_submit, text):
        try:
            on_submit(text)
        except Exception as e:
            print(f"❌ unexpected error: {e}", flush=True)
        finally:
            self.busy = False

    def run(self, stdscr, on_submit):
        curses.curs_set(1)
        stdscr.keypad(True)
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            for pair, colour in ((4, curses.COLOR_CYAN), (5, curses.COLOR_GREEN),
                                 (6, curses.COLOR_YELLOW), (7, curses.COLOR_RED)):
                curses.init_pair(pair, colour, bg)
        stdscr.timeout(100)      # wake up often: the worker thread adds lines meanwhile
        while True:
            self._draw(stdscr)
            if self.busy:
                self.spin += 1
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            page = max(1, stdscr.getmaxyx()[0] - 5)
            if ch == curses.KEY_PPAGE:
                self.offset += page
            elif ch == curses.KEY_NPAGE:
                self.offset -= page
            elif ch == curses.KEY_UP:
                self.offset += 3
            elif ch == curses.KEY_DOWN:
                self.offset -= 3
            elif ch == curses.KEY_HOME:
                self.offset = 10 ** 9
            elif ch == curses.KEY_END:
                self.offset = 0
            elif ch == curses.KEY_LEFT:
                self.pos = max(0, self.pos - 1)
            elif ch == curses.KEY_RIGHT:
                self.pos = min(len(self.text), self.pos + 1)
            elif ch == '\x01':
                self.pos = 0
            elif ch == '\x05':
                self.pos = len(self.text)
            elif ch == '\x15':
                self.text, self.pos = '', 0
            elif ch == '\x04' and not self.text:
                return
            elif ch in ('\x7f', '\b') or ch == curses.KEY_BACKSPACE:
                if self.pos:
                    self.text = self.text[:self.pos - 1] + self.text[self.pos:]
                    self.pos -= 1
            elif ch == curses.KEY_DC:
                self.text = self.text[:self.pos] + self.text[self.pos + 1:]
            elif ch in ('\n', '\r') or ch == curses.KEY_ENTER:
                stdscr.timeout(0)
                try:
                    pending = stdscr.get_wch()
                except curses.error:
                    pending = None
                stdscr.timeout(100)
                if pending is not None:
                    # more input follows at once: pasted text, so keep the line break
                    curses.unget_wch(pending)
                    self.text = self.text[:self.pos] + '\n' + self.text[self.pos:]
                    self.pos += 1
                    continue
                text = self.text.strip()
                if not text:
                    continue
                if self.busy:
                    print("⏳ The AI is still working: send the next message when it has answered.", flush=True)
                    continue
                self.text, self.pos, self.offset = '', 0, 0
                print(f"you> {text}", flush=True)
                self.busy = True
                threading.Thread(target=self._work, args=(on_submit, text), daemon=True).start()
            elif isinstance(ch, str) and ch.isprintable():
                self.text = self.text[:self.pos] + ch + self.text[self.pos:]
                self.pos += 1

    def start(self, on_submit, intro):
        """Run the view until Ctrl+C or Ctrl+D. intro() prints the opening lines into it."""
        saved = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = self
        try:
            intro()
            curses.wrapper(self.run, on_submit)
        finally:
            sys.stdout, sys.stderr = saved


def _clip(text, limit, what='output'):
    """Cut text to limit bytes for display only. The footer gives the full size."""
    raw = text.encode('utf-8')
    if len(raw) <= limit:
        return text
    shown = raw[:limit].decode('utf-8', 'ignore').rstrip('\n')
    return (f"{shown}\n\n--- {what}: showing {limit / 1024:.1f} of {len(raw) / 1024:.1f} kB. "
            f"The AI received all of it. ---")

def _history_tokens(messages):
    """Tokens the whole conversation takes, estimated the same way as the other counts."""
    return calculate_tokens(json.dumps(messages, ensure_ascii=False))

def _trim_history(messages, limit):
    """Shorten the conversation in place until it is under CONTEXT_TRIM_FRACTION of the window.
    The oldest tool results are replaced by a one-line note with their size. The system prompt
    and the user and assistant text stay. Returns how many results were replaced."""
    target = int(limit * CONTEXT_TRIM_FRACTION)
    total = _history_tokens(messages)
    trimmed = 0
    # the tool results of the latest round are what the model is working on now: never trimmed
    latest = max((i for i, m in enumerate(messages) if m.get('role') == 'assistant'), default=len(messages))
    for msg in messages[:latest]:
        if total <= target:
            break
        if msg.get('role') != 'tool' or str(msg.get('content', '')).startswith('[trimmed'):
            continue
        before = calculate_tokens(json.dumps(msg, ensure_ascii=False))
        size = len(str(msg.get('content', '')).encode('utf-8'))
        msg['content'] = (f"[trimmed to save context: this tool result was {size / 1024:.1f} kB. "
                          f"Run the command again if you need it.]")
        total -= before - calculate_tokens(json.dumps(msg, ensure_ascii=False))
        trimmed += 1
    return trimmed

def _models_age(config):
    """Seconds since the OpenRouter model list was fetched, or None when that is unknown."""
    try:
        stamp = datetime.fromisoformat(config.get('openrouter_models_time') or '')
    except (TypeError, ValueError):
        return None
    return max(0.0, (datetime.now() - stamp).total_seconds())

def _models_stale(config):
    age = _models_age(config)
    return age is None or age > MODELS_MAX_AGE

def _fmt_age(seconds):
    if seconds is None:
        return 'of unknown age'
    if seconds < 3600:
        return f"{int(seconds // 60)} min old"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h old"
    return f"{int(seconds // 86400)} days old"

def _openrouter_turn(key, model, tools, messages, header=None):
    """Send the conversation, run the tool calls the model asks for and repeat until it
    answers in text. messages is extended in place. Raises RuntimeError on failure."""
    for _ in range(OPENROUTER_MAX_STEPS):
        limit = header.context if header else 0
        if limit:
            used = _history_tokens(messages)
            if used > limit * CONTEXT_WARN_FRACTION:
                trimmed = _trim_history(messages, limit)
                after = _history_tokens(messages)
                print(f"⚠ context {used / limit:.0%} full: {trimmed} old tool result(s) trimmed, "
                      f"now about {after:,} of {limit:,} tokens", flush=True)
                if after > limit * CONTEXT_WARN_FRACTION:
                    print("⚠ still close to the limit: type /new to start a fresh conversation", flush=True)
        mcp_log(f"→ OpenRouter ({model})")
        data = _openrouter_request('/chat/completions', key, {
            'model': model, 'messages': messages, 'tools': tools, 'usage': {'include': True}})
        choices = data.get('choices') if isinstance(data, dict) else None
        if not choices or not isinstance(choices[0], dict):
            err = data.get('error') if isinstance(data, dict) else None
            raise RuntimeError(f"unexpected answer from OpenRouter: {err or str(data)[:200]}")
        message = choices[0].get('message') or {}
        text = message.get('content') or ''
        calls = message.get('tool_calls') or []
        usage = data.get('usage') or {}
        mcp_log(f"← {usage.get('prompt_tokens', '?')} tokens in, {usage.get('completion_tokens', '?')} out")
        if header:
            header.add_usage(usage)
        entry = {'role': 'assistant', 'content': text}
        if calls:
            entry['tool_calls'] = calls
        messages.append(entry)
        if calls:
            mcp_log(f"· model asked for {len(calls)} tool call(s)")
        if text.strip():
            print(f"\nai> {text.strip()}", flush=True)
        if not calls:
            if not text.strip():
                print("\nai> (empty answer)", flush=True)
            return
        for call in calls:
            fn = call.get('function') or {}
            try:
                arguments = json.loads(fn.get('arguments') or '{}')
            except ValueError:
                arguments = None
            if (fn.get('name') != 'promptpack' or not isinstance(arguments, dict)
                    or not isinstance(arguments.get('commands'), list) or not arguments['commands']):
                mcp_log(f"✖ invalid tool call from model: name={fn.get('name')!r}, arguments={str(fn.get('arguments'))[:160]}")
                result = "✖ invalid tool call: use the tool promptpack with a non-empty commands list"
            else:
                result = '\n\n'.join(run_promptpack_command(item, mcp_log) for item in arguments['commands'])
            messages.append({'role': 'tool', 'tool_call_id': call.get('id'), 'content': result})
    raise RuntimeError(f"stopped after {OPENROUTER_MAX_STEPS} tool rounds without a final answer")


def run_openrouter_chat(config, instructions, marked, header=None):
    """promptpack --mcp in OpenRouter mode: this terminal is both the chat and the log.
    The model gets the same tool and the same spec as a Claude Desktop connection; its tool
    calls run locally through run_promptpack_command. In a terminal the chat runs in a
    scrollable curses view (_ChatView); otherwise a plain input() loop is used.
    Ctrl+C (or Ctrl+D) stops."""
    try:
        import readline   # noqa: F401  (line editing and history for input() where available)
    except ImportError:
        pass
    key, model = config['openrouter_key'], config['openrouter_model']
    spec = _MCPServer._tool_definition()
    tools = [{'type': 'function', 'function': {
        'name': spec['name'], 'description': spec['description'], 'parameters': spec['inputSchema']}}]
    start = [{'role': 'system', 'content': instructions}]
    messages = list(start)

    def intro():
        print("🔌 promptpack MCP chat (OpenRouter)")
        print(f"   project: {Path.cwd()}")
        print(f"   model:   {model}")
        print(f"   config:  {MCP_CONFIG_FILE}")
        print(f"   marked files in spec: {marked}")
        print("   Type a message and press Enter. /new starts a new conversation. Ctrl+C stops.")
        print("   PgUp/PgDn, Up/Down or the mouse wheel scroll, Home/End jump to the top or bottom.")
        if _models_stale(config):
            print(f"⚠ The model list is {_fmt_age(_models_age(config))}: press F6, OpenRouter, then r to refresh it.", flush=True)
        print("   Every tool call, patch and result is logged here as it happens.")
        print(f"   {MCP_SECURITY_NOTE}", flush=True)

    def handle(user_text):
        nonlocal messages
        if user_text == '/new':
            messages = list(start)
            print("↺ New conversation started.", flush=True)
            return
        messages.append({'role': 'user', 'content': user_text})
        try:
            _openrouter_turn(key, model, tools, messages, header)
        except RuntimeError as e:
            if messages[-1]['role'] == 'user':
                messages.pop()
                hint = "Your message was not added to the conversation: send it again."
            else:
                hint = "The work done so far is kept: type continue to go on."
            print(f"❌ {e}\n   {hint}", flush=True)

    if sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get('TERM') != 'dumb':
        try:
            _ChatView(header).start(handle, intro)
            print("\n⏹ Chat stopped", flush=True)
            return
        except (EOFError, KeyboardInterrupt):
            print("\n⏹ Chat stopped", flush=True)
            return
        except curses.error as e:
            print(f"⚠ The curses chat view is not available here ({e}): using the plain terminal.", flush=True)
    intro()
    while True:
        try:
            user_text = input("\nyou> ").strip()
            if not user_text:
                continue
            handle(user_text)
        except (EOFError, KeyboardInterrupt):
            print("\n⏹ Chat stopped", flush=True)
            return


def claude_desktop_snippet():
    """JSON for claude_desktop_config.json, built from the paths of this running copy
    of promptpack, so it is correct on any machine and in any folder."""
    entry = {'mcpServers': {'promptpack': {
        'command': sys.executable,
        'args': [os.path.abspath(__file__), '--mcp-bridge'],
    }}}
    return json.dumps(entry, indent=2, ensure_ascii=False)


def claude_desktop_config_hint():
    """Where Claude Desktop keeps its config file on this operating system."""
    if sys.platform == 'win32':
        return r'%APPDATA%\Claude\claude_desktop_config.json'
    if sys.platform == 'darwin':
        return '~/Library/Application Support/Claude/claude_desktop_config.json'
    return 'claude_desktop_config.json in the Claude Desktop config folder (no official Linux build)'


def _put(stdscr, y, x, text, attr=curses.A_NORMAL):
    """addstr that never raises: clipped to the window, ignores a window that is too small."""
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x >= width - 1:
        return
    try:
        stdscr.addstr(y, x, text[:width - x - 1], attr)
    except curses.error:
        pass


def _curses_input(stdscr, row, label, initial=''):
    """One-line text field on the given row. Enter saves, Esc cancels.
    Returns the new text, or None when cancelled."""
    text = initial
    curses.curs_set(1)
    try:
        while True:
            height, width = stdscr.getmaxyx()
            visible = text[-max(1, width - len(label) - 2):]
            try:
                stdscr.move(row, 0)
                stdscr.clrtoeol()
            except curses.error:
                pass
            _put(stdscr, row, 0, label + visible)
            try:
                stdscr.move(row, min(width - 2, len(label) + len(visible)))
            except curses.error:
                pass
            stdscr.refresh()
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            if ch in ('\n', '\r') or ch == curses.KEY_ENTER:
                return text.strip()
            if ch == '\x1b':
                return None
            if ch in ('\x7f', '\b') or ch == curses.KEY_BACKSPACE:
                text = text[:-1]
            elif isinstance(ch, str) and ch.isprintable():
                text += ch
    finally:
        curses.curs_set(0)


def _curses_key_modal(stdscr, current=''):
    """Small centered box for pasting an API key. Enter saves, Esc cancels, Ctrl+U clears.
    Returns the key without any whitespace ('' means remove the key), or None when cancelled."""
    text = current
    curses.curs_set(1)
    try:
        while True:
            height, width = stdscr.getmaxyx()
            box_w = max(20, min(width - 2, 78))
            box_h = 7
            top = max(0, (height - box_h) // 2)
            left = max(0, (width - box_w) // 2)
            inner = box_w - 4
            _put(stdscr, top, left, '┌' + '─' * (box_w - 2) + '┐')
            for r in range(1, box_h - 1):
                _put(stdscr, top + r, left, '│' + ' ' * (box_w - 2) + '│')
            _put(stdscr, top + box_h - 1, left, '└' + '─' * (box_w - 2) + '┘')
            _put(stdscr, top + 1, left + 2, "OpenRouter API key"[:inner], curses.A_BOLD)
            _put(stdscr, top + 2, left + 2, "Paste the key into the field (Ctrl+Shift+V)."[:inner])
            label = "Key: "
            visible = text[-max(1, inner - len(label) - 1):]
            _put(stdscr, top + 4, left + 2, (label + visible).ljust(inner)[:inner], curses.A_REVERSE)
            _put(stdscr, top + 5, left + 2, "Enter: save | Esc: cancel | Ctrl+U: clear"[:inner])
            try:
                stdscr.move(top + 4, min(width - 2, left + 2 + len(label) + len(visible)))
            except curses.error:
                pass
            stdscr.refresh()
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            if ch in ('\n', '\r') or ch == curses.KEY_ENTER:
                return ''.join(text.split())
            if ch == '\x1b':
                return None
            if ch == '\x15':
                text = ''
            elif ch in ('\x7f', '\b') or ch == curses.KEY_BACKSPACE:
                text = text[:-1]
            elif isinstance(ch, str) and ch.isprintable():
                text += ch
    finally:
        curses.curs_set(0)


def _curses_message(stdscr, title, lines):
    """Full-screen notice, any key returns."""
    curses.curs_set(0)
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    _put(stdscr, 0, 0, title.ljust(width - 1), curses.A_REVERSE)
    row = 2
    for line in lines:
        for part in (textwrap.wrap(line, max(10, width - 2)) or ['']):
            if row >= height - 2:
                break
            _put(stdscr, row, 1, part)
            row += 1
    _put(stdscr, height - 1, 0, "Press any key to return...".ljust(width - 1), curses.A_REVERSE)
    stdscr.refresh()
    stdscr.getch()


def _show_claude_desktop_notice(stdscr):
    """Shown when Claude Desktop is activated. Nothing is written to Claude's own config."""
    _curses_message(stdscr, "MCP - Claude Desktop", [
        "Claude Desktop mode is active.",
        "",
        "Nothing is written to Claude's config automatically. Add this under mcpServers in " + claude_desktop_config_hint() + ":",
        "",
        *claude_desktop_snippet().splitlines(),
        "",
        "Restart Claude Desktop. Then run promptpack --mcp in the project folder and keep that terminal open: it is a read-only log, Ctrl+C stops it. The same snippet is printed when promptpack --mcp starts, so you can copy it from there.",
        "",
        MCP_SECURITY_NOTE,
    ])


def show_openrouter_settings(stdscr, config):
    """OpenRouter settings: an API key field (shown in clear text) above the list of models
    that can call tools, free and paid. Every change is saved to mcp.json at once. Leaving
    the page with both key and model set makes OpenRouter the active MCP mode."""
    curses.curs_set(0)
    state = {'filter': 'all', 'status': ''}

    def models_shown():
        models = config.get('openrouter_models') or []
        if state['filter'] == 'free':
            return [m for m in models if m.get('free')]
        if state['filter'] == 'paid':
            return [m for m in models if not m.get('free')]
        return models

    def save():
        try:
            save_mcp_config(config)
            return True
        except OSError as e:
            state['status'] = f"❌ could not save {MCP_CONFIG_FILE.name}: {e}"
            return False

    def reload_models():
        stdscr.clear()
        _put(stdscr, 0, 0, "Fetching the model list from OpenRouter...", curses.A_BOLD)
        stdscr.refresh()
        try:
            config['openrouter_models'] = fetch_openrouter_models()
            config['openrouter_models_time'] = datetime.now().isoformat(timespec='seconds')
            if save():
                state['status'] = f"{len(config['openrouter_models'])} models with tool support loaded"
        except RuntimeError as e:
            state['status'] = f"❌ {e}"

    def settle():
        config['mode'] = 'openrouter'
        missing = []
        if not config.get('openrouter_key'):
            missing.append("an API key (press k)")
        if not config.get('openrouter_model'):
            missing.append("a model (press Space on one)")
        if missing:
            ok_text = "Saved. OpenRouter is selected but still needs " + " and ".join(missing) + "."
        else:
            ok_text = "Saved. OpenRouter is the active mode: start promptpack --mcp in the project folder."
        if save():
            state['status'] = ok_text

    def edit_key():
        new_key = _curses_key_modal(stdscr, config.get('openrouter_key') or '')
        if new_key is None:
            return
        if new_key:
            config['openrouter_key'] = new_key
        else:
            config.pop('openrouter_key', None)
        settle()

    if not config.get('openrouter_models') or _models_stale(config):
        reload_models()
    selected, scroll = 0, 0
    for i, m in enumerate(models_shown()):
        if m['id'] == config.get('openrouter_model'):
            selected = i + 1
            break

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        models = models_shown()
        selected = min(selected, len(models))
        list_height = max(1, height - 6)
        idx = selected - 1
        if idx >= 0:
            if idx < scroll:
                scroll = idx
            elif idx >= scroll + list_height:
                scroll = idx - list_height + 1
        scroll = max(0, min(scroll, max(0, len(models) - list_height)))

        title = "OpenRouter - ↑↓: Navigate | Space: Choose model | k: API key | f: Filter | r: Refresh list | Esc: Back"
        _put(stdscr, 0, 0, title.ljust(width - 1), curses.A_REVERSE)
        key_row = f"API key: {config.get('openrouter_key') or '(not set - press k to paste it)'}"
        _put(stdscr, 1, 0, key_row.ljust(width - 1), curses.A_REVERSE if selected == 0 else curses.A_BOLD)
        header = f"  {'Kind':<5} {'In $/M':>8} {'Out $/M':>8} {'Context':>8}  Model (id)   [filter: {state['filter']}]"
        _put(stdscr, 2, 0, header, curses.A_BOLD)

        if not models:
            _put(stdscr, 3, 0, "No models to show. Press r to fetch the list from OpenRouter.")
        for i in range(list_height):
            mi = scroll + i
            if mi >= len(models):
                break
            m = models[mi]
            chosen = m['id'] == config.get('openrouter_model')
            line = (f"{'✓' if chosen else ' '} {'Free' if m.get('free') else 'Paid':<5} "
                    f"{_fmt_price(m.get('prompt')):>8} {_fmt_price(m.get('completion')):>8} "
                    f"{_fmt_context(m.get('context')):>8}  {m.get('name')} ({m['id']})")
            attr = curses.A_REVERSE if mi == idx else curses.A_NORMAL
            if chosen:
                attr |= curses.color_pair(1)
            _put(stdscr, 3 + i, 0, line.ljust(width - 1) if mi == idx else line, attr)

        if idx >= 0 and models:
            m = models[idx]
            detail = f"{m['id']} - {m.get('description') or '(no description)'}"
        else:
            detail = "The API key is saved in clear text in mcp.json, next to promptpack.py."
        for n, part in enumerate(textwrap.wrap(detail, max(10, width - 2))[:2]):
            _put(stdscr, height - 3 + n, 0, part)
        status = state['status'] or f"{len(models)} models, list {_fmt_age(_models_age(config))} (tool-capable only)"
        _put(stdscr, height - 1, 0, status.ljust(width - 1), curses.A_REVERSE)
        stdscr.refresh()

        key = stdscr.getch()
        if key == 27:
            break
        elif key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(len(models), selected + 1)
        elif key == curses.KEY_PPAGE:
            selected = max(0, selected - list_height)
        elif key == curses.KEY_NPAGE:
            selected = min(len(models), selected + list_height)
        elif key == ord(' '):
            if selected == 0:
                edit_key()
            elif models:
                config['openrouter_model'] = models[idx]['id']
                settle()
        elif key in (ord('k'), ord('K')):
            edit_key()
        elif key in (ord('f'), ord('F')):
            order = ['all', 'free', 'paid']
            state['filter'] = order[(order.index(state['filter']) + 1) % len(order)]
            selected = 1 if models_shown() else 0
            scroll = 0
        elif key in (ord('r'), ord('R')):
            reload_models()

    if config.get('openrouter_key') and config.get('openrouter_model') and config.get('mode') != 'openrouter':
        config['mode'] = 'openrouter'
        try:
            save_mcp_config(config)
        except OSError:
            pass


def show_mcp_menu(stdscr):
    """F6: choose how an AI reaches promptpack. Claude Desktop has no settings, OpenRouter
    has its own page. The choice is saved in mcp.json and promptpack --mcp follows it."""
    curses.curs_set(0)
    try:
        config = load_mcp_config(exit_on_error=False)
    except (OSError, ValueError) as e:
        _curses_message(stdscr, "MCP", [f"Cannot read or write {MCP_CONFIG_FILE}: {e}", "",
                                        "Repair the file, or delete it to get a new port and token."])
        return
    selected = 0
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        _put(stdscr, 0, 0, "MCP - ↑↓: Navigate | Space: Choose | Esc: Back".ljust(width - 1), curses.A_REVERSE)
        mode = config.get('mode')
        ready, problem = mcp_ready(config)
        items = [
            ('claude_desktop', 'Claude Desktop',
             'No settings. Reached through a bridge; this terminal becomes a read-only log.'),
            ('openrouter', 'OpenRouter',
             f"Chat with a model in this terminal. Model: {config.get('openrouter_model') or '(none chosen)'}"),
        ]
        for i, (name, label, desc) in enumerate(items):
            chosen = mode == name
            line = f"[{'✓' if chosen else ' '}] {label:<16} {desc}"
            attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
            if chosen:
                attr |= curses.color_pair(1)
            _put(stdscr, 2 + i, 0, line.ljust(width - 1) if i == selected else line, attr)
        row = 5
        status = "Ready: promptpack --mcp will start in the chosen mode." if ready else f"Not ready: {problem}"
        for part in textwrap.wrap(status, max(10, width - 2)):
            _put(stdscr, row, 0, part, curses.color_pair(1) if ready else curses.color_pair(3))
            row += 1
        _put(stdscr, row + 1, 0, f"Settings are saved in {MCP_CONFIG_FILE}")
        stdscr.refresh()

        key = stdscr.getch()
        if key == 27:
            return
        elif key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(len(items) - 1, selected + 1)
        elif key == ord(' '):
            if selected == 0:
                config['mode'] = 'claude_desktop'
                try:
                    save_mcp_config(config)
                except OSError as e:
                    _curses_message(stdscr, "MCP", [f"Could not save {MCP_CONFIG_FILE.name}: {e}"])
                    continue
                _show_claude_desktop_notice(stdscr)
            else:
                config['mode'] = 'openrouter'
                try:
                    save_mcp_config(config)
                except OSError as e:
                    _curses_message(stdscr, "MCP", [f"Could not save {MCP_CONFIG_FILE.name}: {e}"])
                    continue
                show_openrouter_settings(stdscr, config)


def run_mcp_server():
    """promptpack --mcp: serve this project to the AI chosen with F6 (Claude Desktop or
    OpenRouter) and log every call. Refuses to start until a mode is chosen and complete."""
    check_ctags()
    config = load_mcp_config()
    ready, problem = mcp_ready(config)
    if not ready:
        print(f"❌ {problem}")
        sys.exit(1)
    root = build_tree('.')
    instructions = build_mcp_instructions(root)
    marked = len(get_marked_files(root)) if root else 0
    header = _make_mcp_header(config)
    if config['mode'] == 'openrouter':
        run_openrouter_chat(config, instructions, marked, header)   # the curses chat view draws the header itself
        return
    port = config['port']
    try:
        server = _MCPServer(('127.0.0.1', port), config['token'], instructions)
    except OSError as e:
        print(f"❌ Cannot listen on 127.0.0.1:{port} ({e}).")
        print(f"   Another program may use the port. Change \"port\" in {MCP_CONFIG_FILE.name}.")
        sys.exit(1)
    header.start()
    print("🔌 promptpack MCP server (Claude Desktop)")
    print(f"   project: {Path.cwd()}")
    print(f"   url:     http://127.0.0.1:{port}/mcp")
    print(f"   config:  {MCP_CONFIG_FILE}")
    print(f"   marked files in spec: {marked}")
    print("   Claude Desktop: add this under mcpServers in", claude_desktop_config_hint() + ":")
    print(claude_desktop_snippet())
    print("   Restart Claude Desktop after editing the file. Keep this terminal open.\n")
    print(f"   {MCP_SECURITY_NOTE}")
    print("   This terminal is a read-only log: typing is locked. Ctrl+C to stop. Every call is logged below.\n", flush=True)
    restore_terminal = _lock_terminal_input()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ MCP server stopped", flush=True)
    finally:
        restore_terminal()
        server.server_close()
        header.stop()


def run_mcp_bridge():
    """promptpack --mcp-bridge: lets Claude Desktop reach a running promptpack --mcp.
    Claude Desktop starts this program and speaks MCP over stdin and stdout. Each
    message is passed unchanged as an HTTP POST to the server in the terminal, and
    the server's answer is written back. stdout carries only the protocol, so
    problems go to stderr. A request that cannot be answered gets a JSON-RPC error."""
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

    def warn(text):
        print(f"[promptpack-bridge] {text}", file=sys.stderr, flush=True)

    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        sys.stdout.flush()

    try:
        with open(MCP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        port, token = int(config['port']), str(config['token'])
    except (OSError, ValueError, KeyError, TypeError) as e:
        warn(f"cannot read {MCP_CONFIG_FILE.name}: {e}. Start promptpack --mcp in the project folder once first.")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/mcp"
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            msg = None
        mid = msg.get('id') if isinstance(msg, dict) else None
        req = urllib.request.Request(url, data=line.encode('utf-8'), method='POST', headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        })
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                status, reply = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, reply = e.code, e.read()
        except OSError as e:
            warn(f"cannot reach promptpack --mcp on port {port} ({e}). Is it running in the project folder?")
            if mid is not None:
                send({'jsonrpc': '2.0', 'id': mid, 'error': {
                    'code': -32000,
                    'message': 'promptpack --mcp is not running. Start it in the project folder.'}})
            continue
        if status == 202 or not reply:
            continue   # notification accepted: nothing to send back
        try:
            out = json.loads(reply.decode('utf-8'))
        except ValueError:
            out = None
        if not (isinstance(out, dict) and out.get('jsonrpc') == '2.0'):
            warn(f"server answered HTTP {status}: {reply[:200]!r}")
            if mid is None:
                continue
            out = {'jsonrpc': '2.0', 'id': mid, 'error': {
                'code': -32000,
                'message': f'promptpack --mcp answered HTTP {status}. Check the token in mcp.json.'}}
        send(out)


def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    if hasattr(curses, 'set_escdelay'):
        curses.set_escdelay(25)   # Esc is back/quit everywhere: do not wait a second for it

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

        if key == 27:
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
        elif key == curses.KEY_F6:
            show_mcp_menu(stdscr)
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
    _orig_excepthook = sys.excepthook
    def _history_excepthook(etype, value, tb):
        if issubclass(etype, HistoryCorruptError):
            append_to_clipboard_tmp(f"❌ {value}")
            print(f"❌ {err_note(str(value))}", file=sys.stderr)
        else:
            _orig_excepthook(etype, value, tb)
    sys.excepthook = _history_excepthook

    class ClipboardArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            cmd = 'promptpack ' + ' '.join(sys.argv[1:])
            append_to_clipboard_tmp(
                f"❌ PROMPTPACK ARGUMENT ERROR: {message}\n"
                f"Command that failed: {cmd}\n"
                f"Nothing was executed. Check the command syntax in the promptpack spec (e.g. -n takes 'START,END FILE', -s takes 'STRING BEFORE,AFTER FILE').\n"
            )
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: error: {message}\n(error copied to clipboard.tmp - run promptpack -c)\n")

    parser = ClipboardArgumentParser(description='Interactive directory navigator')
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
                        help='Export instructions section to promptpack_instructions.txt')
    parser.add_argument('--summary', nargs='?', const='', default=None, metavar='ABOUT',
                        help='Save a task summary to summary.json. The argument ABOUT is 1-2 dense sentences (stored as the "about" field, listed in ctags.txt # WORKLOG); the verbose text is read from stdin (heredoc), same as -f. Both are required, plus --rating. Reports back [SUMMARYID N]. One per task, run after NEWFILE/PATCH commands and before the block-closing -c. Skip when only repairing a failed patch. Use -us SUMMARYID to mark a summary as reverted later (annotation only, no patches are touched). Example: promptpack --summary "about text" --rating 2 with a heredoc on stdin.')
    parser.add_argument('-w', '--worklog', action='store_true',
                        help='Combine all applied patches and summary entries from patch.json/summary.json into a single chronological work.txt (TOC + compact entries, no code embedded).')
    parser.add_argument('-ph', '--patch-history', nargs='+', type=int, metavar='PATCHID',
                        help='Fetch full old/new code for one or more specific patch IDs from patch.json, copied to clipboard.tmp. Example: -ph 12 15 18. Use work.txt (-w) to decide which PATCHIDs are worth a closer look.')
    parser.add_argument('-log', '--log-fetch', nargs='+', metavar='SUMMARYID',
                        help='Fetch the full text (and ABOUT line) of one or more summaries from summary.json, copied to clipboard.tmp. IDs may be space- or comma-separated. Example: -log 53 54 55 or -log 53,54,55. IDs come from the # WORKLOG section in ctags.txt (lines starting with ID LOG:).')
    parser.add_argument('-completelog', '--complete-log', action='store_true',
                        help='Print the complete, unfiltered worklog (every summary with its rating, every patch line) to clipboard.tmp, in the same format as the # WORKLOG section of ctags.txt. Can be long.')
    parser.add_argument('--rating', type=int, choices=[1, 2, 3], default=None, metavar='N',
                        help='Required together with --summary: impact of the task on the code and future development, 1 (minor) to 3 (architecture, data format, workflow rules or decisions future work must respect). Decides how long the task stays visible in the ctags.txt # WORKLOG.')
    parser.add_argument('--mcp-bridge', action='store_true',
                        help='Relay MCP messages from stdin to a running promptpack --mcp. Started by Claude Desktop, not by hand.')
    parser.add_argument('--mcp', action='store_true',
                        help='Start the MCP server in this terminal: HTTP on 127.0.0.1, port and token in mcp.json next to promptpack.py. Every tool call is logged here. Stop with Ctrl+C.')
    args = parser.parse_args()

    if args.mcp:
        run_mcp_server()
        sys.exit(0)

    if args.mcp_bridge:
        run_mcp_bridge()
        sys.exit(0)


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

        print(f"\n✅ 🧹 Tidied {success_count} file(s)" + (f", ❌ {error_count} error(s)" if error_count else ""))
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
                        copied_kb = len(content.encode('utf-8')) / 1024
                        print(f"📋 Copied to clipboard: {copied_kb:,.1f} KB, {calculate_tokens(content):,} tokens")
                        try:
                            CLIPBOARD_TMP_FILE.unlink()
                            sys.exit(0)
                        except Exception as e:
                            print(f"⚠️ File copied but could not remove: {e}")
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
            if not success:
                message = err_note(message)
            print(message)
        sys.exit(0)

    if args.lines:
        line_range, filepath = args.lines
        success, message = read_lines_to_clipboard(line_range, filepath)
        if not success:
            message = err_note(message)
        print(message)
        sys.exit(0)

    if args.search:
        search_string, offset_range, filepath = args.search
        success, message = search_and_read_lines(search_string, offset_range, filepath)
        if not success:
            message = err_note(message)
        print(message)
        sys.exit(0)


    if args.file_search:
        search_term, pattern = args.file_search
        success, message = file_search(search_term, pattern)
        if not success:
            message = err_note(message)

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
                error_msg = f"🚫 Blocked: command contains blacklisted term '{term}'"
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
            print(f"⚙️ Command executed, output in clipboard.tmp")

        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            time.sleep(0.1)
            if process.poll() is None:
                process.kill()
            append_to_clipboard_tmp(f"\n[Command timed out after {timeout} seconds]")
            print(f"⏳ Command timed out, output captured up to timeout in clipboard.tmp")
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
            print(f"❌ {err_note(message)}")
            sys.exit(1)

    if args.undo is not None:
        success, message = unapply_patch(args.undo)
        if success:
            print(f"✅ ↩️ {message}")
            sys.exit(0)
        else:
            print(f"❌ {err_note(message)}")
            sys.exit(1)

    if args.undo_summary is not None:
        success, message = unapply_summary(args.undo_summary)
        if success:
            print(f"✅ {message}")
            sys.exit(0)
        else:
            print(f"❌ {err_note(message)}")
            sys.exit(1)

    if args.summary is not None:
        if not args.summary.strip():
            error_msg = "❌ Summary NOT saved: the about text is missing. Use: promptpack --summary 'about text' (1-2 dense sentences) plus the verbose text via heredoc on stdin. Resend the --summary command."
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)
        if args.rating is None:
            error_msg = "❌ Summary NOT saved: --rating is missing. Add --rating 1, 2 or 3 (3 = architecture, data format, workflow rules or a decision future work must respect; 2 = new feature or noticeable behavior change; 1 = bugfix, docs, cosmetics). Resend the --summary command."
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)
        if sys.stdin.isatty():
            error_msg = "❌ Summary NOT saved: no verbose text on stdin. Pipe it in with a heredoc: cat <<'SUMMARY' | promptpack --summary 'about text'. Resend the --summary command."
            append_to_clipboard_tmp(error_msg)
            print(error_msg)
            sys.exit(1)
        text = sys.stdin.read()
        success, message = append_to_summary_file(text, args.summary, args.rating)
        if not success:
            message = err_note(message)
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
            msg = f"📜 Fetched {len(found)} patch(es): {', '.join(map(str, found))}"
        else:
            msg = "⚠️ No matching patches found (error saved to clipboard.tmp - run promptpack -c)"
            append_to_clipboard_tmp("⚠️ No matching patches found")
        if missing:
            msg += f" | ⚠️ Not found: {', '.join(map(str, missing))}"
        print(msg)
        sys.exit(0 if found else 1)
    if args.log_fetch:
        ids = []
        bad = []
        for chunk in args.log_fetch:
            for tok in chunk.replace(',', ' ').split():
                try:
                    ids.append(int(tok))
                except ValueError:
                    bad.append(tok)
        summary_map = {s['id']: s for s in load_summary_history()}
        output_lines = []
        found = []
        missing = []
        for sid in ids:
            s = summary_map.get(sid)
            if s is None:
                missing.append(sid)
                continue
            try:
                ts_str = datetime.fromisoformat(s['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                ts_str = s.get('timestamp', 'unknown time')
            tag = " [REVERTED]" if s.get('reverted', False) else ""
            output_lines.append(f"[{ts_str}] LOG [SUMMARYID {sid}] RATING {s.get('rating', '?')}{tag}")
            if s.get('patch_ids'):
                output_lines.append(f"PATCHES: {_compress_ids(s['patch_ids'])}")
            if s.get('about'):
                output_lines.append(f"ABOUT: {s['about']}")
            output_lines.append(s.get('text', '').strip())
            output_lines.append("-" * 70)
            found.append(sid)
        if output_lines:
            append_to_clipboard_tmp("\n".join(output_lines))
        if found:
            msg = f"📜 Fetched {len(found)} summary(ies): {', '.join(map(str, found))}"
        else:
            msg = "⚠️ No matching summaries found (error saved to clipboard.tmp - run promptpack -c)"
            append_to_clipboard_tmp("⚠️ No matching summaries found")
        if missing:
            msg += f" | ⚠️ Not found: {', '.join(map(str, missing))}"
        if bad:
            msg += f" | ⚠️ Not a number: {', '.join(bad)}"
        print(msg)
        sys.exit(0 if found else 1)
    if args.complete_log:
        note, lines = build_worklog_lines(complete=True)
        if not lines:
            append_to_clipboard_tmp("⚠️ No summaries or patches found")
            print("⚠️ No summaries or patches found (error saved to clipboard.tmp - run promptpack -c)")
            sys.exit(1)
        append_to_clipboard_tmp(note + "\n" + "\n".join(lines))
        print(f"📜 Complete log: {len(lines)} lines copied to clipboard.tmp - run promptpack -c")
        sys.exit(0)
    if args.instructions:
        try:
            with open('promptpack_instructions.txt', 'w', encoding='utf-8') as out:
                out.write(PROMPTPACK_CORE_INSTRUCTIONS)
            print("📦 promptpack_instructions.txt created!")
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

                print(f"📦 {filename} created!")
                print(f"\nIncluded {file_count} files")
                print(f"File size: {file_size:,} bytes")
                print(f"Tokensize: {total_tokens:,} tokens")

            except Exception as e:
                print(f"❌ Error reading {filename}: {e}")
