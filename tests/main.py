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
clean_env.pop('STRIPE_SECRET_KEY', None)

pernosco_submit = ['./pernosco-submit']

# Test keygen and get some keys for us to use
output = subprocess.check_output(pernosco_submit + ["keygen", "FAKE_KEY_ID,FAKE_CRED"], encoding='utf-8').split()
private_key = output[2].split('=', 1)[1]
public_key = output[5]

def make_changes():
    with open("%s/main.c"%testdir, "a") as f:
        print("/* EXTRA JUNK */", file=f)
    with open("%s/submodule/submodule.c"%testdir, "a") as f:
        print("/* EXTRA JUNK */", file=f)
    os.mkdir("%s/unreadable_dir"%testdir)
    os.chmod("%s/unreadable_dir"%testdir, 0);

def cleanup_changes():
    os.chmod("%s/unreadable_dir"%testdir, 0o700)

def build():
    # Temporarily rename the build directory so we can test that 'substitute' works
    build_dir = "%s/%s-build"%(os.path.dirname(testdir), os.path.basename(testdir));
    os.rename(testdir, build_dir)
    subprocess.check_call(['./build.sh'], cwd=build_dir)
    os.rename(build_dir, testdir)

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

def main_binary():
    return os.path.basename(glob.glob("%s/*main"%trace_dir)[0])

def submit_dry_run(title='FAKE TITLE', url='FAKE_ñ_URL', prefer_env_vars=True):
    path = "%s/.config/pernosco/user_secret_key"%os.environ['HOME']
    os.makedirs(os.path.dirname(path), exist_ok=True)
    upload_env = dict(clean_env, PERNOSCO_USER='pernosco-submit-test@pernos.co',
                      PERNOSCO_GROUP='pernosco-submit-test')
    delete_path = False
    if prefer_env_vars or os.path.exists(path):
        upload_env['PERNOSCO_USER_SECRET_KEY'] = private_key
    else:
        with open(path, "w") as f:
            f.write(private_key)
        delete_path = True
    cmd = pernosco_submit + ['-x', 'upload',
           '--substitute', 'main=%s'%testdir,
           '--dry-run', '%s/dry-run'%tmpdir, '--consent-to-current-privacy-policy']
    if title:
        cmd.extend(['--title', title])
    if url:
        cmd.extend(['--url', url])
    cmd.extend([trace_dir, tmpdir])
    result = subprocess.run(cmd, env=upload_env)
    if delete_path:
        os.remove(path)
    return result

def validate_dry_run(title="FAKE%20TITLE", url="FAKE_%C3%B1_URL"):
    with open('%s/dry-run.cmd'%tmpdir) as f:
        cmd_obj = json.loads(f.read())
    upload_cmd = cmd_obj['upload_cmd']
    assert upload_cmd[0] == 'aws'
    assert upload_cmd[1] == 's3'
    assert upload_cmd[2] == 'cp'
    assert upload_cmd[3] == '--metadata'
    metadata = upload_cmd[4].split(',')
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
    if upload_cmd[5] == "--endpoint-url":
        assert upload_cmd[6].startswith("https://s3-accelerate.amazonaws.com")
        assert not os.path.exists(upload_cmd[7]) # temp file should have been cleaned up
        assert upload_cmd[8].endswith(".tar.zst")
    else:
        assert not os.path.exists(upload_cmd[5]) # temp file should have been cleaned up
        assert upload_cmd[6].startswith("s3://pernosco-upload/")
        assert upload_cmd[6].endswith(".tar.zst")
    cloud_env = cmd_obj['cloud_env']
    assert cloud_env['AWS_DEFAULT_REGION'] == 'us-east-2'
    assert cloud_env['AWS_ACCESS_KEY_ID'] == 'FAKE_KEY_ID'
    assert cloud_env['AWS_SECRET_ACCESS_KEY'] == 'FAKE_CRED'

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

def validate_sources_user(repo_url, repo_url_suffix=None, submodule_repo_url=None, submodule_private_repo_url=None):
    with open('%s/sources.user'%trace_dir) as f:
        files_user = json.loads(f.read())
    or_condition = files_user[0]['condition']['or']
    assert any(map(lambda x: x['binary'].endswith('librrpreload.so'), or_condition))
    assert any(map(lambda x: x['binary'].endswith('main'), or_condition))
    files = files_user[0]['files']
    if submodule_private_repo_url:
        assert not submodule_repo_url == None
        assert len(files) == 6
        print(submodule_private_repo_url)
        print(files)
        assert any(map(lambda x: x.get('url') == submodule_private_repo_url and x['at'] == "%s/submodule-private"%testdir and x.get('urlSuffix') == repo_url_suffix, files))
    elif submodule_repo_url:
        assert len(files) == 5
        assert any(map(lambda x: x.get('url') == submodule_repo_url and x['at'] == "%s/submodule"%testdir and x.get('urlSuffix') == repo_url_suffix, files))
    else:
        assert len(files) == 4
    assert any(map(lambda x: x.get('url') == repo_url and x['at'] == testdir and x.get('urlSuffix') == repo_url_suffix, files))
    assert any(map(lambda x: x.get('url') and x['url'].startswith('https://raw.githubusercontent.com/rr-debugger/rr/'), files))
    assert any(map(lambda x: x.get('archive') == 'files.user/sources.zip' and x['at'] == '/', files))
    assert any(map(lambda x: x.get('link') == '%s/file.c'%testdir and x['at'] == '%s/out/file.c'%testdir, files))
    assert files_user[0]['relevance'] == 'Relevant'

    or_condition = files_user[1]['condition']['or']
    assert any(map(lambda x: x['binary'].endswith('librrpreload.so'), or_condition))
    assert any(map(lambda x: x['binary'].endswith('main'), or_condition))
    files = files_user[1]['files']
    assert len(files) == 1
    assert files[0]['archive'] == 'files.user/sources-placeholders.zip'
    assert files[0]['at'] == '/'
    assert files_user[1]['relevance'] == 'NotRelevant'

    assert files_user[2]['condition']['binary'] == main_binary()
    assert files_user[2]['overrideCompDir'] == testdir
    assert len(files_user) == 3

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
    assert len(files) == 5
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

    def check_file_present(file):
        sources_zip.getinfo(file)

    def check_file_not_present(file):
        try:
            sources_zip.getinfo(file)
            assert False
        except KeyError:
            pass

    check_file_present('%s/out/message.h'%testdir)
    check_file_present('%s/main.c'%testdir)
    check_file_not_present('%s/file.h'%testdir)
    check_file_present('%s/submodule/submodule.c'%testdir)
    check_file_not_present('%s/submodule/submodule.h'%testdir)
    check_file_not_present('usr/include/stdio.h')

def validate_libthread_db():
    assert os.path.exists('%s/files.system-debuginfo/libthread_db.so'%trace_dir)

def validate_external_debuginfo():
    debug_roots = list(os.listdir('%s/debug/.build-id'%trace_dir))
    assert len(debug_roots) > 0
    for d in debug_roots:
        debugs = list(os.listdir('%s/debug/.build-id/%s'%(trace_dir, d)))
        assert len(debugs) > 0
        for dd in debugs:
            assert dd.endswith(".debug") or dd.endswith(".sup")

def validate_dwos():
    dwos = list(os.listdir('%s/debug/.dwo'%trace_dir))
    assert len(dwos) == 4
    for f in dwos:
        assert f.endswith(".dwo")

print("\nTesting Github checkout...")

pernosco_submit_test_git_revision = '82ce7a2dda8c00e3c0c20aebb93bb79f6ab7da26'
pernosco_submit_test_submodule_git_revision = '5d1caa2e9a9967f3425b924b7e690965645df65e'
pernosco_submit_test_submodule_private_git_revision = '06d6d2214bfc1b6194377a20a4d56dad687fccbf'
subprocess.check_call(['git', 'clone', '--recurse-submodules', 'https://github.com/Pernosco/pernosco-submit-test'], cwd=tmpdir)
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
validate_sources_user(github_raw_url, submodule_repo_url="https://raw.githubusercontent.com/Pernosco/pernosco-submit-test-submodule/%s/"%pernosco_submit_test_submodule_git_revision, submodule_private_repo_url="https://raw.githubusercontent.com/Pernosco/pernosco-submit-test-private-submodule/%s/"%pernosco_submit_test_submodule_private_git_revision)
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()
cleanup_changes()

# Check pernosco-submit bails out when sensitive environment variables are present in the trace
for k in ['SSHPASS', 'AWS_SECRET_ACCESS_KEY', 'PERNOSCO_USER_SECRET_KEY']:
    unclean_env = dict(clean_env)
    unclean_env[k] = "abc"
    record(unclean_env)
    assert submit_dry_run().returncode == 2

# Test analyze-build
subprocess.check_call(pernosco_submit + ["analyze-build",
                       '--substitute', 'main=%s'%testdir,
                       "--allow-source", testdir, "--build-dir", testdir, tmpdir, "%s/out/main"%testdir])
sources_extra_name = glob.glob("%s/extra_rr_trace_files/sources.extra*"%tmpdir)
assert len(sources_extra_name) == 1
extra_part = os.path.basename(sources_extra_name[0])[8:]
validate_sources_extra(extra_part, github_raw_url, None)
validate_sources_extra_zip(extra_part)

print("\nTesting Mercurial checkout...")

pernosco_submit_test_hg_revision = '0049ebe540cbe86278f29dce682e0fda050de59d'
subprocess.check_call(['hg', 'clone', 'http://hg.code.sf.net/p/pernosco-submit-test/code', 'pernosco-submit-test-hg', '-u', pernosco_submit_test_hg_revision], cwd=tmpdir)
testdir = "%s/pernosco-submit-test-hg"%tmpdir
make_changes()
build()
record(clean_env)
assert submit_dry_run(prefer_env_vars=False).returncode == 0
validate_dry_run()
validate_producer_metadata()
validate_files_user()
validate_sources_user('https://sourceforge.net/p/pernosco-submit-test/code/ci/%s/tree/'%pernosco_submit_test_hg_revision, repo_url_suffix="?format=raw")
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()
cleanup_changes()

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
validate_sources_user('https://sourceforge.net/p/pernosco-submit-test/code/ci/%s/tree/'%pernosco_submit_test_hg_revision, repo_url_suffix="?format=raw")
validate_sources_zip()
validate_libthread_db()
validate_external_debuginfo()
validate_dwos()
cleanup_changes()

print("\nPASS")

shutil.rmtree(tmpdir)
