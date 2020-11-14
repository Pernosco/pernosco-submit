#!/usr/bin/env python3

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

# Installation requirements (all on $PATH):
# -- latest rr
# -- git
# -- hg
# -- git-cinnabar: https://github.com/glandium/git-cinnabar
#
# Run from the pernosco-submit repo directory.

tmpdir = tempfile.mkdtemp()
print("Working directory: %s"%tmpdir)
trace_dir = None
next_trace_id = 0

clean_env = dict(os.environ, _RR_TRACE_DIR=tmpdir)
clean_env.pop('PERNOSCO_USER_SECRET_KEY', None)
clean_env.pop('AWS_SECRET_ACCESS_KEY', None)
clean_env.pop('SSHPASS', None)

# Test keygen and get some keys for us to use
output = subprocess.check_output(["./pernosco-submit", "keygen", "FAKE_KEY_ID,FAKE_CRED"], encoding='utf-8').split()
private_key = output[2].split('=', 1)[1]
public_key = output[5]

def make_changes():
    with open("%s/main.c"%testdir, "a") as f:
        print("/* EXTRA JUNK */", file=f)

def build():
    subprocess.check_call(['./build.sh'], cwd=testdir)

def create_extra_rr_trace_files():
    os.makedirs("%s/out/extra_rr_trace_files/files.extra"%testdir)
    with open("%s/out/extra_rr_trace_files/files.extra/data"%testdir, "w") as f:
        f.write("Hello kitty")

def record(env):
    global trace_dir
    global next_trace_id
    # Create clean environment with no secret keys that pernosco-submit would reject
    subprocess.check_call(['rr', 'record', '%s/out/main'%testdir], env=env)
    trace_dir = "%s/main-%d"%(tmpdir, next_trace_id)
    next_trace_id += 1

def submit_dry_run(title='FAKE TITLE', url='FAKE_ñ_URL'):
    upload_env = dict(clean_env, PERNOSCO_USER='pernosco-submit-test@pernos.co',
                      PERNOSCO_GROUP='pernosco-submit-test',
                      PERNOSCO_USER_SECRET_KEY=private_key)
    cmd = ['./pernosco-submit', 'upload', '--dry-run', '%s/dry-run'%tmpdir, '--consent-to-current-privacy-policy']
    if title:
        cmd.extend(['--title', title])
    if url:
        cmd.extend(['--url', url])
    cmd.extend([trace_dir, tmpdir])
    return subprocess.run(cmd, env=upload_env)

def validate_dry_run(title="FAKE%20TITLE", url="FAKE_%C3%B1_URL"):
    with open('%s/dry-run.cmd'%tmpdir) as f:
        cmd_obj = json.loads(f.read())
    aws_cmd = cmd_obj['aws_cmd']
    assert aws_cmd[0] == 'aws'
    assert aws_cmd[1] == 's3'
    assert aws_cmd[2] == 'cp'
    assert aws_cmd[3] == '--metadata'
    metadata = aws_cmd[4].split(',')
    assert metadata[0] == "publickey=%s"%public_key
    assert metadata[1].startswith("signature=")
    assert metadata[2] == "user=pernosco-submit-test@pernos.co"
    assert metadata[3] == "group=pernosco-submit-test"
    expect_metadata_len = 4
    if title != None:
        assert metadata[expect_metadata_len] == "title=%s"%title
        expect_metadata_len += 1
    if url != None:
        assert metadata[expect_metadata_len] == "url=%s"%url
        expect_metadata_len += 1
    assert len(metadata) == expect_metadata_len
    assert not os.path.exists(aws_cmd[5]) # temp file should have been cleaned up
    assert aws_cmd[6].startswith("s3://pernosco-upload/")
    assert aws_cmd[6].endswith(".tar.zst")
    aws_env = cmd_obj['aws_env']
    assert aws_env['AWS_DEFAULT_REGION'] == 'us-east-2'
    assert aws_env['AWS_ACCESS_KEY_ID'] == 'FAKE_KEY_ID'
    assert aws_env['AWS_SECRET_ACCESS_KEY'] == 'FAKE_CRED'

def validate_producer_metadata(title='FAKE TITLE', url='FAKE_ñ_URL'):
    with open('%s/producer-metadata'%trace_dir) as f:
        producer_metadata = json.loads(f.read())
    assert producer_metadata.get('title') == title
    assert producer_metadata.get('url') == url

def validate_files_user():
    with open('%s/files.user/user'%trace_dir) as f:
        assert f.read().strip() == "pernosco-submit-test@pernos.co"
    with open('%s/files.user/group'%trace_dir) as f:
        assert f.read().strip() == "pernosco-submit-test"

def validate_extra_rr_trace_files():
    assert os.path.exists("%s/files.extra/data"%trace_dir)

def validate_sources_user(repo_url, repo_url_suffix):
    with open('%s/sources.user'%trace_dir) as f:
        files_user = json.loads(f.read())
    or_condition = files_user[0]['condition']['or']
    assert len(or_condition) == 2
    assert any(map(lambda x: x['binary'].endswith('librrpreload.so'), or_condition))
    assert any(map(lambda x: x['binary'].endswith('main'), or_condition))
    files = files_user[0]['files']
    assert len(files) == 4
    assert any(map(lambda x: x.get('url') == repo_url and x['at'] == testdir and x.get('urlSuffix') == repo_url_suffix, files))
    assert any(map(lambda x: x.get('url') and x['url'].startswith('https://raw.githubusercontent.com/rr-debugger/rr/'), files))
    assert any(map(lambda x: x.get('archive') == 'files.user/sources.zip' and x['at'] == '/', files))
    assert any(map(lambda x: x.get('link') == '%s/file.c'%testdir and x['at'] == '%s/out/file.c'%testdir, files))
    assert files_user[0]['relevance'] == 'Relevant'

def build_id_for(file):
    try:
        output = subprocess.check_output(["readelf", "-n", file], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        return None
    m = re.search(b"Build ID: ([0-9a0-f]+)", output)
    if m:
        return m.group(1).decode('utf-8')
    return None

def validate_sources_extra(extra_part, repo_url, repo_url_suffix):
    with open('%s/extra_rr_trace_files/sources.%s'%(tmpdir, extra_part)) as f:
        files_user = json.loads(f.read())
    or_condition = files_user[0]['condition']['or']
    assert len(or_condition) == 1
    assert or_condition[0]['buildid'] == build_id_for("%s/out/main"%testdir)
    assert files_user[0]['buildDir'] == testdir
    files = files_user[0]['files']
    assert len(files) == 3
    assert any(map(lambda x: x.get('url') == repo_url and x['at'] == testdir and x.get('urlSuffix') == repo_url_suffix, files))
    assert any(map(lambda x: x.get('archive') == 'files.%s/sources.zip'%extra_part and x['at'] == '/', files))
    assert any(map(lambda x: x.get('link') == '%s/file.c'%testdir and x['at'] == '%s/out/file.c'%testdir, files))
    assert files_user[0]['relevance'] == 'Relevant'

def validate_sources_zip():
    validate_sources_zip_path('%s/files.user/sources.zip'%trace_dir)

def validate_sources_extra_zip(extra_part):
    validate_sources_zip_path('%s/extra_rr_trace_files/files.%s/sources.zip'%(tmpdir, extra_part))

def validate_sources_zip_path(path):
    sources_zip = zipfile.ZipFile(path)
    sources_zip.getinfo('%s/out/message.h'%testdir[1:])
    sources_zip.getinfo('%s/main.c'%testdir[1:])
    try:
        sources_zip.getinfo('usr/include/stdio.h')
        assert False
    except KeyError:
        pass

def validate_libthread_db():
    assert os.path.exists('%s/files.system-debuginfo/libthread_db.so'%trace_dir)

def validate_external_debuginfo():
    debug_roots = list(os.listdir('%s/debug/.build-id'%trace_dir))
    assert len(debug_roots) == 1
    debugs = list(os.listdir('%s/debug/.build-id/%s'%(trace_dir, debug_roots[0])))
    assert len(debugs) == 1
    assert debugs[0].endswith(".debug")

def validate_dwos():
    dwos = list(os.listdir('%s/debug/.dwo'%trace_dir))
    assert len(dwos) == 2
    for f in dwos:
        assert f.endswith(".dwo")

print("\nTesting Github checkout...")

pernosco_submit_test_git_revision = '84861f84a7462c2b4e04b7b41f7f83616c83c8dc'
subprocess.check_call(['git', 'clone', 'https://github.com/Pernosco/pernosco-submit-test'], cwd=tmpdir)
testdir = "%s/pernosco-submit-test"%tmpdir
subprocess.check_call(['git', 'checkout', '-q', pernosco_submit_test_git_revision], cwd=testdir)
make_changes()
build()
create_extra_rr_trace_files()
record(clean_env)
assert submit_dry_run().returncode == 0
validate_dry_run()
validate_producer_metadata()
validate_files_user()
validate_extra_rr_trace_files()
github_raw_url = 'https://raw.githubusercontent.com/Pernosco/pernosco-submit-test/%s/'%pernosco_submit_test_git_revision
validate_sources_user(github_raw_url, None)
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()

# Check pernosco-submit bails out when sensitive environment variables are present in the trace
for k in ['SSHPASS', 'AWS_SECRET_ACCESS_KEY', 'PERNOSCO_USER_SECRET_KEY']:
    unclean_env = dict(clean_env)
    unclean_env[k] = "abc"
    record(unclean_env)
    assert submit_dry_run().returncode == 2

# Test analyze-build
subprocess.check_call(["./pernosco-submit", "analyze-build", "--allow-source", testdir, "--build-dir", testdir, tmpdir, "%s/out/main"%testdir])
sources_extra_name = glob.glob("%s/extra_rr_trace_files/sources.extra*"%tmpdir)
assert len(sources_extra_name) == 1
extra_part = os.path.basename(sources_extra_name[0])[8:]
validate_sources_extra(extra_part, github_raw_url, None)
validate_sources_extra_zip(extra_part)

print("\nTesting Mercurial checkout...")

pernosco_submit_test_hg_revision = '1591b57de6f0042423129f14219ddaed04477d6a'
subprocess.check_call(['hg', 'clone', 'http://hg.code.sf.net/p/pernosco-submit-test/code', 'pernosco-submit-test-hg', '-u', pernosco_submit_test_hg_revision], cwd=tmpdir)
testdir = "%s/pernosco-submit-test-hg"%tmpdir
make_changes()
build()
record(clean_env)
assert submit_dry_run().returncode == 0
validate_dry_run()
validate_producer_metadata()
validate_files_user()
validate_sources_user('https://sourceforge.net/p/pernosco-submit-test/code/ci/%s/tree/'%pernosco_submit_test_hg_revision, "?format=raw")
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()

print("\nTesting git-cinnabar checkout...")

subprocess.check_call(['git', 'clone', 'hg::http://hg.code.sf.net/p/pernosco-submit-test/code', 'pernosco-submit-test-cinnabar'], cwd=tmpdir)
testdir = "%s/pernosco-submit-test-cinnabar"%tmpdir
cinnabar_git_revision = subprocess.check_output(['git', 'cinnabar', 'hg2git', pernosco_submit_test_hg_revision], encoding='utf-8', cwd=testdir).strip()
subprocess.check_call(['git', 'checkout', '-q', cinnabar_git_revision], cwd=testdir)
make_changes()
build()
record(clean_env)
# Test skipping title/url
assert submit_dry_run(title=None, url=None).returncode == 0
validate_dry_run(title=None, url=None)
validate_producer_metadata(title=None, url=None)
validate_files_user()
validate_sources_user('https://sourceforge.net/p/pernosco-submit-test/code/ci/%s/tree/'%pernosco_submit_test_hg_revision, "?format=raw")
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()

print("\nPASS")

shutil.rmtree(tmpdir)
