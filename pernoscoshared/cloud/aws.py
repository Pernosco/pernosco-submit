from __future__ import annotations
from typing import Dict, List, Optional, Union, Tuple, NewType, TYPE_CHECKING

import os
import shutil
import sys

import pernoscoshared.base as base
from . import *

isAwsCliV2 = base.check_output(['aws', '--version']).decode('utf-8').startswith("aws-cli/2.")

if TYPE_CHECKING:
    StrPath = Union[str, os.PathLike[str]]
else:
    StrPath = Union[str, os.PathLike]

AwsAccessKeyId = NewType('AwsAccessKeyId', str)
AwsSecretAccessKey = NewType('AwsSecretAccessKey', str)

def check_for_command() -> None:
    """
    Check that the `aws' command-line tools are installed.
    """
    if not shutil.which('aws'):
        print("Please install the AWS command-line tools using", file=sys.stderr)
        print("  sudo pip3 install awscli --upgrade", file=sys.stderr)
        print("(Distribution packages may fail due to https://github.com/aws/aws-cli/issues/2403.)", file=sys.stderr)
        sys.exit(1)

def prep_env_with_config(config: Config) -> Tuple[Dict[str, str], Optional[PernoscoSecretKey]]:
    """
    Return a dictionary with current environment variables plus AWS access
    credentials, and the PernoscoSecretKey, if present.

        Parameters:
            config: The Pernosco tool config.

        Returns:
            Dictionary with current environment variables plus, if applicable,
            AWS access, and the PernoscoSecretKey.
    """
    if config["user_secret_key"] is None:
        return (dict(os.environ), None)

    pernosco_user_secret_key = config["user_secret_key"]
    parts = pernosco_user_secret_key.split(',')
    aws_access_key_id = AwsAccessKeyId(parts[0])
    aws_secret_access_key = AwsSecretAccessKey(parts[1])
    aws_env = dict(os.environ,
        AWS_DEFAULT_REGION='us-east-2',
        AWS_ACCESS_KEY_ID=aws_access_key_id,
        AWS_SECRET_ACCESS_KEY=aws_secret_access_key)
    pernosco_secret_key = PernoscoSecretKey(parts[2])
    return (aws_env, pernosco_secret_key)

def check_credentials_cmd(public_key: PublicKey, pernosco_user: PernoscoUser, pernosco_group: PernoscoGroup) -> List[str]:
    cmd = ["aws", "lambda", "invoke", "--function-name", "upload-credential-check", "--qualifier"]
    if 'PERNOSCO_CREDENTIAL_CHECKER' in os.environ:
        cmd.extend([os.environ['PERNOSCO_CREDENTIAL_CHECKER']])
    else:
        cmd.extend(["PROD"])
    if isAwsCliV2:
        cmd.extend(["--cli-binary-format", "raw-in-base64-out"])
    cmd.extend(["--payload", "\"publickey=%s,user=%s,group=%s\""%(strip_wrapper(public_key), pernosco_user, pernosco_group), "/dev/null"])
    return cmd

def upload_file_cmd(bucket_path: str, payload: StrPath, metadata: str, transferAcceleration: bool = False, **kwargs) -> List[str]:
    cmd = ["aws", "s3", "cp", "--metadata", metadata]

    if transferAcceleration:
        cmd.extend(["--endpoint-url", "https://s3-accelerate.amazonaws.com"])

    cmd.extend([str(payload), bucket_path])

    return cmd

def get_config(require_user_secret_key: bool = True, **kwargs) -> Config:
    user = PernoscoUser(get_config_var('user'))
    group = PernoscoGroup(get_config_var('group'))
    if require_user_secret_key:
        user_secret_key = PernoscoUserSecretKey(get_config_var('user_secret_key'))
    else:
        config_var = get_config_var_allow_missing('user_secret_key')
        if config_var is None:
            user_secret_key = None
        else:
            user_secret_key = PernoscoUserSecretKey(config_var)
    return {
        "user": user,
        "group": group,
        "user_secret_key": user_secret_key,
    }
