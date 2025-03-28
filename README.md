# pernosco-submit

Submits rr traces to Pernosco for debugging.

## Configuration

The following environment variables must be set:
* `PERNOSCO_USER`: User ID in email address form.
* `PERNOSCO_USER_SECRET_KEY`: Secret key. Be careful about sharing this.
* `PERNOSCO_GROUP`: Group to upload to, e.g. `public`. Influences who can access the trace and who gets billed.

The `openssl`, `tar`, `zstdmt` and `aws` tools must be installed. The best way to install `aws` is
```
sudo pip3 install awscli --upgrade
```
Ubuntu and Debian packages [can have issues](https://github.com/aws/aws-cli/issues/2403).

You will need Python 3.8 or later installed. If your default Python is not 3.8 or later, run `python3.8 pernosco-submit ...` below.

You must use rr master, at least commit [6116360abd43b2098efcd8f37a6e6bab61ca7a79](https://github.com/rr-debugger/rr/commit/6116360abd43b2098efcd8f37a6e6bab61ca7a79).

## Usage

Run
```
pernosco-submit upload [--title <string>] [--url <url>] <rr-trace-dir> [<source-dir>...]
```
The rr trace directory will be packaged and uploaded. This may take a while and send gigabytes of data to Amazon S3.

`pernosco-submit` scans the trace to identify relevant source files. For source files in git or Mercurial repositories that `pernosco-submit` knows about, whose plaintext source can be loaded from some publicly available Web server, `pernosco-submit` adds metadata to the upload so that the Pernosco client will load the source directly from that server. (We gladly accept <a href="https://github.com/Pernosco/pernosco-submit/pulls">pull requests</a> to extend that support.) For source files not in a supported repository (including files generated by the build), or modified locally, `pernosco-submit` will upload the file as part of the submission *only if* the file's `realpath` is under one of the listed `<source-dir>`s. This is to reduce the likelihood of `pernosco-submit` accidentally uploading confidental files. Thus, if you want locally modified and non-repository files to be available in the Pernosco client, you must whitelist directories containing them by passing them as `<source-dir>` parameters to `pernosco-submit`.

`pernosco-submit` does not handle private Github/etc repositories for individual accounts. To have source present for a private repository, use the `--copy-source=<source-dir>` flag to force the repository to be uploaded to Pernosco.

The `--title` option lets you specify a title for the upload. This title is quoted in notification emails from Pernosco, appears in the browser tab title for a Pernosco session, and appears in the top right of the Pernosco window. The `--url` option lets you specify a URL which the title text links to.

## Two-step Upload
Run
```
pernosco-submit package <output-tarball> <rr-trace-dir> [<source-dir> ..]
```
to produce a compressed tarball containing the relevant debug info and source data. Later run
```
pernosco-submit upload-package [--title <string>] [--url <url>] <output-tarball>
```
to upload the trace to Pernosco. Together these two commands are equivalent to the `pernosco-submit upload` command above.

This is intended to allow capturing rr traces in a CI setup and storing the result of `pernosco-submit package` as a CI artifact. A user can decide at a later date that the failure is interesting and finish uploading the data to Pernosco for debugging.

## Tests

Ensure `git`, `hg` and [git-cinnabar](https://github.com/glandium/git-cinnabar) are installed.

Then in the `pernosco-submit` checkout directory, run
```
tests/main.py
```
