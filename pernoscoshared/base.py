from __future__ import annotations
from typing import Dict, Optional, List, IO, Union, Any, Mapping, TYPE_CHECKING

import os
import shutil
import subprocess
import sys

if TYPE_CHECKING:
    StrPath = Union[str, os.PathLike[str]]
else:
    StrPath = Union[str, os.PathLike]

class CustomException(Exception):
    pass

trace_dir: Optional[str] = None
echo_commands: bool = False

def maybe_echo(cmd: List[str]) -> None:
    if echo_commands:
        print(" ".join(cmd), file=sys.stderr)

# Given a complete source path and a complete destination path,
# replaces the destination with a copy of the source.
def copy_replace_file(src: StrPath, dst: str) -> None:
    try:
        os.remove(dst)
    except:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        pass
    shutil.copyfile(src, dst)

def check_output(process_args: List[str], cwd: Optional[str] = None, close_fds: bool=True,
        env: Optional[Mapping[str, str]] = None, stdin: Union[None, int, IO[Any]] = None,
        stderr: Union[None, int, IO[Any]] = None, input: bytes = b"") -> bytes:
    if echo_commands:
        print("Running %s"%(" ".join(process_args)))
    input_arg: Dict[str, Any] = dict()
    if len(input) != 0:
        input_arg["input"] = input
    else:
        input_arg["stdin"] = stdin
    output: bytes = subprocess.check_output(process_args, cwd=cwd, close_fds=close_fds, env=env, stderr=stderr, **input_arg)
    return output

def call(process_args: List[str], cwd: Optional[str] = None, close_fds: bool=True,
        env: Optional[Mapping[str, str]] = None, stdin: Union[None, int, IO[Any]] = None,
        stdout: Union[None, int, IO[Any]] = None, stderr: Union[None, int, IO[Any]] = None) -> int:
    if echo_commands:
        print("Running %s"%(" ".join(process_args)))
    return subprocess.call(process_args, cwd=cwd, close_fds=close_fds, env=env, stdin=stdin, stdout=stdout, stderr=stderr)

def check_call(process_args: List[str], cwd: Optional[str] = None, close_fds: bool=True,
        env: Optional[Mapping[str, str]] = None, stdin: Union[None, int, IO[Any]] = None,
        stdout: Union[None, int, IO[Any]] = None, stderr: Union[None, int, IO[Any]] = None) -> int:
    if echo_commands:
        print("Running %s"%(" ".join(process_args)))
    return subprocess.check_call(process_args, cwd=cwd, close_fds=close_fds, env=env, stdin=stdin, stdout=stdout, stderr=stderr)

def Popen(process_args: List[str], cwd: Optional[str] = None, close_fds: bool=True,
        env: Optional[Mapping[str, str]] = None, stdin: Union[None, int, IO[Any]] = None,
        stdout: Union[None, int, IO[Any]] = None, stderr: Union[None, int, IO[Any]] = None) -> subprocess.Popen[bytes]:
    if echo_commands:
        print("Running %s"%(" ".join(process_args)))
    return subprocess.Popen(process_args, cwd=cwd, close_fds=close_fds, env=env, stdin=stdin, stdout=stdout, stderr=stderr)
