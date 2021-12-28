from __future__ import annotations
from typing import Optional, List, Pattern, Callable, Tuple, Dict, TypedDict, Any, Mapping, cast, Union

import glob
import json
import lzma
import os
import shutil
import subprocess

import pernoscoshared.base as base

class TraceOverlayManifest(TypedDict, total=False):
    overlays: Mapping[str, List[str]]

def collect_candidate_build_ids() -> Mapping[str, bool]:
    assert base.trace_dir
    names = []
    for binary in glob.glob("%s/mmap_*"%base.trace_dir):
        names.append("%s\n"%binary)
    build_id_text = base.check_output(['rr', 'buildid'], input="".join(names).encode('utf-8')).decode('utf-8')
    ret = {}
    for build_id in build_id_text.split("\n"):
        if len(build_id) == 0:
            continue
        ret[build_id] = True
    return ret

# resource is, e.g., trace-overlay.manifest.xz
def debuginfo_resource_reader(overlays_path: str, resource: str) -> subprocess.Popen[bytes]:
    cmd = []
    if overlays_path.startswith("s3://"):
        cmd = ["aws", "s3", "cp", "%s/%s"%(overlays_path, resource), "-"]
    else:
        cmd = ["cat", "%s/%s"%(overlays_path, resource)]
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)

def read_manifest(overlays_path: str) -> TraceOverlayManifest:
    with debuginfo_resource_reader(overlays_path, "trace-overlay.manifest.xz") as xz_reader:
        with lzma.LZMAFile(xz_reader.stdout) as reader:
            return cast(TraceOverlayManifest, json.load(reader))

def apply_overlay(overlays_path: str, overlay: str) -> None:
    assert base.trace_dir
    with debuginfo_resource_reader(overlays_path, overlay) as xz_reader:
        with subprocess.Popen(["tar", "-Jxf", "-"], cwd=base.trace_dir, stdin=xz_reader.stdout) as tar_proc:
            tar_proc.communicate()

# overlays_path is either an S3 bucket path, e.g. "s3://pernosco-system-debuginfo-overlays",
# or a filesystem path containing a similar set of files, i.e.
# a trace-overlay.manifest.xz containing a json-encoded map from overlay name to list of
# build-ids, and for each overlay name, a .tar.xz to be expanded into the trace directory.
def apply_system_debuginfo(overlays_path: str, build_ids: Mapping[str, bool]) -> None:
    assert base.trace_dir
    if len(build_ids) == 0:
        return
    manifest = read_manifest(overlays_path)
    overlays = {}
    for key, value in manifest['overlays'].items():
        for v in value:
            if v in build_ids:
                overlays[key] = True
    # Do things deterministically to make bugs more reproducible
    for o in sorted(overlays):
        apply_overlay(overlays_path, o)
