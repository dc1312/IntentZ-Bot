import json
import time
from decimal import Decimal

import requests
from nearai.agents.environment import Environment

import base64
import requests
import hashlib
import secrets
from typing import Any, List, Optional, Union
from serializer import BinarySerializer
from borsh_construct import U32

default_mainnet_rpc = "https://rpc.mainnet.near.org"

with open("tokens.json", "r") as file:
    data = json.load(file)

INTENTS_CONTRACT = "intents.near"
url = "https://solver-relay-v2.chaindefuser.com/rpc"

headers = {
    "Content-Type": "application/json"
}

ED_PREFIX = "ed25519:"  

FT_DEPOSIT_GAS = 30000000000000
FT_TRANSFER_GAS = 50000000000000
FT_MINIMUM_STORAGE_BALANCE_LARGE = 1250000000000000000000


async def add_public_key(env: Environment, public_key):
    # Setup
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    near = env.set_near(user_account_id, user_private_key)

    has_public_key = await near.view(
        "intents.near",
        "has_public_key",
        {
            "account_id": user_account_id,
            "public_key": str(public_key),
        }
    )

    if has_public_key:
        return

    # Add the public_key
    result = await near.call(
        "intents.near",
        "add_public_key",
        {"public_key": str(public_key)},
        FT_DEPOSIT_GAS,  # optional: you can specify gas
        1  # 1 yoctoNEAR
    )


def get_intent_settled_status(intent_hash):
    data = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "get_status",
        "params": [
            {
                "intent_hash": intent_hash
            }
        ]
    }

    start_time = time.time()
    status = "GOOD"
    while True:
        time.sleep(0.2)

        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        resp = response.json()

        if resp['result']['status'] == "SETTLED":
            return True, resp

        elif (resp['result']['status'] == "NOT_FOUND_OR_NOT_VALID_ANYMORE"
            or resp['result']['status'] == "NOT_FOUND_OR_NOT_VALID"):
            print("Intent not found or not valid anymore")
            return False, resp
        
        elif resp['result']['status'] == "FAILED":
            return False, resp

        elif time.time() - start_time > 30:
            print("Timeout: Operation took longer than 30 seconds")
            return False, resp

        if status != resp['result']['status']:
            status = resp['result']['status']
        


async def get_withdraw_message_to_sign(env: Environment, signer_id, token, receiver_id, amount, blockchain):
    # now + 3 min in a format of 2025-01-21T14:55:40.323Z
    exp_time = (time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 180)))
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")

    near = env.set_near(user_account_id, user_private_key)

    nep141balance = await near.view(
        contract_id="wrap.near",
        method_name="storage_balance_of",
        args={
            "account_id": user_account_id
        }
    )

    if nep141balance.result:
        nep141balance = int(nep141balance.result['available'])
    else:
        nep141balance = 0

    storage_deposit = 0 if nep141balance > FT_MINIMUM_STORAGE_BALANCE_LARGE else FT_MINIMUM_STORAGE_BALANCE_LARGE

    message = "dummy"

    if token == "wrap.near":
        message = {
            "signer_id": signer_id,
            "deadline": exp_time,
            "intents": [
                {
                    "intent": "native_withdraw" ,
                    "receiver_id": receiver_id,
                    "amount": str(amount)
                }
            ]
        }
    elif blockchain == "near":
        message = {
            "signer_id": signer_id,
            "deadline": exp_time,
            "intents": [
                {
                    "intent": "ft_withdraw" ,
                    "receiver_id": receiver_id,
                    "token": token,
                    "amount": str(amount),
                    "deposit": str(storage_deposit)
                }
            ]
        }
    else:
        message = {
            "signer_id": signer_id,
            "deadline": exp_time,
            "intents": [
                {
                    "intent": "ft_withdraw",
                    "receiver_id": token,
                    "amount": str(amount),
                    "token": token,
                    "deposit": str(storage_deposit),
                    "memo": f"WITHDRAW_TO:{receiver_id}"
                }
            ]
        }
    
    # Convert message dictionary to JSON string
    message_str = json.dumps(message)
    return message_str


def get_swap_message_to_sign(signer_id, token_in, amount_in, token_out, amount_out, exp_time):
    # Construct the message dictionary
    message = {
        "signer_id": signer_id,
        "deadline": exp_time,
        "intents": [
            {
                "intent": "token_diff",
                "diff": {
                    f"{token_in}": f"-{amount_in}",
                    f"{token_out}": amount_out
                }
            }
        ]
    }

    message_str = json.dumps(message)
    return message_str


def generate_nonce():
    random_array = secrets.token_bytes(32)
    return base64.b64encode(random_array).decode('utf-8')


def base64_to_uint8array(base64_string):
    binary_data = base64.b64decode(base64_string)
    return list(binary_data)


def convert_nonce(value: Union[str, bytes, list[int]]):
    """Converts a given value to a 32-byte nonce."""
    if isinstance(value, bytes):
        if len(value) > 32:
            raise ValueError("Invalid nonce length")
        if len(value) < 32:
            value = value.rjust(32, b"0")
        return value
    elif isinstance(value, str):
        nonce_bytes = value.encode("utf-8")
        if len(nonce_bytes) > 32:
            raise ValueError("Invalid nonce length")
        if len(nonce_bytes) < 32:
            nonce_bytes = nonce_bytes.rjust(32, b"0")
        return nonce_bytes
    elif isinstance(value, list):
        if len(value) != 32:
            raise ValueError("Invalid nonce length")
        return bytes(value)
    else:
        raise ValueError("Invalid nonce format")


class Payload:
    def __init__(  # noqa: D107
            self, message: str, nonce: Union[bytes, str, List[int]], recipient: str, callback_url: Optional[str] = None
    ):
        self.message = message
        self.nonce = convert_nonce(nonce)
        self.recipient = recipient
        self.callbackUrl = callback_url


PAYLOAD_SCHEMA: list[list[Any]] = [
    [
        Payload,
        {
            "kind": "struct",
            "fields": [
                ["message", "string"],
                ["nonce", [32]],
                ["recipient", "string"],
                [
                    "callbackUrl",
                    {
                        "kind": "option",
                        "type": "string",
                    },
                ],
            ],
        },
    ]
]

def serialize_intent(intent_message, recipient, nonce):
    payload2 = Payload(intent_message, nonce, recipient, None)
    borsh_payload = BinarySerializer(dict(PAYLOAD_SCHEMA)).serialize(payload2)

    base_int = 2 ** 31 + 413
    base_int_serialized = U32.build(base_int)
    combined_data = base_int_serialized + borsh_payload
    hash_result = hashlib.sha256(combined_data).digest()
    return hash_result
