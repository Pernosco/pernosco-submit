from typing import NewType, TypedDict

PernoscoUser = NewType('PernoscoUser', str)
PernoscoGroup = NewType('PernoscoGroup', str)
PernoscoSecretKey = NewType('PernoscoSecretKey', str)
PernoscoUserSecretKey = NewType('PernoscoUserSecretKey', str)
PublicKey = NewType('PublicKey', str)
Signature = NewType('Signature', str)
Nonce = NewType('Nonce', str)

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
