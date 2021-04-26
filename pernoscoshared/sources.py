from __future__ import annotations
from typing import Optional, List, Pattern, Callable, Tuple, Dict, TypedDict, Any, Mapping, cast, Union

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pernoscoshared.base as base

UrlGenerator = Callable[[str], Tuple[str, Optional[str]]]

class UrlMount(TypedDict, total=False):
    url: str
    at: str
    urlSuffix: str
class ArchiveMount(TypedDict):
    archive: str
    at: str
class LinkMount(TypedDict):
    link: str
    at: str
Mount = Union[UrlMount, ArchiveMount, LinkMount]

# Recursive type annotations aren't supported hence Any here
MountCondition = TypedDict("MountCondition", {'or': List[Any], 'binary': str, 'compilationUnit': str, 'build_id': str}, total=False)
class MountRule(TypedDict, total=False):
    condition: MountCondition
    priority: int
    files: List[Mount]
    relevance: str
    buildDir: str
    overrideCompDir: str

class ExternalDebugInfo(TypedDict):
    path: str
    build_id: str
    type: str
class Dwo(TypedDict):
    name: str
    full_path: str
    trace_file: str
    comp_dir: str
    id: int
Symlink = TypedDict("Symlink", {"from": str, "to": str})
class RrSources(TypedDict, total=False):
    relevant_binaries: List[str]
    comp_dir_substitutions: Mapping[str, str]
    external_debug_info: List[ExternalDebugInfo]
    dwos: List[Dwo]
    symlinks: List[Symlink]
    files: Mapping[str, List[str]]

# Known Mercurial hosts
mozilla_re: Pattern[str] = re.compile('https://hg.mozilla.org/(.*)')
sourceforge_re: Pattern[str] = re.compile('http://hg.code.sf.net/(.*)')

def hg_remote_url_to_source_url_generator(remote_url: str) -> Optional[UrlGenerator]:
    m = mozilla_re.match(remote_url)
    if m:
        if m.group(1) == 'try':
            # Ignore 'try' because it gets purged frequently
            return None
        mm = m # Capture so it can't change in the lambda
        return lambda rev: ("https://hg.mozilla.org/%s/raw-file/%s/"%(mm.group(1), rev), None)
    m = sourceforge_re.match(remote_url)
    if m:
        mm = m # Capture so it can't change in the lambda
        return lambda rev: ("https://sourceforge.net/%s/ci/%s/tree/"%(mm.group(1), rev), "?format=raw")
    return None

# Known Git hosts
github_re: Pattern[str] = re.compile('(https://github.com/|git@github.com:)([^/]+)/(.*)')
gitlab_re: Pattern[str] = re.compile('(https://gitlab.com/|git@gitlab.com:)([^/]+)/(.*)')
googlesource_re: Pattern[str] = re.compile('https://([^.]+.googlesource.com)/(.*)')

def strip(s: str, m: str) -> str:
    if s.endswith(m):
        return s[:(len(s) - len(m))]
    return s

def cinnabar_hg_rev(git_rev: str, repo_path: str) -> str:
    return base.check_output(['git', 'cinnabar', 'git2hg', git_rev], cwd=repo_path).decode('utf-8').split()[0]

def git_remote_url_to_source_url_generator(remote_url: str, repo_path: str) -> Optional[UrlGenerator]:
    m = github_re.match(remote_url)
    if m:
        # Capture so it can't change in the lambda
        mm = m
        return lambda rev: ("https://raw.githubusercontent.com/%s/%s/%s/"%(mm.group(2), strip(mm.group(3), ".git"), rev), None)
    m = gitlab_re.match(remote_url)
    if m:
        # Capture so it can't change in the lambda
        mm = m
        return lambda rev: ("https://gitlab.com/%s/%s/raw/%s/"%(mm.group(2), strip(mm.group(3), ".git"), rev), None)
    m = googlesource_re.match(remote_url)
    if m:
        # Capture so it can't change in the lambda
        mm = m
        # googlesource uses gitiles
        return lambda rev: ("https://%s/%s/+/%s/"%(mm.group(1), mm.group(2), rev), "?format=TEXT")
    if remote_url.startswith('hg::'):
        # Cinnabar Mercurial host
        hg = hg_remote_url_to_source_url_generator(remote_url[4:])
        if hg:
            # Capture so it can't change in the lambda
            hhg = hg
            return lambda rev: hhg(cinnabar_hg_rev(rev, repo_path))
    return None

# Returns a hash of remote names to generators of URLs Pernosco can use to fetch files
def git_remotes(repo_path: str) -> Dict[str, UrlGenerator]:
    output = base.check_output(['git', 'remote', '--verbose'], cwd=repo_path).decode('utf-8')
    ret = {}
    for line in output.splitlines():
        [remote, url, token] = line.split()[:3]
        if token != "(fetch)":
            continue
        url_generator = git_remote_url_to_source_url_generator(url, repo_path)
        if url_generator:
            ret[remote] = url_generator
    return ret

def git_find_rev(repo_path: str, remotes: Dict[str, UrlGenerator]) -> Optional[Tuple[str, str]]:
    git = base.Popen(['git', 'log', '--format=%H %D'],
                cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert git.stdout
    for line in git.stdout:
        revision = line.split()[0]
        for token in line.split():
            if b"/" in token:
                remote = token.split(b'/')[0].decode('utf-8')
                if remote in remotes:
                    git.kill()
                    git.wait()
                    return (revision.decode('utf-8'), remote)
    git.wait()
    return None

def git_committed_files(repo_path: str, revision: str, files: List[str]) -> Dict[str, bool]:
    h = {}
    for f in files:
        h[f] = True
    git = base.Popen(['git', 'diff', '--name-only', revision, 'HEAD'],
                cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ret = {}
    assert git.stdout
    for line in git.stdout:
        file = line.decode('utf-8').rstrip()
        if file in h:
            ret[file] = True
    git.wait()
    return ret

# Computes the files under repo_path that aren't fully committed to HEAD
# (i.e. ignored, untracked, modified in the working area, modified in the git index).
# returns the result as a hash-set.
def git_changed_files(repo_path: str, files: List[str]) -> Dict[str, bool]:
    h = {}
    for f in files:
        h[f] = True
    git = base.Popen(['git', 'status', '--untracked-files=all', '--ignored', '--short'],
                cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ret = {}
    assert git.stdout
    for line in git.stdout:
        line_str = line.decode('utf-8')
        if line_str.startswith("warning:"):
            continue
        if line_str[2] != ' ':
            raise base.CustomException("Unexpected line: %s"%line_str)
        file = line_str[3:].rstrip()
        if file in h:
            ret[file] = True
    git.wait()
    return ret

# XXX use TypeDict
def analyze_git_repo(repo_path: str, files: List[str]) -> Tuple[Optional[UrlMount], List[str]]:
    remotes = git_remotes(repo_path)
    if len(remotes) == 0:
        print("No remotes found for Git repo %s, packaging files instead..."%repo_path)
        return (None, files)
    r = git_find_rev(repo_path, remotes)
    if not r:
        print("Can't find usable remote master for Git repo %s, packaging files instead..."%repo_path)
        return (None, files)
    (revision, remote) = r
    (url, url_suffix) = remotes[remote](revision)
    print("Git repo at %s: Checking for source files changed since revision %s in remote %s (access via %s)..."%(repo_path, revision, remote, url), end="")
    # Collect files changed between `revision` and HEAD
    out_files = git_committed_files(repo_path, revision, files)
    # Collect files changed between HEAD and working dir
    changed_files = git_changed_files(repo_path, files)
    out_files_len = len(out_files)
    out_files.update(changed_files)
    if len(out_files) == 0:
        print(" no changes")
    else:
        print(" %d files with committed changes, %d files changed since HEAD, %d overall"%(out_files_len, len(changed_files), len(out_files)))
    mount: UrlMount = {'url': url, 'at': repo_path}
    if url_suffix:
         mount['urlSuffix'] = url_suffix
    return (mount, list(out_files.keys()))

def safe_env() -> Dict[str, str]:
    return dict(os.environ, HGPLAIN='1')

# Returns a hash of remote names to generators of URLs Pernosco can use to fetch files
def hg_remotes(repo_path: str) -> Dict[str, UrlGenerator]:
    output = base.check_output(['hg', 'paths'], cwd=repo_path, env=safe_env()).decode('utf-8')
    ret = {}
    for line in output.splitlines():
        [remote, equals, url] = line.split()[:3]
        url_generator = hg_remote_url_to_source_url_generator(url)
        if url_generator:
            ret[remote] = url_generator
    return ret

def hg_find_rev(repo_path: str, remotes: Dict[str, UrlGenerator]) -> Optional[Tuple[str, str]]:
    best_rev_num = -1
    best_sha = None
    best_remote = None
    for r in remotes:
        output = base.check_output(['hg', 'log', '-T', '{rev} {node}', '-r', "ancestor((parents(outgoing('%s') & ancestors(.))) | .)"%r],
                              cwd=repo_path, env=safe_env()).decode('utf-8')
        [rev_num, sha] = output.split()[:2]
        rev_int = int(rev_num)
        if rev_int > best_rev_num:
            best_rev_num = rev_int
            best_sha = sha
            best_remote = r
    if not best_sha or not best_remote:
        return None
    return (best_sha, best_remote)

def hg_changed_files(repo_path: str, revision: str, files: List[str]) -> Dict[str, bool]:
    h = {}
    for f in files:
        h[f] = True
    hg = base.Popen(['hg', 'status', '-nmaui', '--rev', revision],
               cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=safe_env())
    ret = {}
    assert hg.stdout
    for line in hg.stdout:
        file = line.decode('utf-8').rstrip()
        if file in h:
            ret[file] = True
    hg.wait()
    return ret

def analyze_hg_repo(repo_path: str, files: List[str]) -> Tuple[Optional[UrlMount], List[str]]:
    remotes = hg_remotes(repo_path)
    if len(remotes) == 0:
        print("No remotes found for Mercurial repo %s, packaging files instead..."%repo_path)
        return (None, files)
    r = hg_find_rev(repo_path, remotes)
    if not r:
        print("Can't find usable remote master for Mercurial repo %s, packaging files instead..."%repo_path)
        return (None, files)
    (revision, remote) = r
    (url, url_suffix) = remotes[remote](revision)
    print("Mercurial repo at %s: Checking for source files changed since revision %s in remote '%s' (access via %s)..."%(repo_path, revision, remote, url), end="")
    # Collect files changed between `revision` and HEAD
    out_files = hg_changed_files(repo_path, revision, files)
    if len(out_files) == 0:
        print(" no changes")
    else:
        print(" %d files changed"%len(out_files))
    mount: UrlMount = {'url': url, 'at': repo_path}
    if url_suffix:
         mount['urlSuffix'] = url_suffix
    return (mount, list(out_files.keys()))

def analyze_repo(repo_path: str, files: List[str]) -> Tuple[Optional[UrlMount], List[str]]:
    # This could be a plain file for a git submodule
    if os.path.exists(os.path.join(repo_path, ".git")):
        return analyze_git_repo(repo_path, files)
    if os.path.isdir(os.path.join(repo_path, ".hg")):
        return analyze_hg_repo(repo_path, files)
    return (None, files)

def allowed_file(source_dirs: List[str], file: str) -> bool:
    for f in source_dirs:
        if file.startswith(f):
            return True
    return False

def run_rr_sources(comp_dir_substitutions: Dict[str, str], cmd: str, params: List[str]) -> RrSources:
    print("Obtaining source file list...")
    rr_comp_dir_substitutions = []
    for k in comp_dir_substitutions:
        rr_comp_dir_substitutions.append("--substitute")
        rr_comp_dir_substitutions.append("%s=%s"%(k, comp_dir_substitutions[k]))
    try:
        rr_output = base.check_output(['rr', cmd] + rr_comp_dir_substitutions + params).decode('utf-8')
    except subprocess.CalledProcessError as x:
        if len(rr_comp_dir_substitutions) > 0:
            print("Error while running rr sources; your installed version of rr may not be new enough to support the --substitute option.")
        else:
            print("Unknown error while running rr sources, aborting")
        sys.exit(1)
    return cast(RrSources, json.loads(rr_output))

def package_source_files(source_dirs: List[str], comp_dir_substitutions: Dict[str, str]) -> List[str]:
    assert base.trace_dir
    rr_sources = run_rr_sources(comp_dir_substitutions, 'sources', [base.trace_dir])
    return package_source_files_from_rr_output(source_dirs, rr_sources, comp_dir_substitutions, base.trace_dir, "user", "binary")

# Package external debuginfo files and DWOs into the trace. Does not put them
# in the right place for gdb to find them, yet, but Pernosco will find them.
def package_debuginfo_files() -> None:
    assert base.trace_dir
    rr_sources = run_rr_sources({}, 'sources', [base.trace_dir])
    package_debuginfo_from_sources_json(rr_sources, base.trace_dir)

def package_debuginfo_from_sources_json(rr_sources: RrSources, output_dir: str) -> None:
    if 'dwos' in rr_sources:
        dir = "%s/debug/.dwo/"%output_dir
        for d in rr_sources['dwos']:
            if 'full_path' in d:
                path = d['full_path']
            else:
                path = os.path.join(d['comp_dir'], d['name'])
            if os.path.isfile(path):
                dst = "{0:s}/{1:0{2}x}.dwo".format(dir, d['id'], 16)
                base.copy_replace_file(path, dst)
            else:
                print("Can't find DWO file %s, skipping"%path, file=sys.stderr)

    # Copy external debuginfo into place
    if 'external_debug_info' in rr_sources:
        for e in rr_sources['external_debug_info']:
            build_id = e['build_id']
            dir = "%s/debug/.build-id/%s"%(output_dir, build_id[:2])
            t = e['type']
            if t == 'debuglink':
                ext = "debug"
            elif t == 'debugaltlink':
                ext = "sup"
            else:
                print("Unknown type '%s' from 'rr sources': is this script out of date? Aborting.", file=sys.stderr)
                sys.exit(1)
            dst = "%s/%s.%s"%(dir, build_id[2:], ext)
            base.copy_replace_file(e['path'], dst)

def package_source_files_from_rr_output(source_dirs: List[str], rr_sources: RrSources,
      comp_dir_substitutions: Dict[str, str], output_dir: str, tag: str, condition_type: str, build_dir: Optional[str]=None) -> List[str]:
    package_debuginfo_from_sources_json(rr_sources, output_dir)

    out_sources: MountRule = {};
    out_placeholders: MountRule = {};
    or_condition = [];
    for b in rr_sources['relevant_binaries']:
        or_condition.append({condition_type:b})
    out_sources['condition'] = {'or': or_condition}
    out_placeholders['condition'] = {'or': or_condition}
    explicit_files = []
    out_mounts: List[Mount] = []
    out_placeholder_mounts: List[Mount] = []
    repo_paths = []
    non_repo_files_count = 0;
    # Mount repos
    for repo_path in rr_sources['files']:
        files = rr_sources['files'][repo_path]
        if repo_path == '':
            non_repo_files_count = len(files)
            explicit_files.extend(files)
            continue
        repo_paths.append(repo_path)
        (repo_mount, modified_files) = analyze_repo(repo_path, files)
        for m in modified_files:
            explicit_files.append(os.path.join(repo_path, m))
        if not repo_mount:
            continue
        out_mounts.append(repo_mount)
    # Install non-repo files
    print("Packaging %d modified and %d non-repository files..."%(len(explicit_files) - non_repo_files_count, non_repo_files_count))

    with zipfile.ZipFile('%s/files.%s/sources.zip'%(output_dir, tag), mode='w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        for f in explicit_files:
            if allowed_file(source_dirs, f):
                # Don't call zip_file.write(f) since that tries to preserve timestamps,
                # which fails for timestamps before 1980
                with open(f, "rb") as file:
                    zip_file.writestr(f, file.read())
    disallowed_file_count = 0
    with zipfile.ZipFile('%s/files.%s/sources-placeholders.zip'%(output_dir, tag), mode='w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        for f in explicit_files:
            if not allowed_file(source_dirs, f):
                content = ("/* This file was not uploaded because the path %s is not under the allowed directories [%s] */"%
                    (f, ", ".join(['"%s"'%d for d in source_dirs])))
                zip_file.writestr(f, content)
                if not ("/.cargo/registry/src/" in f):
                    disallowed_file_count += 1
                    if disallowed_file_count <= 10:
                        print("Not uploading source file %s (add an allowed source directory to the command line?)"%f)
                    if disallowed_file_count == 11:
                        print("(too many disallowed-source-file warnings, suppressing the rest)")
    out_mounts.append({'archive': 'files.%s/sources.zip'%tag, 'at': '/'})
    out_placeholder_mounts.append({'archive': 'files.%s/sources-placeholders.zip'%tag, 'at': '/'})
    # Add symlinks
    for s in rr_sources['symlinks']:
        # A symlink at 'from' points to the file at 'to'. So, we want to create
        # a symlink *at* 'from' which is *links* to 'to'.
        out_mounts.append({'link': s['to'], 'at': s['from']})
    # Dump output
    if build_dir:
        out_sources['buildDir'] = build_dir
    out_sources['files'] = out_mounts
    out_sources['relevance'] = 'Relevant'
    out_placeholders['files'] = out_placeholder_mounts
    out_placeholders['relevance'] = 'NotRelevant'
    out_placeholders['priority'] = 1000

    all_rules = [out_sources, out_placeholders]
    if len(comp_dir_substitutions) > 0:
        if 'comp_dir_substitutions' in rr_sources:
            substitutions = rr_sources['comp_dir_substitutions']
            for sub in substitutions:
                out_substitution: MountRule = {}
                out_substitution['condition'] = cast(MountCondition, {condition_type: sub});
                out_substitution['overrideCompDir'] = substitutions[sub];
                all_rules.append(out_substitution)

    with open('%s/sources.%s'%(output_dir, tag), "wt") as out_f:
        json.dump(all_rules, out_f, indent=2)
    return repo_paths

# The files under these paths are copied into gdbinit/
gdb_paths: List[str] = [
    # Mozilla
    '.gdbinit',
    '.gdbinit_python',
    'third_party/python/gdbpp',
    # Chromium
    'tools/gdb',
    'third_party/libcxx-pretty-printers',
    'third_party/blink/tools/gdb',
]

def package_gdbinit(repo_paths: List[str], out_dir: str) -> None:
    shutil.rmtree(out_dir, ignore_errors=True)
    gdbinit_sub_paths = []
    for repo in repo_paths:
        sub_path = repo.replace("/", "_");
        for g in gdb_paths:
            path = os.path.join(repo, g)
            out_path = "%s/%s/%s"%(out_dir, sub_path, g)
            if os.path.isfile(path):
                print("Copying file %s into trace"%path)
                base.copy_replace_file(path, out_path)
            elif os.path.isdir(path):
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                print("Copying tree %s into trace"%path)
                shutil.copytree(path, out_path, copy_function=base.copy_replace_file)
        # Install our own Pernosco-compatible .gdbinit for Chromium
        if os.path.isfile("%s/%s/tools/gdb/gdb_chrome.py"%(out_dir, sub_path)):
            with open("%s/%s/.gdbinit"%(out_dir, sub_path), "wt") as f:
                f.write("""python
import sys
sys.path.insert(0, "/trace/gdbinit/%s/tools/gdb/")
sys.path.insert(0, "/trace/gdbinit/%s/third-party/libcxx-pretty-printers/")
import gdb_chrome
from libcxx.v1.printers import register_libcxx_printers
register_libcxx_printers(None)
gdb.execute('source /trace/gdbinit/%s/tools/gdb/viewg.gdb')
end
"""%(sub_path, sub_path, sub_path))
        if os.path.isfile("%s/%s/.gdbinit"%(out_dir, sub_path)):
            gdbinit_sub_paths.append(sub_path)
    if len(gdbinit_sub_paths) > 0:
        with open("%s/.gdbinit"%out_dir, "wt") as f:
            for sub_path in gdbinit_sub_paths:
                print("directory /trace/gdbinit/%s"%sub_path, file=f)
                print("source /trace/gdbinit/%s/.gdbinit"%sub_path, file=f)
