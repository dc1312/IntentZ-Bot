import base64
import json
import time
from decimal import Decimal

import base58
import nacl.signing
import requests
from nearai.agents.environment import Environment

from intents.utils import get_intent_settled_status, get_withdraw_message_to_sign, generate_nonce, base64_to_uint8array, serialize_intent
from intents.swap import _intent_swap

default_mainnet_rpc = "https://rpc.mainnet.near.org"

import re

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


async def withdraw_from_intents(env: Environment, token, amount, receiver_id, data, token_data=None):
    
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    near = env.set_near(user_account_id, user_private_key)

    amount = int(Decimal(amount) * Decimal(10) ** int(token_data["decimals"]))

    if amount < int(token_data["min_withdraw_amount"]):
        env.add_reply(f"You need to withdraw at minimum {token_data['min_withdraw_amount']} {token} or else you may lose your money.")
        return False

    contract_id = token_data["defuse_asset_id"].replace("nep141:", "")


    token_list = [obj for obj in data if obj["symbol"] == token.upper()]
    
    if len(token_list) > 1:
        contract_list = [obj["defuse_asset_id"] for obj in token_list]
        tr = await near.view("intents.near", "mt_batch_balance_of",
                    {
                        "account_id": user_account_id,
                        "token_ids": contract_list,
                    })
        result = tr.result
        i = 0
        j = contract_list.index(token_data["defuse_asset_id"])
        result[j] = Decimal(result[j]) / (Decimal(10) ** int(token_data["decimals"]))

        for i, token_obj in enumerate(token_list):
            if i == j or Decimal(result[i]) == 0:
                continue
            result[i] = Decimal(result[i]) / (Decimal(10) ** int(token_obj["decimals"]))
            if result[j] >= Decimal(amount):
                break

            amount_swapped = await _intent_swap(env, token_obj["symbol"], token_data["symbol"], result[i], data, token_obj["defuse_asset_id"], token_data["defuse_asset_id"])
            
            result[i] = 0
            result[j] = result[j] + amount_swapped

            i = i + 1
            
    near = env.set_near(user_account_id, user_private_key)
    args = {
        "account_id": user_account_id,
        "token_ids": [token_data["defuse_asset_id"]],
    }
    
    tr = await near.view("intents.near", "mt_batch_balance_of", args)
    if Decimal(amount) > Decimal(tr.result[0]):
        env.add_reply("Amount is more than the maximum available amount to withdraw. Withdrawing the complete amount")
        amount = Decimal(tr.result[0])
    
    message_str = await get_withdraw_message_to_sign(env, user_account_id, contract_id, receiver_id, amount, token_data["blockchain"])
    nonce = generate_nonce()
    
    nonce_uint8array = base64_to_uint8array(nonce)
    quote_hash_solver = serialize_intent(message_str, INTENTS_CONTRACT, nonce_uint8array)

    private_key_base58 = user_private_key[len(ED_PREFIX):]
    private_key_bytes = base58.b58decode(private_key_base58)

    if len(private_key_bytes) != 64:
        raise ValueError("The private key must be exactly 64 bytes long")

    private_key_seed = private_key_bytes[:32]
    signing_key = nacl.signing.SigningKey(private_key_seed)
    public_key = signing_key.verify_key
    signed = signing_key.sign(quote_hash_solver)
    
    final_signature = base58.b58encode(signed.signature).decode("utf-8")
    public_key_base58 = base58.b58encode(public_key.encode()).decode("utf-8")

    request = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "publish_intent",
        "params": [
            {
                "quote_hashes": [],
                "signed_data": {
                    "payload": {
                        "message": message_str,
                        "nonce": nonce,
                        "recipient": INTENTS_CONTRACT,
                    },
                    "standard": "nep413",
                    "signature": f"ed25519:{final_signature}",
                    "public_key": f"ed25519:{base58.b58encode(public_key.encode()).decode()}",
                }
            }
        ]
    }

    response = requests.post(url, headers=headers, json=request)
    response.raise_for_status()
    resp = response.json()

    if resp["result"]["status"] == "OK":
        intent_hash = resp["result"]["intent_hash"]

        settled, result = get_intent_settled_status(intent_hash)
        if settled:
            transaction_hash = result["result"]["data"]["hash"]
            env.add_reply(f"Transaction Hash: {transaction_hash}")
            return True

        else:
            return None

    else:
        return None
