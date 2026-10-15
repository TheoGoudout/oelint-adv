# Type stubs for the bitbake 'bb' module, as available to python code in bitbake files
import logging
from typing import Any, Callable, NamedTuple, NoReturn, TypeVar

from bb import acl as acl
from bb import asyncrpc as asyncrpc
from bb import build as build
from bb import cache as cache
from bb import cache_extra as cache_extra
from bb import checksum as checksum
from bb import codeparser as codeparser
from bb import command as command
from bb import compress as compress
from bb import cooker as cooker
from bb import cookerdata as cookerdata
from bb import COW as COW
from bb import daemonize as daemonize
from bb import data as data
from bb import data_smart as data_smart
from bb import event as event
from bb import fetch as fetch
from bb import fetch2 as fetch2
from bb import filter as filter
from bb import methodpool as methodpool
from bb import monitordisk as monitordisk
from bb import msg as msg
from bb import parse as parse
from bb import process as process
from bb import progress as progress
from bb import providers as providers
from bb import remotedata as remotedata
from bb import runqueue as runqueue
from bb import server as server
from bb import siggen as siggen
from bb import taskdata as taskdata
from bb import tinfoil as tinfoil
from bb import ui as ui
from bb import utils as utils
from bb import xattr as xattr

_F = TypeVar('_F', bound=Callable[..., Any])

__version__: str

class BBHandledException(Exception): ...

logger: logging.Logger
mainlogger: logging.Logger

def plain(*args: str) -> None: ...
def debug(lvl: int, *args: str) -> None: ...
def note(*args: str) -> None: ...
def verbnote(*args: str) -> None: ...
def warn(*args: str) -> None: ...
def warnonce(*args: str) -> None: ...
def error(*args: str, **kwargs: Any) -> None: ...
def erroronce(*args: str) -> None: ...
def fatal(*args: str, **kwargs: Any) -> NoReturn: ...
def deprecated(func: _F, name: str | None = ..., advice: str = ...) -> _F: ...

class TaskData(NamedTuple):
    pn: str
    taskname: str
    fn: str
    deps: Any
    provides: Any
    taskhash: str
    unihash: str
    hashfn: str
    taskhash_deps: Any
