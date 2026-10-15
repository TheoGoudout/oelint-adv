import json
import os
import re
import sys

import pytest  # noqa: I900

from .base import TestBaseClass

EXAMPLE_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'tools-config.json')


# flake8: noqa S101 - n.a. for test files
class TestClassOelintTools(TestBaseClass):

    def _tools_config(self, tools):
        return self._create_tempfile('tools.json', json.dumps({'tools': tools}))

    def _script(self, name, content):
        return self._create_tempfile(name, content)

    def _issues(self, args):
        from oelint_adv.__main__ import run
        issues, _ = run(args)
        return [x[1] for x in issues]

    def check_for_tool(self, args, id_, occurrences):
        # unlike check_for_id this counts sub IDs (e.g. oelint.tools.ruff.F401 for oelint.tools.ruff) as well
        issues = [x for x in self._issues(args) if re.search(rf':{re.escape(id_)}[\w.-]*:', x)]
        assert len(issues) == occurrences, '{id} expected {o} time(s) in:\n{i}'.format(id=id_, o=occurrences, i='\n'.join(issues))

    # ---- example configuration with the real tools ----

    @pytest.mark.parametrize('id_', ['oelint.tools.shellcheck.SC3014'])
    @pytest.mark.parametrize('occurrence', [1])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         if [ "${A}" == "b" ]; then
                                             install -d "${D}${bindir}"
                                         fi
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install:append() {
                                         if [ "${@bb.utils.contains('DISTRO_FEATURES', 'x11', 'a', 'b', d)}" == "b" ]; then
                                             install -d "${D}${bindir}"
                                         fi
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     require oelint_adv_test.inc
                                     ''',
                                     'oelint_adv_test.inc':
                                     '''
                                     A = "1"

                                     fakeroot do_install() {
                                         if [ "${A}" == "b" ]; then
                                             install -d "${D}${bindir}"
                                         fi
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_shellcheck_bad(self, input_, id_, occurrence):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         install -d "${D}${bindir}"
                                         if [ "${A}" == "b" ]; then
                                             echo a
                                         fi
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_line_mapping(self, input_):
        issues = self._issues(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]))
        assert any(x.endswith('oelint_adv_test.bb:3:warning:oelint.tools.shellcheck.SC3014:'
                              'In POSIX sh, == in place of = is undefined. [branch:true]') for x in issues), issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     require oelint_adv_test.inc
                                     ''',
                                     'oelint_adv_test.inc':
                                     '''
                                     A = "1"

                                     python do_foo() {
                                         import os
                                         bb.note(d.getVar("A"))
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_line_mapping_include(self, input_):
        issues = self._issues(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]))
        assert any(x.endswith('oelint_adv_test.inc:4:warning:oelint.tools.ruff.F401:`os` imported but unused [branch:true]')
                   for x in issues), issues

    @pytest.mark.parametrize('id_', ['oelint.tools.shellcheck'])
    @pytest.mark.parametrize('occurrence', [0])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         install -d "${D}${bindir}"
                                         local foo="${libdir}"
                                         echo "${foo}" "${@bb.utils.contains('DISTRO_FEATURES', 'x11', 'a', 'b', d)}"
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     # nooelint: oelint.tools.shellcheck.SC3014
                                     do_install() {
                                         if [ "${A}" == "b" ]; then
                                             install -d "${D}${bindir}"
                                         fi
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         # shellcheck disable=SC3014
                                         if [ "${A}" == "b" ]; then
                                             install -d "${D}${bindir}"
                                         fi
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo ${@'a' if
                                         True else 'b'}
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         import os
                                         x = os.path.join("a", "b")
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_shellcheck_good(self, input_, id_, occurrence):
        self.check_for_tool(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         if [ "${A}" == "b" ]; then
                                             echo a
                                         fi
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_shellcheck_suppress(self, input_):
        self.check_for_tool(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG,
                                                       '--suppress', 'oelint.tools.shellcheck.SC3014']),
                            'oelint.tools.shellcheck', 0)

    def test_inherited_class(self):
        from oelint_parser.cls_item import Function
        from oelint_parser.cls_stash import Stash

        from oelint_adv.embedded import get_snippets
        self._create_tempfile('conf/layer.conf', 'BBPATH .= ":${LAYERDIR}"')
        self._create_tempfile('classes/oelint_adv_test_class.bbclass', '''
            do_install() {
                if [ "${A}" == "b" ]; then
                    echo a
                fi
            }
            ''')
        _recipe = self._create_tempfile('recipes-test/oelint_adv_test.bb', '''
            inherit oelint_adv_test_class
            do_compile() {
                echo b
            }
            ''')
        stash = Stash(quiet=True)
        stash.AddFile(_recipe)
        stash.Finalize()
        # the class has been parsed ...
        assert [x.FuncName for x in stash.GetItemsFor(filename=_recipe, classifier=Function.CLASSIFIER)] == ['do_install', 'do_compile']
        # ... but only the code of the recipe is checked as part of the recipe
        assert [x.name for x in get_snippets(stash, _recipe, 'shell')] == ['do_compile']

        # the code of the class is checked once, as part of the class, like all other rules do
        issues = [x for x in self._issues(self._create_args_existing_file(_recipe, ['--tools-config', EXAMPLE_CONFIG]))
                  if 'oelint.tools' in x]
        assert len(issues) == 1 and 'oelint_adv_test_class.bbclass:2:warning:oelint.tools.shellcheck.SC3014:' in issues[0], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'classes/oelint_adv_test_class.bbclass':
                                     '''
                                     do_install() {
                                         if [ "${A}" == "b" ]; then
                                             echo a
                                         fi
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_bbclass_itself(self, input_):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]),
                          'oelint.tools.shellcheck.SC3014', 1)

    @pytest.mark.parametrize('id_', ['oelint.tools.ruff.F821', 'oelint.tools.flake8.F821', 'oelint.tools.mypy.name-defined'])
    @pytest.mark.parametrize('occurrence', [1])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         bb.note(d.getVar("A") + undefined_name)
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python () {
                                         bb.note(d.getVar("A") + undefined_name)
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     def foo(d):
                                         return d.getVar("A") + undefined_name
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python oelint_handler() {
                                         bb.note(e.data.getVar("A") + d.getVar("B") + undefined_name)
                                     }
                                     addhandler oelint_handler
                                     ''',
                                 },
                             ],
                             )
    def test_python_bad(self, input_, id_, occurrence):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    # flake8 is limited to pyflakes and pycodestyle, as the plugins installed for the development of oelint-adv add a lot of noise
    @pytest.mark.parametrize('id_', ['oelint.tools.ruff', 'oelint.tools.flake8.F', 'oelint.tools.flake8.E', 'oelint.tools.flake8.W',
                                     'oelint.tools.mypy', 'oelint.tools.black'])
    @pytest.mark.parametrize('occurrence', [0])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         import os

                                         bb.note(os.path.join(d.getVar("A") or "", "${@d.getVar('B')}"))
                                         helper(d)
                                     }

                                     def helper(d):
                                         return d.getVar("A")
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python oelint_handler() {
                                         bb.note((e.data.getVar("A") or "") + (d.getVar("B") or ""))
                                     }
                                     addhandler oelint_handler
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                     foo bar
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python helper() {
                                         bb.note(d.getVar("A") or "")
                                     }

                                     def helper(d):
                                         return d.getVar("A")
                                     ''',
                                 },
                             ],
                             )
    def test_python_good(self, input_, id_, occurrence):
        args = self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG])
        self.check_for_tool(args, id_, occurrence)
        # flake8 itself didn't fail
        self.check_for_id(args, 'oelint.tools.flake8', 0)

    @pytest.mark.parametrize('id_,occurrence',
                             [
                                 ('oelint.tools.mypy.union-attr', 1),
                                 ('oelint.tools.mypy.attr-defined', 0),
                                 ('oelint.tools.mypy.arg-type', 0),
                                 ('oelint.tools.mypy.import-not-found', 0),
                             ],
                             )
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         bb.note(" ".join(d.getVar("A").split()))
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python () {
                                         if d.getVarFlag("do_foo", "network").lower() == "1":
                                             bb.utils.mkdirhier(d.expand("${WORKDIR}/foo"))
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python oelint_handler() {
                                         bb.note(e.data.getVar("A").strip())
                                     }
                                     addhandler oelint_handler
                                     ''',
                                 },
                             ],
                             )
    def test_python_typed_bad_none(self, input_, id_, occurrence):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    @pytest.mark.parametrize('id_,occurrence',
                             [
                                 ('oelint.tools.mypy.attr-defined', 1),
                                 ('oelint.tools.mypy.arg-type', 1),
                                 ('oelint.tools.mypy.import-not-found', 0),
                             ],
                             )
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         bb.warning("a")
                                         oe.path.join(d.getVar("A") or "", 1)
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python oelint_handler() {
                                         bb.note(" ".join(e.getPkgs()))
                                         bb.utils.mkdirhier(bb.utils.contains("A", "b", 1, None, d))
                                     }
                                     addhandler oelint_handler
                                     ''',
                                 },
                             ],
                             )
    def test_python_typed_bad_api(self, input_, id_, occurrence):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    @pytest.mark.parametrize('id_', ['oelint.tools.mypy'])
    @pytest.mark.parametrize('occurrence', [0])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         import oe.patch

                                         fetcher = bb.fetch2.Fetch((d.getVar("SRC_URI") or "").split(), d)
                                         fetcher.download()
                                         for url in fetcher.urls:
                                             bb.note(fetcher.localpath(url))
                                         bb.fetch.Fetch([], d).unpack(d.getVar("WORKDIR") or "")
                                         if oe.types.boolean(d.getVar("A")) and bb.data.inherits_class("native", d):
                                             bb.utils.remove(oe.path.join(d.getVar("D") or "", "foo"), recurse=True)
                                         d.setVar("B", oe.utils.conditional("A", "1", "a", "b", d).upper())
                                         stdout, _ = bb.process.run(["true"])
                                         oe.patch.PatchSet(d)
                                         bb.runqueue.anything(stdout)
                                     }

                                     def helper(d):
                                         return d.getVar("A").split()
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python oelint_handler() {
                                         if isinstance(e, bb.event.BuildStarted):
                                             bb.note(" ".join(e.getPkgs()))
                                         elif isinstance(e, bb.build.TaskFailed):
                                             bb.note(e.taskname, e.logfile or "")
                                     }
                                     addhandler oelint_handler
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         try:
                                             helper(d)
                                         except bb.parse.SkipRecipe:
                                             raise
                                         except bb.process.ExecutionError as e:
                                             bb.fatal(str(e.exitcode))
                                     }

                                     def helper(d: bb.data_smart.DataSmart):
                                         return d.getVar("A") or ""
                                     ''',
                                 },
                             ],
                             )
    def test_python_typed_good(self, input_, id_, occurrence):
        self.check_for_tool(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         x = d.getVar('A')
                                     }

                                     python oelint_handler() {
                                         x = e.data.getVar('A')
                                     }
                                     addhandler oelint_handler

                                     def helper(d):
                                         return d.getVar('A')
                                     ''',
                                 },
                             ],
                             )
    def test_annotations_stubs(self, input_):
        script = self._script('linter.py', '''
            import os
            import sys
            stubs = sys.argv[1]
            valid = stubs == os.environ['OELINT_STUBS'] and os.path.isfile(os.path.join(stubs, 'bb', 'data_smart.pyi'))
            for index, line in enumerate(sys.stdin.read().splitlines(), start=1):
                if line.startswith('def '):
                    print(f'{index + 1}:{valid}:{line}')
            ''')
        tools = {
            'typed': {
                'language': 'python',
                'kind': 'linter',
                'annotations': True,
                'command': [sys.executable, script, '{stubs}'],
                'env': {'OELINT_STUBS': '{stubs}'},
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
            },
        }
        issues = sorted(x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x)
        assert issues == [
            '11:warning:oelint.tools.typed:True:def helper(d): [branch:true]',
            '2:warning:oelint.tools.typed:True:def do_foo(d: bb.data_smart.DataSmart): [branch:true]',
            '6:warning:oelint.tools.typed:True:def oelint_handler(e: bb.event.Event, d: bb.data_smart.DataSmart): [branch:true]',
        ], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         x = d.getVar('A')
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_annotations_formatter(self, input_):
        from oelint_adv.__main__ import run
        with open(EXAMPLE_CONFIG) as i:
            black = json.load(i)['tools']['black']
        tools = {'black': {**black, 'annotations': True}}
        args = self._create_args_fix(input_, ['--tools-config', self._tools_config(tools)])
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == 'python do_foo() {\n    x = d.getVar("A")\n}\n'

    def test_stubs(self):
        import subprocess
        from oelint_adv.embedded import STUBS_PATH
        proc = subprocess.run(['mypy', '--strict', '--cache-dir=/dev/null', '-p', 'bb', '-p', 'oe'],
                              capture_output=True, text=True, env={**os.environ, 'MYPYPATH': STUBS_PATH})
        assert proc.returncode == 0, proc.stdout + proc.stderr

    @pytest.mark.parametrize('id_', ['oelint.tools.black'])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         import os
                                         x = d.getVar('A')
                                         bb.note(os.path.join(x,'b'))
                                     }
                                     ''',
                                 },
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     require oelint_adv_test.inc
                                     ''',
                                     'oelint_adv_test.inc':
                                     '''
                                     def foo(d):
                                         return d.getVar('A')
                                     ''',
                                 },
                             ],
                             )
    def test_black_fix(self, input_, id_):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, 1)
        self.fix_and_check(self._create_args_fix(input_, ['--tools-config', EXAMPLE_CONFIG]), id_)

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     A = "1"

                                     python do_foo() {
                                         x = d.getVar('A')
                                     }

                                     B = "2"
                                     ''',
                                 },
                             ],
                             )
    def test_black_fix_content(self, input_):
        from oelint_adv.__main__ import run
        args = self._create_args_fix(input_, ['--tools-config', EXAMPLE_CONFIG])
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == 'A = "1"\n\npython do_foo() {\n    x = d.getVar("A")\n}\n\nB = "2"\n'

    @pytest.mark.parametrize('id_', ['oelint.tools.black'])
    @pytest.mark.parametrize('occurrence', [0])
    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     python do_foo() {
                                         x = d.getVar('${@d.getVar("A")}')
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_black_inline_skipped(self, input_, id_, occurrence):
        self.check_for_id(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG]), id_, occurrence)
        args = self._create_args_fix(input_, ['--tools-config', EXAMPLE_CONFIG])
        from oelint_adv.__main__ import run
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == 'python do_foo() {\n    x = d.getVar(\'${@d.getVar("A")}\')\n}\n'

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         if [ "${A}" == "b" ]; then
                                             echo a
                                         fi
                                     }
                                     python do_foo() {
                                         y: int = "a"
                                         bb.note(y)
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_mode_all(self, input_):
        issues = self._issues(self._create_args(input_, ['--tools-config', EXAMPLE_CONFIG, '--mode=all']))
        assert len([x for x in issues if ':oelint.tools.shellcheck.SC3014:' in x]) == 1, issues
        assert len([x for x in issues if ':oelint.tools.mypy.assignment:' in x]) == 1, issues

    # ---- generic behavior with configured (fake) tools ----

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     do_compile() {
                                         echo b
                                     }
                                     python do_foo() {
                                         bb.note("a")
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_function_filter(self, input_):
        script = self._script('linter.py', '''
            import sys
            for index, line in enumerate(sys.stdin.read().splitlines(), start=1):
                if line.strip().startswith('echo'):
                    print(f'{index}:X1:{line.strip()}')
            ''')
        tools = {
            'echo': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<code>\\w+):(?P<message>.*)$',
                'functions': ['do_*'],
                'exclude_functions': ['do_compile'],
            },
        }
        issues = self._issues(self._create_args(input_, ['--tools-config', self._tools_config(tools)]))
        assert [x.split(':', 1)[1] for x in issues if 'oelint.tools' in x] == [
            '2:warning:oelint.tools.echo.X1:echo a [branch:true]'], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_severity_map(self, input_):
        script = self._script('linter.py', '''
            import sys
            print('2:error:E1:an error')
            print('2:note:N1:a note')
            print('2:info:I1:an info')
            print('2:other:O1:other')
            print('2:::no severity')
            print('1:error:E2:on the synthetic header')
            print('garbage')
            sys.exit(1)
            ''')
        tools = {
            'sev': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<severity>\\w*):(?P<code>[\\w-]*):(?P<message>.*)$',
                'severity': 'info',
                'severity_map': {'error': 'error', 'note': None, 'info': 'warning'},
            },
        }
        issues = sorted(x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x)
        assert issues == [
            '2:error:oelint.tools.sev.E1:an error [branch:true]',
            '2:info:oelint.tools.sev.O1:other [branch:true]',
            '2:info:oelint.tools.sev:no severity [branch:true]',
            '2:warning:oelint.tools.sev.I1:an info [branch:true]',
        ], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_rulefile(self, input_):
        script = self._script('linter.py', '''
            print('2:E1:an error')
            print('2:E2:another error')
            ''')
        tools = {
            'rf': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<code>\\w+):(?P<message>.*)$',
            },
            'other': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<code>\\w+):(?P<message>.*)$',
            },
        }
        rulefile = self._create_tempfile('rulefile.json', json.dumps({'oelint.tools.rf.E1': 'error'}))
        issues = [x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools), '--rulefile', rulefile]))]
        assert issues == ['2:error:oelint.tools.rf.E1:an error [branch:true]'], issues

        rulefile = self._create_tempfile('rulefile2.json', json.dumps({'oelint.tools.rf': '', 'oelint.tools.other': 'error'}))
        issues = sorted(x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools), '--rulefile', rulefile])))
        assert issues == [
            '2:error:oelint.tools.other.E1:an error [branch:true]',
            '2:error:oelint.tools.other.E2:another error [branch:true]',
            '2:warning:oelint.tools.rf.E1:an error [branch:true]',
            '2:warning:oelint.tools.rf.E2:another error [branch:true]',
        ], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_print_rulefile(self, input_, capsys):
        from oelint_adv.__main__ import print_rulefile
        tools = {
            'rf': {
                'language': 'shell',
                'kind': 'linter',
                'command': ['true'],
                'output_regex': '^(?P<line>\\d+)$',
            },
        }
        rulefile = self._create_tempfile('rulefile.json', json.dumps({'oelint.tools.rf.E1': 'error'}))
        print_rulefile(self._create_args(input_, ['--tools-config', self._tools_config(tools), '--rulefile', rulefile]))
        assert json.loads(capsys.readouterr().out) == {'oelint.tools.rf.E1': 'error'}

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_stderr_file_input_cwd_env(self, input_):
        script = self._script('linter.py', '''
            import os
            import sys
            with open(sys.argv[1]) as i:
                lines = i.read().splitlines()
            sys.stderr.write(f'{len(lines) - 1}:{os.path.basename(os.getcwd())}:{os.environ["OELINT_TEST"]}:{sys.argv[2]}\\n')
            ''')
        os.makedirs(os.path.join(self._tmpdir, 'workdir'))
        tools = {
            'stderr': {
                'language': 'shell',
                'kind': 'linter',
                'input': 'file',
                'command': [sys.executable, script, '{file}', '{virtual_path}:{recipe}'],
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
                'output_stream': 'stderr',
                'cwd': 'workdir',
                'env': {'OELINT_TEST': 'set'},
            },
        }
        args = self._create_args(input_, ['--tools-config', self._tools_config(tools)])
        issues = [x.split(':', 1)[1] for x in self._issues(args) if 'oelint.tools' in x]
        recipe = args.files[0]
        assert issues == [f'2:warning:oelint.tools.stderr:workdir:set:{recipe}.sh:{recipe} [branch:true]'], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     do_install:append() {
                                         echo b
                                     }
                                     do_install:append() {
                                         echo c
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_document(self, input_):
        script = self._script('linter.py', '''
            import sys
            for index, line in enumerate(sys.stdin.read().splitlines(), start=1):
                print(f'{index}:{line}')
            ''')
        tools = {
            'doc': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
                'prelude': ['# prelude'],
            },
        }
        issues = sorted(x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x)
        assert issues == [
            '2:warning:oelint.tools.doc:echo a [branch:true]',
            '5:warning:oelint.tools.doc:echo b [branch:true]',
            '8:warning:oelint.tools.doc:echo c [branch:true]',
        ], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    @pytest.mark.parametrize('command,timeout,expected,expected_fmt',
                             [
                                 (['oelint-adv-tool-does-not-exist'], 60,
                                  "'oelint-adv-tool-does-not-exist' not found", None),
                                 ([sys.executable, '-c', 'import time; time.sleep(10)'], 0.5,
                                  'timed out after 0.5 seconds', None),
                                 ([sys.executable, '-c', 'import sys; sys.exit(3)'], 60,
                                  'exited with code 3', None),
                                 ([sys.executable, '-c', 'import sys; sys.stderr.write("bad  things\\n happened"); sys.exit(3)'], 60,
                                  'exited with code 3: bad things happened', None),
                                 ([sys.executable, '-c', 'import sys; sys.stderr.write("Traceback: crash"); sys.exit(1)'], 60,
                                  "exited with code 1, but no output matched 'output_regex': Traceback: crash",
                                  'exited with code 1: Traceback: crash'),
                                 ([sys.executable, '-c', 'import sys; sys.exit(1)'], 60,
                                  "exited with code 1, but no output matched 'output_regex'",
                                  'exited with code 1'),
                             ],
                             )
    def test_tool_errors(self, input_, command, timeout, expected, expected_fmt):
        tools = {
            'broken': {
                'language': 'shell',
                'kind': 'linter',
                'command': command,
                'output_regex': '^(?P<line>\\d+)$',
                'timeout': timeout,
            },
            'brokenfmt': {
                'language': 'shell',
                'kind': 'formatter',
                'command': command,
                'timeout': timeout,
            },
        }
        issues = sorted(x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x)
        assert issues == [
            f"1:error:oelint.tools.broken:'broken' failed: {expected} [branch:true]",
            f"1:error:oelint.tools.brokenfmt:'brokenfmt' failed: {expected_fmt or expected} [branch:true]",
        ], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_tool_not_executable(self, input_):
        tools = {
            'broken': {
                'language': 'shell',
                'kind': 'linter',
                'command': [self._script('notexecutable', 'foo')],
                'output_regex': '^(?P<line>\\d+)$',
            },
        }
        issues = [x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x]
        assert len(issues) == 1 and "1:error:oelint.tools.broken:'broken' failed:" in issues[0] and "can't be run" in issues[0], issues

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                     \techo a
                                     \tif true; then
                                     \t\techo b
                                     \tfi
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_shell_formatter(self, input_):
        script = self._script('formatter.py', '''
            import re
            import sys
            sys.stdout.write(re.sub(r'\\t', '    ', sys.stdin.read()) + '\\n\\n')
            ''')
        tools = {
            'fmt': {
                'language': 'shell',
                'kind': 'formatter',
                'command': [sys.executable, script],
            },
        }
        self.check_for_id(self._create_args(input_, ['--tools-config', self._tools_config(tools)]), 'oelint.tools.fmt', 1)
        from oelint_adv.__main__ import run
        args = self._create_args_fix(input_, ['--tools-config', self._tools_config(tools)])
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == 'do_install() {\n    echo a\n    if true; then\n        echo b\n    fi\n}\n'

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     python do_foo() {
                                         bb.note("a")
                                     }
                                     ''',
                                 },
                             ],
                             )
    @pytest.mark.parametrize('language,output,expected',
                             [
                                 ('shell', 'garbage\\n', 'function header was changed'),
                                 ('shell', 'do_install() {\\n    echo a\\n', 'function end was changed'),
                                 ('shell', 'do_install() {\\n', 'function end was changed'),
                                 ('shell', 'do_install() {\\n}\\n', 'function body is empty'),
                                 ('shell', '', 'function header was changed'),
                                 ('python', 'garbage\\n', 'function header was changed'),
                                 ('python', '', 'function header was changed'),
                                 ('python', 'def do_foo(d):\\n    foo bar\\n', 'formatted code is not valid python'),
                             ],
                             )
    def test_formatter_bad_output(self, input_, language, output, expected):
        script = self._script('formatter.py', f'''
            import sys
            sys.stdin.read()
            sys.stdout.write('{output}')
            ''')
        tools = {
            'fmt': {
                'language': language,
                'kind': 'formatter',
                'command': [sys.executable, script],
            },
        }
        issues = [x.split(':', 1)[1] for x in self._issues(
            self._create_args(input_, ['--tools-config', self._tools_config(tools)])) if 'oelint.tools' in x]
        assert len(issues) == 1 and f"'fmt' failed: unexpected output: {expected}" in issues[0], issues

        # fixing leaves the file untouched
        from oelint_adv.__main__ import run
        args = self._create_args_fix(input_, ['--tools-config', self._tools_config(tools)])
        with open(args.files[0]) as i:
            before = i.read()
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == before

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_linter_no_fix(self, input_):
        script = self._script('linter.py', '''
            print('2:issue')
            ''')
        tools = {
            'lint': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
            },
        }
        from oelint_adv.__main__ import run
        args = self._create_args_fix(input_, ['--tools-config', self._tools_config(tools)])
        with open(args.files[0]) as i:
            before = i.read()
        run(args)
        with open(args.files[0]) as i:
            assert i.read() == before

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     A = "1"
                                     ''',
                                 },
                             ],
                             )
    def test_no_snippets(self, input_):
        tools = {
            'missing': {
                'language': 'python',
                'kind': 'linter',
                'command': ['oelint-adv-tool-does-not-exist'],
                'output_regex': '^(?P<line>\\d+)$',
            },
        }
        self.check_for_tool(self._create_args(input_, ['--tools-config', self._tools_config(tools)]), 'oelint.tools.missing', 0)

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     A = "1"
                                     ''',
                                 },
                             ],
                             )
    def test_config_errors(self, input_):
        import argparse
        with pytest.raises(argparse.ArgumentTypeError, match='is not a valid tools configuration'):
            self._create_args(input_, ['--tools-config', '/does/not/exist.json'])
        with pytest.raises(argparse.ArgumentTypeError, match="'language' is mandatory"):
            self._create_args(input_, ['--tools-config', self._tools_config({'foo': {'kind': 'linter', 'command': ['a']}})])

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     A = "1"
                                     ''',
                                 },
                             ],
                             )
    def test_config_file_option(self, input_):
        _config = self._tools_config({})
        _cstfile = self._create_tempfile('.oelint.cfg', '[oelint]\ntools-config=tools.json')
        os.environ['OELINT_CONFIG'] = _cstfile
        try:
            _args = self._create_args(input_)
        finally:
            del os.environ['OELINT_CONFIG']
        assert _args.tools_config == _config

    @pytest.mark.parametrize('input_',
                             [
                                 {
                                     'oelint_adv_test.bb':
                                     '''
                                     do_install() {
                                         echo a
                                     }
                                     ''',
                                 },
                             ],
                             )
    def test_cached(self, input_):
        script = self._script('linter.py', '''
            print('2:issue')
            ''')
        tools = {
            'lint': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
                'version_command': [sys.executable, '--version'],
            },
            'noversion': {
                'language': 'shell',
                'kind': 'linter',
                'command': [sys.executable, script],
                'output_regex': '^(?P<line>\\d+):(?P<message>.*)$',
            },
        }
        cachedir = os.path.join(self._tmpdir, 'cache')
        args = self._create_args(input_, ['--tools-config', self._tools_config(tools), '--cached', f'--cachedir={cachedir}'])
        self.check_for_id(args, 'oelint.tools.lint', 1)
        self.check_for_id(args, 'oelint.tools.noversion', 1)

    def test_lib_mode(self):
        from oelint_adv.core import create_lib_arguments, run
        _file = self._create_tempfile('oelint_adv_test.bb', '''
            do_install() {
                if [ "${A}" == "b" ]; then
                    echo a
                fi
            }
            ''')
        args = create_lib_arguments([_file], tools_config=EXAMPLE_CONFIG, quiet=True, jobs=1)
        issues, _ = run(args)
        assert any(':oelint.tools.shellcheck.SC3014:' in x[1] for x in issues), issues
