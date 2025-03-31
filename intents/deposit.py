import json
from decimal import Decimal

import requests
from nearai.agents.environment import Environment

import zcash

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


async def _deposit_to_intents(env: Environment, data, amount, sender, token_symbol = ""):
    
    supported_data = data
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    matches = [obj for obj in supported_data if obj["symbol"] == token_symbol.upper() and obj["blockchain"] in ("near", "zec")]
    
    if not matches:
      env.add_reply(f"Token {token_symbol} may not be supported. Please confirm your token again.")
      return False
  
    token = matches[0]
    if token["symbol"] == "ZEC":
        txid = await zcash.deposit(env, sender, amount)
        return True
    
    amount = Decimal(amount) * Decimal(10) ** int(token["decimals"])
    amount = int(amount) 
    contract_id = token["defuse_asset_id"].replace("nep141:", "")

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

    storage_payment = FT_MINIMUM_STORAGE_BALANCE_LARGE - nep141balance

    if contract_id == "wrap.near":

        token_response = requests.get(f"https://api.fastnear.com/v1/account/{user_account_id}/ft")
        token_response.raise_for_status()

        tokens = token_response.json().get("tokens", [])
        near_balance = int(next((token["balance"] for token in tokens if token["contract_id"] == "wrap.near"), 0))

        near_amount = 0 if amount - near_balance < 0 else (amount) - near_balance

        if (storage_payment > 0 or near_amount > 0):
            tr = await near.call(contract_id, "near_deposit", {}, FT_DEPOSIT_GAS, storage_payment + near_amount)
            if "SuccessValue" not in tr.status:
                return False
            
        tr = await near.call(contract_id, "ft_transfer_call",
                {"receiver_id": INTENTS_CONTRACT, "amount": str(amount), "msg": ""},
                FT_TRANSFER_GAS,
                1)
        
        if "SuccessValue" not in tr.status:
                return False
    
    else:
      if storage_payment > 0:
        tr = await near.call(contract_id, "storage_deposit",
                {
                  "account_id": INTENTS_CONTRACT,
                #   "registration_only": True,
                },
                FT_DEPOSIT_GAS, storage_payment)
        
        if "SuccessValue" not in tr.status:
            return False
        
      tr = await near.call(contract_id, "ft_transfer_call",
            {"receiver_id": INTENTS_CONTRACT, "amount": str(amount), "msg": ""},
              FT_TRANSFER_GAS,
            1)
      
      if "SuccessValue" not in tr.status:
            return False

    amount = float(amount) / float(Decimal(10) ** int(token["decimals"]))
    env.add_reply(f"Transaction Hash: {tr.transaction.hash}")
    return True
