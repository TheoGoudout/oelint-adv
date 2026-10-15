import ast
import fnmatch
import os
import re
import shutil
import subprocess  # noqa: S404 - running the configured tools is the purpose of this module
import tempfile
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from oelint_parser.cls_item import Function, Item, PythonBlock
from oelint_parser.cls_stash import Stash

from oelint_adv.tools_config import ToolConfig

INLINE_PLACEHOLDER = 'OELINT_INLINE_{index}'
# type stubs for the bb and oe modules
STUBS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'stubs')
# types of the parameters bitbake passes to python functions and event handlers
PARAM_ANNOTATIONS = {
    'd': 'bb.data_smart.DataSmart',
    'e': 'bb.event.Event',
}


class ToolError(Exception):
    """Raised if an external tool can't be run successfully."""


@dataclass
class Snippet:
    """A piece of embedded code found in a bitbake file."""

    item: Item
    language: str
    name: str
    full_name: str
    header: str
    body: str
    footer: str
    # line in the origin file, the first body line is located at
    body_line: int
    params: str = 'd'
    # body with inline blocks replaced by placeholders
    lint_body: str = ''
    # snippet contains inline python blocks
    has_inline: bool = False

    @property
    def origin(self) -> str:
        return self.item.Origin

    @property
    def header_line(self) -> int:
        return self.item.InFileLine


@dataclass
class Document:
    """Synthetic source file passed to a tool."""

    text: str
    # synthetic line -> (snippet, line in origin file)
    line_map: Dict[int, Tuple[Snippet, int]] = field(default_factory=dict)


@dataclass
class ToolFinding:
    """A finding reported by a tool, mapped to the bitbake file."""

    snippet: Snippet
    line: int
    code: str
    message: str
    severity: Optional[str]


def _find_inline_blocks(text: str) -> List[Tuple[int, int]]:
    """Find inline python blocks (${@...}), matching braces like bitbake does

    Returns:
        List[Tuple[int, int]]: start and end (exclusive) index of each block
    """
    res = []
    pos = text.find('${@')
    while pos >= 0:
        level = 0
        end = len(text)
        for index in range(pos + 1, len(text)):
            if text[index] == '{':
                level += 1
            elif text[index] == '}':
                level -= 1
                if not level:
                    end = index + 1
                    break
        res.append((pos, end))
        pos = text.find('${@', end)
    return res


def _replace_inline_blocks(text: str, language: str) -> Optional[str]:
    """Replace inline python blocks by placeholders

    Returns:
        Optional[str]: text with placeholders, None if a block spans multiple lines
    """
    blocks = _find_inline_blocks(text)
    for start, end in blocks:
        if '\n' in text[start:end]:
            return None
    for index, (start, end) in reversed(list(enumerate(blocks))):
        placeholder = INLINE_PLACEHOLDER.format(index=index)
        if language == 'shell':
            placeholder = '${' + placeholder + '}'
        text = text[:start] + placeholder + text[end:]
    return text


def _split_function(raw: str) -> Optional[Tuple[str, str, str]]:
    """Split a function into header, body and footer

    Returns:
        Optional[Tuple[str, str, str]]: header, body, footer or None if not splittable
    """
    newline = raw.find('\n')
    if newline < 0:
        return None
    header = raw[:newline + 1]
    if not header.rstrip().endswith('{'):
        return None
    rest = raw[newline + 1:]
    stripped = rest.rstrip()
    closing = stripped.rfind('\n') + 1
    if stripped[closing:].strip() != '}':
        return None
    return (header, rest[:closing], rest[closing:])


def _is_python(code: str) -> bool:
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return True


def _looks_like_python(item: Function) -> bool:
    """Same heuristic as oelint.task.pythonprefix: shell functions containing python code"""
    if len([x for x in item.FuncBodyRaw.split('\n') if x.strip()]) < 2:
        return False
    return _is_python(textwrap.dedent(item.FuncBodyRaw.rstrip('}\n')))


def _event_handlers(stash: Stash, _file: str) -> List[str]:
    res = []
    for item in stash.GetItemsFor(filename=_file):
        m = re.match(r'^\s*addhandler\s+(?P<names>.+)$', item.Raw.strip())
        if m:
            res += m.group('names').split()
    return res


def python_wrapper(snippet: Snippet, name: str, annotations: bool = False) -> str:
    if isinstance(snippet.item, PythonBlock):
        return ''
    params = snippet.params
    if annotations:
        params = ', '.join(f'{x}: {PARAM_ANNOTATIONS[x]}' for x in params.split(', '))
    # this is how bitbake compiles python functions and event handlers
    return f'def {name}({params}):\n'


def shell_wrapper(name: str) -> Tuple[str, str]:
    return (f'{name}() {{\n', '}\n')


def get_snippets(stash: Stash, _file: str, language: str) -> List[Snippet]:
    """Get all snippets of embedded code of a language

    Content of inherited classes is skipped, unless the class is the
    linted file itself, so the code of a class is checked once, as part of
    the class, and not again for every recipe inheriting it.
    Snippets that are empty, not parsable or contain multiline
    inline blocks are skipped as well.

    Args:
        stash (Stash): Parsed stash
        _file (str): File being linted
        language (str): python or shell

    Returns:
        List[Snippet]: List of snippets
    """
    res = []
    handlers = _event_handlers(stash, _file) if language == 'python' else []
    items = stash.GetItemsFor(filename=_file, classifier=[Function.CLASSIFIER, PythonBlock.CLASSIFIER])
    for item in sorted(items, key=lambda x: (x.Origin, x.InFileLine)):
        if item.IsFromClass and item.Origin != _file:
            continue
        if isinstance(item, PythonBlock):
            if language != 'python':
                continue
            body = item.RealRaw.rstrip('\n') + '\n'
            snippet = Snippet(item=item, language=language, name=item.FuncName, full_name=item.FuncName,
                              header='', body=body, footer=item.RealRaw[len(body):],
                              body_line=item.InFileLine)
        else:
            if item.IsPython != (language == 'python'):
                continue
            if language == 'shell' and _looks_like_python(item):
                continue
            parts = _split_function(item.RealRaw)
            if parts is None:
                continue
            header, body, footer = parts
            snippet = Snippet(item=item, language=language,
                              name=item.FuncName or '__anonymous', full_name=item.FuncNameComplete or '__anonymous',
                              header=header, body=body, footer=footer,
                              body_line=item.InFileLine + 1,
                              params='e, d' if item.FuncName in handlers else 'd')
        if not snippet.body.strip():
            continue
        lint_body = _replace_inline_blocks(snippet.body, language)
        if lint_body is None:
            continue
        snippet.lint_body = lint_body
        snippet.has_inline = lint_body != snippet.body
        if language == 'python' and not _is_python(python_wrapper(snippet, 'f') + lint_body):
            continue
        res.append(snippet)
    return res


def filter_snippets(snippets: List[Snippet], tool: ToolConfig) -> List[Snippet]:
    def _match(snippet: Snippet, patterns: List[str]) -> bool:
        return any(fnmatch.fnmatchcase(snippet.name, x) or fnmatch.fnmatchcase(snippet.full_name, x) for x in patterns)
    return [x for x in snippets if _match(x, tool.functions) and not _match(x, tool.exclude_functions)]


def _unique_names(snippets: List[Snippet]) -> List[str]:
    # def functions keep their names, generated names must not clash with them
    taken = {x.name for x in snippets if isinstance(x.item, PythonBlock)}
    res = []
    for snippet in snippets:
        if isinstance(snippet.item, PythonBlock):
            res.append(snippet.name)
            continue
        name = re.sub(r'[^A-Za-z0-9_]', '_', snippet.full_name)
        if name[0].isdigit():
            name = f'_{name}'
        candidate = name
        index = 1
        while candidate in res or candidate in taken:
            candidate = f'{name}_{index}'
            index += 1
        res.append(candidate)
    return res


def build_document(snippets: List[Snippet], tool: ToolConfig) -> Document:
    """Create a synthetic source file from snippets

    Args:
        snippets (List[Snippet]): snippets to include
        tool (ToolConfig): tool configuration

    Returns:
        Document: synthetic file
    """
    lines = list(tool.prelude)
    line_map = {}
    for snippet, name in zip(snippets, _unique_names(snippets)):
        if tool.language == 'python':
            if lines:
                lines += ['', '']
            header, footer = python_wrapper(snippet, name, tool.annotations), ''
        else:
            if lines:
                lines.append('')
            header, footer = shell_wrapper(name)
        lines += header.splitlines()
        for index, line in enumerate(snippet.lint_body.splitlines()):
            lines.append(line)
            line_map[len(lines)] = (snippet, snippet.body_line + index)
        lines += footer.splitlines()
    return Document(text='\n'.join(lines) + '\n', line_map=line_map)


_RESULTS: Dict[Tuple, Tuple[int, str, str]] = {}


def _expand(value: str, placeholders: Dict[str, str]) -> str:
    for key, replacement in {**placeholders, '{stubs}': STUBS_PATH}.items():
        value = value.replace(key, replacement)
    return value


def run_tool(tool: ToolConfig, text: str, recipe: str) -> Tuple[int, str, str]:
    """Run a tool on a text

    Args:
        tool (ToolConfig): tool configuration
        text (str): text to pass to the tool
        recipe (str): path to the linted file

    Raises:
        ToolError: if the tool can't be run or fails

    Returns:
        Tuple[int, str, str]: return code, stdout and stderr of the tool
    """
    recipe = os.path.abspath(recipe)
    cwd = tool.cwd or os.path.dirname(recipe)
    virtual_path = recipe + tool.extension
    key = (tool.name, tuple(tool.command), text, recipe, cwd)
    if key not in _RESULTS:
        tmpdir = tempfile.mkdtemp(prefix='oelint-')
        try:
            tmpfile = os.path.join(tmpdir, f'oelint_snippet{tool.extension}')
            with open(tmpfile, 'w') as o:
                o.write(text)
            placeholders = {'{file}': tmpfile, '{virtual_path}': virtual_path, '{recipe}': recipe}
            command = [_expand(x, placeholders) for x in tool.command]
            env = {k: _expand(v, placeholders) for k, v in tool.env.items()}
            try:
                proc = subprocess.run(command,  # noqa: S603 - command is user configured
                                      input=text if tool.input == 'stdin' else None,
                                      stdin=subprocess.DEVNULL if tool.input == 'file' else None,
                                      capture_output=True, text=True, cwd=cwd,
                                      env={**os.environ, **env}, timeout=tool.timeout)
            except FileNotFoundError:
                raise ToolError(f"'{command[0]}' not found")
            except subprocess.TimeoutExpired:
                raise ToolError(f'timed out after {tool.timeout} seconds')
            except OSError as e:
                raise ToolError(f"'{command[0]}' can't be run: {e}")
            _RESULTS[key] = (proc.returncode, proc.stdout, proc.stderr)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    returncode, stdout, stderr = _RESULTS[key]
    if returncode not in tool.ok_returncodes:
        details = ' '.join((stderr.strip() or stdout.strip()).split())[:300]
        raise ToolError(f'exited with code {returncode}{": " + details if details else ""}')
    return (returncode, stdout, stderr)


def parse_output(tool: ToolConfig, document: Document, output: str) -> Tuple[List[ToolFinding], int]:
    """Parse linter output to findings

    Args:
        tool (ToolConfig): tool configuration
        document (Document): synthetic document passed to the tool
        output (str): output of the tool

    Returns:
        Tuple[List[ToolFinding], int]: findings on lines of embedded code, number of matching output lines
    """
    res = []
    matches = 0
    for line in output.splitlines():
        m = tool.output_regex.match(line)
        if not m:
            continue
        matches += 1
        groups = m.groupdict()
        try:
            mapped = document.line_map.get(int(groups['line']))
        except (TypeError, ValueError):
            continue
        if mapped is None:
            # finding on a synthetic line
            continue
        severity = tool.severity
        if groups.get('severity') and groups['severity'] in tool.severity_map:
            severity = tool.severity_map[groups['severity']]
            if severity is None:
                continue
        message = (groups.get('message') or line).strip()
        code = (groups.get('code') or '').strip()
        res.append(ToolFinding(snippet=mapped[0], line=mapped[1], code=code, message=message, severity=severity))
    return (res, matches)


def lint(tool: ToolConfig, snippets: List[Snippet], recipe: str) -> Tuple[List[ToolFinding], List[Tuple[Snippet, str]]]:
    """Run a linter

    Args:
        tool (ToolConfig): tool configuration
        snippets (List[Snippet]): snippets to lint
        recipe (str): path to the linted file

    Returns:
        Tuple[List[ToolFinding], List[Tuple[Snippet, str]]]: findings and errors
    """
    findings = []
    errors = []
    groups = [snippets] if tool.scope == 'file' else [[x] for x in snippets]
    for group in groups:
        if not group:
            continue
        document = build_document(group, tool)
        try:
            returncode, stdout, stderr = run_tool(tool, document.text, recipe)
        except ToolError as e:
            errors.append((group[0], str(e)))
            continue
        _findings, matches = parse_output(tool, document, stdout if tool.output_stream == 'stdout' else stderr)
        if returncode and not matches:
            # tools like flake8 use the same return code for findings and crashes
            details = ' '.join((stderr.strip() or stdout.strip()).split())[-300:]
            errors.append((group[0], f"exited with code {returncode}, but no output matched 'output_regex'"
                                     f'{": " + details if details else ""}'))
            continue
        findings += _findings
    return (findings, errors)


def format_snippet(tool: ToolConfig, snippet: Snippet, recipe: str) -> Optional[str]:
    """Run a formatter on a snippet

    Args:
        tool (ToolConfig): tool configuration
        snippet (Snippet): snippet to format
        recipe (str): path to the linted file

    Raises:
        ToolError: if the formatter can't be run or the output can't be used

    Returns:
        Optional[str]: formatted body, None if the snippet can't be formatted safely
    """
    if snippet.has_inline:
        # the formatter could change the quoting around inline blocks
        return None
    name = _unique_names([snippet])[0]
    if tool.language == 'python':
        header, footer = python_wrapper(snippet, name, tool.annotations), ''
    else:
        header, footer = shell_wrapper(name)
    _, stdout, _ = run_tool(tool, header + snippet.body + footer, recipe)

    lines = stdout.splitlines(keepends=True)
    if header:
        if not lines or lines[0] != header:
            raise ToolError('unexpected output: function header was changed')
        lines = lines[1:]
    if footer:
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines or lines[-1].strip() != footer.strip():
            raise ToolError('unexpected output: function end was changed')
        lines = lines[:-1]
    body = ''.join(lines).rstrip('\n')
    if not body.strip():
        raise ToolError('unexpected output: function body is empty')
    body += '\n'
    if tool.language == 'python' and not _is_python(header + body):
        raise ToolError('unexpected output: formatted code is not valid python')
    return body


def tool_version(tool: ToolConfig) -> str:
    """Get the version information of a tool, as reported by its version_command

    Args:
        tool (ToolConfig): tool configuration

    Returns:
        str: version information or the reason it couldn't be determined
    """
    try:
        proc = subprocess.run(tool.version_command, capture_output=True, text=True,  # noqa: S603 - command is user configured
                              stdin=subprocess.DEVNULL, timeout=tool.timeout,
                              env={**os.environ, **{k: _expand(v, {}) for k, v in tool.env.items()}})
    except (OSError, subprocess.TimeoutExpired) as e:
        return f'{tool.name}:{e!r}'
    return f'{tool.name}:{proc.returncode}:{proc.stdout}{proc.stderr}'
