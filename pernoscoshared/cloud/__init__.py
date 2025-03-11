from typing import NewType, Optional, TypedDict

import os
import sys

PernoscoUser = NewType('PernoscoUser', str)
PernoscoGroup = NewType('PernoscoGroup', str)
PernoscoSecretKey = NewType('PernoscoSecretKey', str)
PernoscoUserSecretKey = NewType('PernoscoUserSecretKey', str)
PublicKey = NewType('PublicKey', str)
Signature = NewType('Signature', str)
Nonce = NewType('Nonce', str)

class Config(TypedDict):
    """
    user (PernoscoUser): Pernosco user
    """
    user: PernoscoUser
    """
    pernosco_group (PernoscoGroup): Pernosco group
    """
    group: PernoscoGroup
    """
    pernosco_user_secret_key (PernoscoUserSecretKey): Secret credentials required for Pernosco
    """
    user_secret_key: Optional[PernoscoUserSecretKey]

class CryptoData(TypedDict):
    public_key: PublicKey
    signature: Signature
    nonce: Nonce

def strip_wrapper(s: PublicKey) -> str:
    ret = ""
    for line in s.splitlines():
        if line.startswith("----"):
            continue
        ret += line.strip()
    return ret

def get_config_var_allow_missing(name: str) -> Optional[str]:
    env_var = "PERNOSCO_%s"%(name.upper())
    if env_var in os.environ:
        return os.environ[env_var]
    if 'HOME' in os.environ:
        path = "%s/.config/pernosco/%s"%(os.environ['HOME'], name)
        try:
            with open(path, "r") as file:
                return file.read().replace('\n', '')
        except:
            pass
    return None

def get_config_var(name: str) -> str:
    var = get_config_var_allow_missing(name)
    if var is None:
        env_var = "PERNOSCO_%s"%(name.upper())
        print("Can't find %s or ~/.config/pernosco/%s"%(env_var, name), file=sys.stderr)
        sys.exit(1)

    return var
