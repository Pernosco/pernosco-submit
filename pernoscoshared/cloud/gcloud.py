from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Union, TYPE_CHECKING

import os
import shutil
import sys

import pernoscoshared.base as base
from . import PublicKey, PernoscoUser, PernoscoGroup, PernoscoSecretKey, PernoscoUserSecretKey, Config, strip_wrapper, get_config_var_allow_missing

if TYPE_CHECKING:
    StrPath = Union[str, os.PathLike[str]]
else:
    StrPath = Union[str, os.PathLike]

def check_for_command() -> None:
    """
    Check that the `gcloud' command-line tools are installed.
    """
    if not shutil.which('gcloud'):
        print("Please install the gcloud command-line tools using", file=sys.stderr)
        print("  https://cloud.google.com/sdk/docs/install", file=sys.stderr)
        sys.exit(1)

def prep_env_with_config(config: Config) -> Tuple[Dict[str, str], Optional[PernoscoSecretKey]]:
    """
    Return a dictionary with current environment variables plus gcloud access
    credentials, and the PernoscoSecretKey, if present.

        Parameters:
            config: The Pernosco tool config.

        Returns:
            Dictionary with current environment variables plus, if applicable,
            gcloud access, and the PernoscoSecretKey.
    """
    return (dict(os.environ), None)

def check_credentials_cmd(public_key: PublicKey, pernosco_user: PernoscoUser, pernosco_group: PernoscoGroup) -> List[str]:
    raise NotImplementedError

def upload_file_cmd(bucket_path: str, payload: StrPath, metadata: str, **kwargs) -> List[str]:
    return ["gcloud", "storage", "cp", "--custom-metadata", metadata, str(payload), bucket_path]

def get_config(**kwargs) -> Config:
    u = get_config_var_allow_missing('user')
    if not u:
        u = base.check_output(['gcloud', 'config', 'list', 'account', '--format',
                               'value(core.account)']).decode('utf-8')
        if not u:
            print("gcloud does not appear to be logged in.", file=sys.stderr)
            print("  Run `gcloud auth login`", file=sys.stderr)
            sys.exit(1)

    # For now just hardcode something
    group = PernoscoGroup("pernosco-users")
    return {
        "user": PernoscoUser(u),
        "group": group,
        # user_secret_key is only used with the publicly hosted service and the
        # publicly hosted service only runs on AWS, so leave it blank.
        "user_secret_key": None,
    }
