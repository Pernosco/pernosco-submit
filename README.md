# pernosco-submit

Submits rr traces to Pernosco for debugging.

## Configuration

The following environment variables must be set:
* `PERNOSCO_USER`: User ID in email address form.
* `PERNOSCO_USER_SECRET_KEY`: Secret key for that user ID. DO NOT SHARE THIS.
* `PERNOSCO_GROUP`: Group to upload to, e.g. `public`. Influences who can access the trace and who gets billed.

## Usage

Run
```
pernosco-submit upload <rr-trace-dir> [<source-dir>...]
```
The rr trace directory will be packaged and uploaded. This may take a while and send many gigabytes of data to Amazon S3.

Only source files under the `<source-dir>`s will be packaged. This will help avoid accidental uploads of confidental files.
