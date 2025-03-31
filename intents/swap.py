import base64
import json
import time
from decimal import Decimal

import base58
import nacl.signing
import requests
from nearai.agents.environment import Environment

from intents.utils import add_public_key, get_intent_settled_status, get_swap_message_to_sign, generate_nonce, base64_to_uint8array, serialize_intent

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


async def intent_swap(env: Environment, token_in, token_out, amount_in, token_data, contract_in = "", contract_out = ""):
    token_list = [obj for obj in data if obj["symbol"] == token_in.upper()]
    
    matches_in = [obj for obj in token_data if obj["symbol"] == token_in.upper()]
    
    if not matches_in:
      return False
  
    token_data_in = matches_in[0] if not contract_in else next((obj for obj in matches_in if obj["defuse_asset_id"] == contract_in), None)
    
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    
    near = env.set_near(user_account_id, user_private_key)
    
    if len(token_list) > 1:
        contract_list = [obj["defuse_asset_id"] for obj in token_list]
        tr = await near.view("intents.near", "mt_batch_balance_of",
                    {
                        "account_id": user_account_id,
                        "token_ids": contract_list,
                    })
        result = tr.result
        i = 0
        j = contract_list.index(token_data_in["defuse_asset_id"])
        result[j] = Decimal(result[j]) / (Decimal(10) ** int(token_data_in["decimals"]))

        for i, token_obj in enumerate(token_list):
            if i == j or Decimal(result[i]) == 0:
                continue
            result[i] = Decimal(result[i]) / (Decimal(10) ** int(token_obj["decimals"]))
            if result[j] >= Decimal(amount_in):
                break

            amount_swapped = await _intent_swap(env, token_obj["symbol"], token_data_in["symbol"], result[i], data, token_obj["defuse_asset_id"], token_data_in["defuse_asset_id"])
            
            result[i] = 0
            result[j] = result[j] + amount_swapped

            i = i + 1
            
    return await _intent_swap(env, token_in, token_out, amount_in, token_data, contract_in, contract_out)
    

async def _intent_swap(env:Environment, token_in, token_out, amount_in, token_data, contract_in = "", contract_out = ""):
    
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    
    matches_in = [obj for obj in token_data if obj["symbol"] == token_in.upper()]
    
    if not matches_in:
      return False
  
    matches_out = [obj for obj in token_data if obj["symbol"] == token_out.upper()]
    
    if not matches_out:
      return False
  
    token_data_in = matches_in[0] if not contract_in else next((obj for obj in matches_in if obj["defuse_asset_id"] == contract_in), None)

    if not token_data_in:
        return False
    
    token_data_out = matches_out[0] if not contract_out else next((obj for obj in matches_out if obj["defuse_asset_id"] == contract_out), None)

    if not token_data_out:
        return False
    
    amount = int(Decimal(amount_in) * Decimal(10) ** int(token_data_in["decimals"]))
    
    near = env.set_near(user_account_id)
    args = {
        "account_id": user_account_id,
        "token_ids": [token_data_in["defuse_asset_id"]],
    }
    
    tr = await near.view("intents.near", "mt_batch_balance_of", args)
    if Decimal(amount) > Decimal(tr.result[0]):
        amount = Decimal(tr.result[0])
    
    data = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "quote",
        "params": [
            {
                "defuse_asset_identifier_in": token_data_in["defuse_asset_id"],
                "defuse_asset_identifier_out": token_data_out["defuse_asset_id"],
                "exact_amount_in": str(amount)
            }
        ]
    }

    max_retries = 5
    retry_delay = 1

    for attempt in range(max_retries):
        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            parsed_response = response.json()

            if parsed_response.get('result') is not None:
                break
            else:
                print(f"Empty result on attempt {attempt + 1}. Retrying in {retry_delay} second(s)...")
                time.sleep(retry_delay)

        except Exception as err:
            env.add_reply(f"HTTP error occurred: {err}")
            env.add_reply(f"Error details: {response.text}")
            return None

    else:
        env.add_reply("Error: result is not provided")
        return None

    amount_out = 0

    quote_hash = None
    amount_in = None
    expiration_time = None

    if "result" in parsed_response and len(parsed_response["result"]) > 0:
        for result in parsed_response["result"]:
            # find a quote with the highest amount_out
            if int(result["amount_out"]) > int(amount_out):
                _asset_in = result["defuse_asset_identifier_in"]
                _asset_out = result["defuse_asset_identifier_out"]
                amount_in = result["amount_in"]
                quote_hash = result["quote_hash"]
                amount_out = result["amount_out"]
                expiration_time = result["expiration_time"]
            else:
                this_amount_out = result["amount_out"]
    else:
        env.add_reply(f"Error: {response.status_code}, {response.text}")
        return False

    if not amount_in or not expiration_time or not quote_hash:
        env.add_reply(f"Error with quote data: {response.status_code}, {response.text}")
        return False

    message_str = get_swap_message_to_sign(user_account_id, token_data_in["defuse_asset_id"], amount_in, token_data_out["defuse_asset_id"],
                                           amount_out, expiration_time)
    nonce = generate_nonce()

    quote_hashes = [quote_hash]

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
    _signature = base64.b64encode(signed.signature).decode("utf-8")

    final_signature = base58.b58encode(signed.signature).decode("utf-8")

    public_key_base58 = base58.b58encode(public_key.encode()).decode("utf-8")
    _full_public_key = ED_PREFIX + public_key_base58

    await add_public_key(env, _full_public_key)

    request = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "publish_intent",
        "params": [
            {
                "quote_hashes": quote_hashes,
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

    intent_response, settled, intent_hash, amount_in_usd, amount_out_usd, result = (
        make_intent_swap(request, token_data_out["symbol"], amount_in, token_data_in["decimals"], amount_out, token_data_out["decimals"]))

    if not settled:
        # Try again
        time.sleep(2)
        intent_response, settled, intent_hash, amount_in_usd, amount_out_usd, result = (
            make_intent_swap(request, token_data_out["symbol"], amount_in, token_data_in["decimals"], amount_out, token_data_out["decimals"]))

        if not settled:
            # Try again
            time.sleep(10)
            intent_response, settled, intent_hash, amount_in_usd, amount_out_usd, result = (
                make_intent_swap(request, token_data_out["symbol"], amount_in, token_data_in["decimals"], amount_out, token_data_out["decimals"]))

    if settled:
        transaction_hash = result["result"]["data"]["hash"]
        amount_out = Decimal(amount_out) / (Decimal(10) ** int(token_data_out["decimals"]))
        amount_in = Decimal(amount_in) / (Decimal(10) ** int(token_data_in["decimals"]))
        env.add_reply(f"Transaction Hash: {transaction_hash}")
        return amount_out

    else:
        return False

def make_intent_swap(request, symbol_out, amount_in, token_in_decimals, amount_out, token_out_decimals):

    response = requests.post(url, headers=headers, json=request)
    response.raise_for_status()
    resp = response.json()

    amount_in_usd = f"{float(amount_in) / pow(10, token_in_decimals):.5f}"
    amount_out_usd = f"{float(amount_out) / pow(10, token_out_decimals):.5f}"

    if resp["result"]["status"] == "OK":
        intent_hash = resp["result"]["intent_hash"]

        settled, result = get_intent_settled_status(intent_hash)

        return resp, settled, intent_hash, amount_in_usd, amount_out_usd, result

    else:
        return resp, False, False, amount_in_usd, amount_out_usd, resp
