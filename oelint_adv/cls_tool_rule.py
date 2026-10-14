from typing import List

from oelint_parser.cls_stash import Stash

from oelint_adv.cls_rule import Rule
from oelint_adv.embedded import (
    Snippet,
    ToolError,
    filter_snippets,
    format_snippet,
    get_snippets,
    lint,
)
from oelint_adv.state import State
from oelint_adv.tools_config import ToolConfig


class ToolRule(Rule):
    """Rule running an external tool, as defined in the tools configuration, on embedded code"""

    PREFIX = 'oelint.tools.'

    def __init__(self, tool: ToolConfig) -> None:
        super().__init__(id=f'{ToolRule.PREFIX}{tool.name}',
                         severity=tool.severity,
                         message=f"{tool.language} code is not formatted according to '{tool.name}'"
                         if tool.kind == 'formatter' else f"'{tool.name}' reported an issue")
        self._tool = tool

    def bind(self, state: State) -> None:
        """Bind the rule to the state and make sub IDs of the rulefile known

        Args:
            state (State): Current state object
        """
        self._state = state
        _prefix = f'{self.ID}.'
        self.Appendix = sorted(x[len(_prefix):] for x in state.get_rulefile() if x.startswith(_prefix))

    def _snippets(self, _file: str, stash: Stash) -> List[Snippet]:
        return filter_snippets(get_snippets(stash, _file, self._tool.language), self._tool)

    def _finding(self, snippet: Snippet, line: int, message: str, severity: str, appendix: str = None) -> List[Rule.Finding]:
        # tool findings come with their own severity, which is used whenever
        # the rulefile doesn't define one
        _base = self.Severity
        self.Severity = severity
        try:
            return self.finding(snippet.origin, line, override_msg=message, appendix=appendix or None,
                                blockoffset=snippet.header_line)
        finally:
            self.Severity = _base

    def _error(self, snippet: Snippet, error: str) -> List[Rule.Finding]:
        return self._finding(snippet, snippet.header_line, f"'{self._tool.name}' failed: {error}", 'error')

    def check(self, _file: str, stash: Stash) -> List[Rule.Finding]:
        res = []
        snippets = self._snippets(_file, stash)
        if self._tool.kind == 'linter':
            findings, errors = lint(self._tool, snippets, _file)
            for snippet, error in errors:
                res += self._error(snippet, error)
            for item in findings:
                res += self._finding(item.snippet, item.line, item.message, item.severity, appendix=item.code)
            return res
        for snippet in snippets:
            try:
                body = format_snippet(self._tool, snippet, _file)
            except ToolError as e:
                res += self._error(snippet, str(e))
                continue
            if body is not None and body != snippet.body:
                res += self._finding(snippet, snippet.header_line, self.Msg, self.Severity)
        return res

    def fix(self, _file: str, stash: Stash) -> List[str]:
        res = []
        if self._tool.kind != 'formatter':
            return res
        for snippet in self._snippets(_file, stash):
            try:
                body = format_snippet(self._tool, snippet, _file)
            except ToolError:
                # reported by check
                continue
            if body is None or body == snippet.body:
                continue
            snippet.item.RealRaw = snippet.header + body + snippet.footer
            snippet.item.Raw = snippet.item.RealRaw
            res.append(_file)
        return res


def create_tool_rules(state: State) -> List[ToolRule]:
    """Create rules for all configured tools

    Args:
        state (State): Current state object

    Returns:
        List[ToolRule]: rules
    """
    res = []
    _rule_file = state.get_rulefile()
    for tool in state.tools:
        rule = ToolRule(tool)
        rule.bind(state)
        if _rule_file and not any(x in _rule_file for x in rule.get_ids()):
            continue
        res.append(rule)
    return res
