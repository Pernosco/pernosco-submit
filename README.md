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

You must use rr master, at least commit [a7e955493673a5e9b43d84bb34da5a8143843c91](https://github.com/mozilla/rr/commit/a7e955493673a5e9b43d84bb34da5a8143843c91).

## Usage

Run
```
pernosco-submit upload <rr-trace-dir> [<source-dir>...]
```
The rr trace directory will be packaged and uploaded. This may take a while and send many gigabytes of data to Amazon S3.

Only source files under the `<source-dir>`s will be packaged. This will help avoid accidental uploads of confidental files.
