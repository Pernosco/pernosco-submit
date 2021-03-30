from __future__ import annotations
from typing import Optional, List, IO, Union, Any, Mapping, Dict

import glob
import os
import shutil

import pernoscoshared.base as base

def rr_pack() -> None:
    print("Running 'rr pack'...")
    assert base.trace_dir
    base.check_call(['rr', 'pack', base.trace_dir])

def package_libthread_db() -> None:
    for f in ['/usr/lib64/libthread_db.so',
              '/usr/lib/x86_64-linux-gnu/libthread_db.so']:
        if os.path.isfile(f):
            print("Copying %s into trace..."%f)
            dest = '%s/files.system-debuginfo/libthread_db.so'%base.trace_dir
            base.copy_replace_file(f, dest)
            # Make sure it's world-readable so containers can read it
            os.chmod(dest, 0o555)
            break

def package_extra_rr_trace_files() -> None:
    extra_file_dirs: Dict[str, bool] = dict()
    assert base.trace_dir
    for binary in glob.glob("%s/mmap_*"%base.trace_dir):
        original_file_names = base.check_output(['rr', 'filename', binary])
        for name in original_file_names.splitlines():
            extra_files_path = b"%s/extra_rr_trace_files"%os.path.dirname(name)
            if os.path.isdir(extra_files_path):
                extra_file_dirs[extra_files_path.decode('utf-8')] = True
    dir_list = list(extra_file_dirs.keys())
    dir_list.sort()
    for d in dir_list:
        for f in os.listdir(d):
            src_name = os.path.join(d, f)
            dest_name = os.path.join(base.trace_dir, f)
            if os.path.isfile(src_name):
                base.copy_replace_file(src_name, dest_name)
            else:
                shutil.copytree(src_name, dest_name)
