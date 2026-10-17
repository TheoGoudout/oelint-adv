# Type stubs for oe.data
from typing import Any

from bb.data_smart import DataSmart

def typed_value(key: str, d: DataSmart) -> Any: ...
def export2json(d: DataSmart, json_file: str, expand: bool = ..., searchString: str = ...,
                replaceString: str = ...) -> None: ...
