import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern

LANGUAGES = ('python', 'shell')
KINDS = ('linter', 'formatter')
SEVERITIES = ('info', 'warning', 'error')
PLACEHOLDERS = ('{file}', '{virtual_path}', '{recipe}', '{stubs}')


class ToolConfigError(ValueError):
    """Raised on invalid tool configurations."""


@dataclass
class ToolConfig:
    """Configuration of an external tool run on embedded code."""

    name: str
    language: str
    kind: str
    command: List[str]
    input: str = 'stdin'  # noqa: A003, VNE003 - name of the config key
    scope: str = 'file'
    prelude: List[str] = field(default_factory=list)
    annotations: bool = False
    output_regex: Optional[Pattern] = None
    output_stream: str = 'stdout'
    severity: str = 'warning'
    severity_map: Dict[str, Optional[str]] = field(default_factory=dict)
    ok_returncodes: List[int] = field(default_factory=list)
    functions: List[str] = field(default_factory=lambda: ['*'])
    exclude_functions: List[str] = field(default_factory=list)
    timeout: int = 60
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    version_command: List[str] = field(default_factory=list)

    @property
    def extension(self) -> str:
        return '.py' if self.language == 'python' else '.sh'


def _check_type(name: str, key: str, value, types, what: str) -> None:
    if isinstance(value, bool) or not isinstance(value, types):
        raise ToolConfigError(f"tool '{name}': '{key}' must be {what}")


def _check_str_list(name: str, key: str, value, allow_empty: bool = True) -> None:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value) or (not allow_empty and not value):
        raise ToolConfigError(f"tool '{name}': '{key}' must be a {'non-empty ' if not allow_empty else ''}list of strings")


def _parse_tool(name: str, spec: dict, basepath: str) -> ToolConfig:  # noqa: C901 - flat validation
    if not re.match(r'^[A-Za-z0-9_-]+$', name):
        raise ToolConfigError(f"tool name '{name}' may only contain letters, digits, '_' and '-'")
    if not isinstance(spec, dict):
        raise ToolConfigError(f"tool '{name}': definition must be an object")

    known = {
        'language', 'kind', 'command', 'input', 'scope', 'prelude', 'annotations', 'output_regex', 'output_stream',
        'severity', 'severity_map', 'ok_returncodes', 'functions', 'exclude_functions',
        'timeout', 'cwd', 'env', 'version_command',
    }
    unknown = sorted(set(spec) - known)
    if unknown:
        raise ToolConfigError(f"tool '{name}': unknown key(s) {', '.join(unknown)}")

    for key in ('language', 'kind', 'command'):
        if key not in spec:
            raise ToolConfigError(f"tool '{name}': '{key}' is mandatory")

    language = spec['language']
    if language not in LANGUAGES:
        raise ToolConfigError(f"tool '{name}': 'language' must be one of {', '.join(LANGUAGES)}")
    kind = spec['kind']
    if kind not in KINDS:
        raise ToolConfigError(f"tool '{name}': 'kind' must be one of {', '.join(KINDS)}")

    _check_str_list(name, 'command', spec['command'], allow_empty=False)

    tool = ToolConfig(name=name, language=language, kind=kind, command=list(spec['command']))

    tool.input = spec.get('input', 'stdin')
    if tool.input not in ('stdin', 'file'):
        raise ToolConfigError(f"tool '{name}': 'input' must be one of stdin, file")
    if tool.input == 'file' and not any('{file}' in x for x in tool.command):
        raise ToolConfigError(f"tool '{name}': 'command' must contain '{{file}}' when 'input' is 'file'")

    tool.scope = spec.get('scope', 'file' if kind == 'linter' else 'function')
    if tool.scope not in ('file', 'function'):
        raise ToolConfigError(f"tool '{name}': 'scope' must be one of file, function")
    if kind == 'formatter' and tool.scope != 'function':
        raise ToolConfigError(f"tool '{name}': formatters only support 'scope' function")

    tool.prelude = spec.get('prelude', [])
    _check_str_list(name, 'prelude', tool.prelude)
    if any('\n' in x for x in tool.prelude):
        raise ToolConfigError(f"tool '{name}': 'prelude' entries must not contain line breaks")
    if kind == 'formatter' and tool.prelude:
        raise ToolConfigError(f"tool '{name}': formatters don't support 'prelude'")

    tool.annotations = spec.get('annotations', False)
    if not isinstance(tool.annotations, bool):
        raise ToolConfigError(f"tool '{name}': 'annotations' must be a boolean")
    if tool.annotations and language != 'python':
        raise ToolConfigError(f"tool '{name}': 'annotations' is only valid for python")

    if kind == 'linter':
        if 'output_regex' not in spec:
            raise ToolConfigError(f"tool '{name}': 'output_regex' is mandatory for linters")
        _check_type(name, 'output_regex', spec['output_regex'], str, 'a string')
        try:
            tool.output_regex = re.compile(spec['output_regex'])
        except re.error as e:
            raise ToolConfigError(f"tool '{name}': 'output_regex' is invalid: {e}")
        if 'line' not in tool.output_regex.groupindex:
            raise ToolConfigError(f"tool '{name}': 'output_regex' must define the named group 'line'")
    elif 'output_regex' in spec:
        raise ToolConfigError(f"tool '{name}': 'output_regex' is only valid for linters")

    tool.output_stream = spec.get('output_stream', 'stdout')
    if tool.output_stream not in ('stdout', 'stderr'):
        raise ToolConfigError(f"tool '{name}': 'output_stream' must be one of stdout, stderr")

    tool.severity = spec.get('severity', 'warning' if kind == 'linter' else 'info')
    if tool.severity not in SEVERITIES:
        raise ToolConfigError(f"tool '{name}': 'severity' must be one of {', '.join(SEVERITIES)}")

    tool.severity_map = spec.get('severity_map', {})
    if not isinstance(tool.severity_map, dict) or \
       not all(v is None or v in SEVERITIES for v in tool.severity_map.values()):
        raise ToolConfigError(f"tool '{name}': 'severity_map' must map to one of {', '.join(SEVERITIES)} or null")

    tool.ok_returncodes = spec.get('ok_returncodes', [0, 1] if kind == 'linter' else [0])
    if not isinstance(tool.ok_returncodes, list) or \
       not all(isinstance(x, int) and not isinstance(x, bool) for x in tool.ok_returncodes):
        raise ToolConfigError(f"tool '{name}': 'ok_returncodes' must be a list of integers")

    tool.functions = spec.get('functions', ['*'])
    _check_str_list(name, 'functions', tool.functions)
    tool.exclude_functions = spec.get('exclude_functions', [])
    _check_str_list(name, 'exclude_functions', tool.exclude_functions)

    tool.timeout = spec.get('timeout', 60)
    _check_type(name, 'timeout', tool.timeout, (int, float), 'a number')
    if tool.timeout <= 0:
        raise ToolConfigError(f"tool '{name}': 'timeout' must be greater than 0")

    tool.cwd = spec.get('cwd', None)
    if tool.cwd is not None:
        _check_type(name, 'cwd', tool.cwd, str, 'a string')
        tool.cwd = os.path.join(basepath, os.path.expanduser(tool.cwd))

    tool.env = spec.get('env', {})
    if not isinstance(tool.env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tool.env.items()):
        raise ToolConfigError(f"tool '{name}': 'env' must map strings to strings")

    tool.version_command = spec.get('version_command', [])
    _check_str_list(name, 'version_command', tool.version_command)

    return tool


def parse_tools_config(content: dict, basepath: str) -> List[ToolConfig]:
    """Parse and validate a tools configuration

    Args:
        content (dict): Loaded JSON content
        basepath (str): Directory relative paths are resolved against

    Raises:
        ToolConfigError: on invalid configurations

    Returns:
        List[ToolConfig]: configured tools
    """
    if not isinstance(content, dict):
        raise ToolConfigError('tools configuration must be an object')
    unknown = sorted(set(content) - {'tools'})
    if unknown:
        raise ToolConfigError(f"unknown key(s) {', '.join(unknown)}")
    tools = content.get('tools', {})
    if not isinstance(tools, dict):
        raise ToolConfigError("'tools' must be an object")
    return [_parse_tool(name, spec, basepath) for name, spec in tools.items()]


def load_tools_config(path: str) -> List[ToolConfig]:
    """Load a tools configuration file

    Args:
        path (str): Path to the JSON file

    Raises:
        ToolConfigError: on unreadable or invalid files

    Returns:
        List[ToolConfig]: configured tools
    """
    try:
        with open(path) as i:
            content = json.load(i)
    except (json.JSONDecodeError, FileNotFoundError, IsADirectoryError) as e:
        raise ToolConfigError(f"'{path}' is not a valid tools configuration: {e}")
    return parse_tools_config(content, os.path.dirname(os.path.abspath(path)))
