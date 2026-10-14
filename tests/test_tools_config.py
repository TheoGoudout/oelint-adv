import os
import re
import sys

import pytest  # noqa: I900

from .base import TestBaseClass


# flake8: noqa S101 - n.a. for test files
class TestClassToolsConfig(TestBaseClass):

    LINTER = {
        'language': 'python',
        'kind': 'linter',
        'command': ['tool', '-'],
        'output_regex': '^(?P<line>\\d+)$',
    }

    FORMATTER = {
        'language': 'python',
        'kind': 'formatter',
        'command': ['tool', '-'],
    }

    def _parse(self, tools, basepath='/base'):
        from oelint_adv.tools_config import parse_tools_config
        return parse_tools_config({'tools': tools}, basepath)

    def test_defaults(self):
        linter, formatter = self._parse({'lint': self.LINTER, 'fmt': self.FORMATTER})
        assert linter.name == 'lint'
        assert linter.input == 'stdin'
        assert linter.scope == 'file'
        assert linter.severity == 'warning'
        assert linter.ok_returncodes == [0, 1]
        assert linter.functions == ['*']
        assert linter.exclude_functions == []
        assert linter.cwd is None
        assert linter.extension == '.py'
        assert formatter.scope == 'function'
        assert formatter.severity == 'info'
        assert formatter.ok_returncodes == [0]
        assert formatter.output_regex is None

    def test_full(self):
        tool, = self._parse({'lint': {
            **self.LINTER,
            'language': 'shell',
            'input': 'file',
            'command': ['tool', '{file}'],
            'scope': 'function',
            'prelude': ['# a'],
            'output_stream': 'stderr',
            'severity': 'error',
            'severity_map': {'a': 'info', 'b': None},
            'ok_returncodes': [0, 2],
            'functions': ['do_*'],
            'exclude_functions': ['do_install'],
            'timeout': 1.5,
            'cwd': 'sub',
            'env': {'A': 'B'},
            'version_command': ['tool', '--version'],
        }})
        assert tool.extension == '.sh'
        assert tool.cwd == '/base/sub'
        assert tool.severity_map == {'a': 'info', 'b': None}
        assert tool.timeout == 1.5

    def test_empty(self):
        from oelint_adv.tools_config import parse_tools_config
        assert parse_tools_config({}, '/') == []
        assert self._parse({}) == []

    @pytest.mark.parametrize('content,error',
                             [
                                 ([], 'tools configuration must be an object'),
                                 ({'foo': {}}, 'unknown key\\(s\\) foo'),
                                 ({'tools': []}, "'tools' must be an object"),
                             ],
                             )
    def test_bad_toplevel(self, content, error):
        from oelint_adv.tools_config import ToolConfigError, parse_tools_config
        with pytest.raises(ToolConfigError, match=error):
            parse_tools_config(content, '/')

    @pytest.mark.parametrize('name,spec,error',
                             [
                                 ('a.b', LINTER, 'may only contain'),
                                 ('', LINTER, 'may only contain'),
                                 ('a', [], 'definition must be an object'),
                                 ('a', {**LINTER, 'foo': 1, 'bar': 2}, 'unknown key\\(s\\) bar, foo'),
                                 ('a', {'kind': 'linter', 'command': ['a']}, "'language' is mandatory"),
                                 ('a', {'language': 'python', 'command': ['a']}, "'kind' is mandatory"),
                                 ('a', {'language': 'python', 'kind': 'linter'}, "'command' is mandatory"),
                                 ('a', {**LINTER, 'language': 'perl'}, "'language' must be one of python, shell"),
                                 ('a', {**LINTER, 'kind': 'checker'}, "'kind' must be one of linter, formatter"),
                                 ('a', {**LINTER, 'command': []}, "'command' must be a non-empty list of strings"),
                                 ('a', {**LINTER, 'command': 'tool'}, "'command' must be a non-empty list of strings"),
                                 ('a', {**LINTER, 'command': ['tool', 1]}, "'command' must be a non-empty list of strings"),
                                 ('a', {**LINTER, 'input': 'pipe'}, "'input' must be one of stdin, file"),
                                 ('a', {**LINTER, 'input': 'file'}, "'command' must contain '{file}'"),
                                 ('a', {**LINTER, 'scope': 'all'}, "'scope' must be one of file, function"),
                                 ('a', {**FORMATTER, 'scope': 'file'}, 'formatters only support'),
                                 ('a', {**LINTER, 'prelude': 'import os'}, "'prelude' must be a list of strings"),
                                 ('a', {**LINTER, 'prelude': ['a\nb']}, 'must not contain line breaks'),
                                 ('a', {**FORMATTER, 'prelude': ['a']}, "formatters don't support 'prelude'"),
                                 ('a', {'language': 'python', 'kind': 'linter', 'command': ['a']}, "'output_regex' is mandatory"),
                                 ('a', {**LINTER, 'output_regex': 1}, "'output_regex' must be a string"),
                                 ('a', {**LINTER, 'output_regex': '('}, "'output_regex' is invalid"),
                                 ('a', {**LINTER, 'output_regex': '^\\d+$'}, "must define the named group 'line'"),
                                 ('a', {**FORMATTER, 'output_regex': '^(?P<line>\\d+)$'}, 'only valid for linters'),
                                 ('a', {**LINTER, 'output_stream': 'both'}, "'output_stream' must be one of stdout, stderr"),
                                 ('a', {**LINTER, 'severity': 'fatal'}, "'severity' must be one of"),
                                 ('a', {**LINTER, 'severity_map': []}, "'severity_map' must map to"),
                                 ('a', {**LINTER, 'severity_map': {'a': 'fatal'}}, "'severity_map' must map to"),
                                 ('a', {**LINTER, 'ok_returncodes': 0}, "'ok_returncodes' must be a list of integers"),
                                 ('a', {**LINTER, 'ok_returncodes': [True]}, "'ok_returncodes' must be a list of integers"),
                                 ('a', {**LINTER, 'functions': 'do_*'}, "'functions' must be a list of strings"),
                                 ('a', {**LINTER, 'exclude_functions': [1]}, "'exclude_functions' must be a list of strings"),
                                 ('a', {**LINTER, 'timeout': '1'}, "'timeout' must be a number"),
                                 ('a', {**LINTER, 'timeout': True}, "'timeout' must be a number"),
                                 ('a', {**LINTER, 'timeout': 0}, "'timeout' must be greater than 0"),
                                 ('a', {**LINTER, 'cwd': 1}, "'cwd' must be a string"),
                                 ('a', {**LINTER, 'env': []}, "'env' must map strings to strings"),
                                 ('a', {**LINTER, 'env': {'a': 1}}, "'env' must map strings to strings"),
                                 ('a', {**LINTER, 'version_command': 'tool'}, "'version_command' must be a list of strings"),
                             ],
                             )
    def test_bad_tool(self, name, spec, error):
        from oelint_adv.tools_config import ToolConfigError
        with pytest.raises(ToolConfigError, match=error):
            self._parse({name: spec})

    def test_load(self):
        from oelint_adv.tools_config import ToolConfigError, load_tools_config
        _path = self._create_tempfile('tools.json', '{"tools": {"a": {"language": "shell", "kind": "formatter", "command": ["a"], "cwd": "x"}}}')
        tool, = load_tools_config(_path)
        assert tool.cwd == os.path.join(os.path.dirname(_path), 'x')
        for content in ['{', '[']:
            _path = self._create_tempfile('bad.json', content)
            with pytest.raises(ToolConfigError):
                load_tools_config(_path)
        with pytest.raises(ToolConfigError, match='is not a valid tools configuration'):
            load_tools_config(os.path.dirname(_path))

    def test_inline_blocks(self):
        from oelint_adv.embedded import _find_inline_blocks, _replace_inline_blocks
        assert _find_inline_blocks('a ${@b} c ${@{"a": "b"}["a"]} ${@d') == [(2, 7), (10, 29), (30, 34)]
        assert _replace_inline_blocks('a ${@b} c ${@d}', 'shell') == 'a ${OELINT_INLINE_0} c ${OELINT_INLINE_1}'
        assert _replace_inline_blocks("x = '${@b}'", 'python') == "x = 'OELINT_INLINE_0'"
        assert _replace_inline_blocks('a ${@b\n}', 'shell') is None

    def test_split_function(self):
        from oelint_adv.embedded import _split_function
        assert _split_function('do_a() {') is None
        assert _split_function('do_a()\n{\n}\n') is None
        assert _split_function('do_a() {\n    echo a }\n') is None
        assert _split_function('do_a() {\n    echo a\n}  \n\n') == ('do_a() {\n', '    echo a\n', '}  \n\n')

    def test_unique_names(self):
        from oelint_adv.embedded import Snippet, _unique_names

        def _snippet(name):
            return Snippet(item=None, language='shell', name=name, full_name=name, header='', body='', footer='', body_line=1)
        assert _unique_names([_snippet(x) for x in ['do_a:append', 'do_a:append', 'do_a_append', '1abc', 'a-b']]) == \
            ['do_a_append', 'do_a_append_1', 'do_a_append_2', '_1abc', 'a_b']

    def test_parse_output(self):
        from oelint_adv.embedded import Document, Snippet, parse_output
        from oelint_adv.tools_config import ToolConfig
        snippet = Snippet(item=None, language='shell', name='a', full_name='a', header='', body='', footer='', body_line=1)
        document = Document(text='', line_map={2: (snippet, 10)})
        tool = ToolConfig(name='a', language='shell', kind='linter', command=['a'],
                          output_regex=re.compile(r'^(?P<line>\w+)?:(?P<message>.*)$'))
        findings, matches = parse_output(tool, document, 'abc:not a number\n:no line\n2:  ok  \n3:unmapped\nnomatch')
        assert matches == 4
        assert [(x.line, x.message, x.code, x.severity) for x in findings] == [(10, 'ok', '', 'warning')]

    def test_tool_version(self):
        from oelint_adv.embedded import tool_version
        from oelint_adv.tools_config import ToolConfig
        tool = ToolConfig(name='a', language='shell', kind='linter', command=['a'],
                          version_command=[sys.executable, '-c', 'print("1.0")'])
        assert tool_version(tool) == 'a:0:1.0\n'
        tool.version_command = ['oelint-adv-tool-does-not-exist']
        assert tool_version(tool).startswith('a:FileNotFoundError(')
        tool.version_command = [sys.executable, '-c', 'import time; time.sleep(10)']
        tool.timeout = 0.5
        assert tool_version(tool).startswith('a:TimeoutExpired(')
