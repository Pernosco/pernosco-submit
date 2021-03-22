import glob
import os
import shutil

import pernoscoshared.base as base

def rr_pack():
    print("Running 'rr pack'...")
    base.check_call(['rr', 'pack', base.trace_dir])

def package_libthread_db():
    for f in ['/usr/lib64/libthread_db.so',
              '/usr/lib/x86_64-linux-gnu/libthread_db.so']:
        if os.path.isfile(f):
            print("Copying %s into trace..."%f)
            base.copy_replace_file(f, '%s/files.system-debuginfo/libthread_db.so'%base.trace_dir)
            break

def package_extra_rr_trace_files():
    extra_file_dirs = dict()
    for binary in glob.glob("%s/mmap_*"%base.trace_dir):
        original_file_names = base.check_output(['rr', 'filename', binary])
        for name in original_file_names.splitlines():
            extra_files_path = b"%s/extra_rr_trace_files"%os.path.dirname(name)
            if os.path.isdir(extra_files_path):
                extra_file_dirs[extra_files_path] = True
    dir_list = list(extra_file_dirs.keys())
    dir_list.sort()
    for d in dir_list:
        for f in os.listdir(d):
            src_name = os.path.join(d, f)
            dest_name = os.path.join(base.trace_dir.encode('utf-8'), f)
            if os.path.isfile(src_name):
                base.copy_replace_file(src_name, dest_name)
            else:
                shutil.copytree(src_name, dest_name)
