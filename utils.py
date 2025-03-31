import json
import re
import base64
from nearai.agents.environment import Environment
import requests
from decimal import Decimal, ROUND_HALF_DOWN
from rich.console import Console
from rich.markdown import Markdown
from io import StringIO

import zcash

NEAR_BUFFER = 25000000000000000000000

with open("tokens.json", "r") as file:
    data = json.load(file)
    meta_data = data
    for token in meta_data:
        token['min_withdraw_amount'] = Decimal(token['min_withdraw_amount']) / (Decimal(10) ** token['decimals'])

main_prompt = f""" 
  
     Tool Usage Guidelines:
        Before calling the tool, always reconfirm with the user regarding parameters of the function and call the tool only after user gives a positive response.
        There is a chance you put wrong parameters in the tool so always reconfirm with the user before calling the tool.
        Make sure you dont call a tool multiple times unless user tells you to do so.
        NEVER CALL ANY TOOL WITHOUT USER CONFIRMATION.
  
   Always reply with MARKDOWN. the markdown you give is going to be formatted and hence needs to be in the standard format making good tables if needed. Dont care about spacing. make it like normal markdown.

  General Guidelines: Always write to the user in the same language and tone as the user writes to you. Use the same words and phrases that the user uses. This will make the conversation more engaging and user-friendly.
  
    User Confirmation:

        Always ask for explicit confirmation before using any tool.
        Keep the interaction friendly and engaging—feel free to add a joke or a lighthearted comment.

         Tool Usage Guidelines:
        Before calling the tool, always reconfirm with the user regarding parameters of the function and call the tool only after user gives a positive response.
        There is a chance you put wrong parameters in the tool so always reconfirm with the user before calling the tool.
        Make sure you dont call a tool multiple times unless user tells you to do so.
        NEVER CALL ANY TOOL WITHOUT USER CONFIRMATION.

    Structured Output:

        The first line of the output must be empty to ensure proper spacing.
        Always reply with MARKDOWN.

        For enhanced readability:
        🔴 Red for errors. 
        🟢 Green for success messages. 
        🟡 Yellow for warnings.
        🔵 Blue for informational messages.
    
        Example usage: \033[32mSuccess: Transaction completed!\033[0m \n \033[34m Here Is the Transaction Hash: txHash\033[0m


    Formatting & Style Guidelines:
        Wrap important information inside ASCII boxes.
        Use text styling (bold, italics, colors) for better readability and emphasis.

        Implement multi-line cell display for long text:
            │ Token name with │ This is a very long │
            │ extra info │ description that wraps │
            
    2️⃣ Section Headers & Separators
        Use bold, capitalized, or ASCII-stylized headers for clarity.
        Example:

                                            ================================
                                                🚀 SYSTEM STATUS REPORT 🚀
                                            ================================
                                        
    3️⃣ Enhanced Readability & Structure
    
        Provide adequate spacing between sections.
        Align text properly for a neat and structured appearance.
        Use indents, lists, and bullet points to enhance readability.

    Text Styling Instructions IMPORTANT:
    Apply these exact ANSI codes for formatting:
        Bold text: \033[1mYOUR_TEXT\033[0m
        Italic text: \033[3mYOUR_TEXT\033[0m
        Underlined text: \033[4mYOUR_TEXT\033[0m
        
    Apply these exact ANSI codes for colors:
        Red text: \033[31mYOUR_TEXT\033[0m
        Green text: \033[32mYOUR_TEXT\033[0m
        Yellow text: \033[33mYOUR_TEXT\033[0m
        Blue text: \033[34mYOUR_TEXT\033[0m
        Magenta text: \033[35mYOUR_TEXT\033[0m
        Cyan text: \033[36mYOUR_TEXT\033[0m


    Additional Considerations:
    
        Do not dump raw JSON; instead, format it in a structured and readable way.
        Provide as much useful and relevant information as possible while keeping the response concise and user-friendly.
        Ensure outputs do not exceed terminal width to avoid formatting issues.
        Basically format so that its easier for user to understand output.
        THE OUTPUT SHOULD BE IN MARKDOWN. 
        See the formatting instructions twice before replying.

    Tool Usage Guidelines:
        Before calling the tool, always reconfirm with the user regarding parameters of the function and call the tool only after user gives a positive response.
        There is a chance you put wrong parameters in the tool so always reconfirm with the user before calling the tool.
        Make sure you dont call a tool multiple times unless user tells you to do so.
        NEVER CALL ANY TOOL WITHOUT USER CONFIRMATION.
        Beautify all the jsons and outputs you get from tool calls before replying to the user.

    IMPORTANT: These are the tokens supported along with the blockchains they are supported as well as their defuse-asset-ids and other metadata:
    {meta_data}

    Do notice that there is a `min_withdraw_amount` for each token.
    """

def load_url(url):
    r = requests.get(url, timeout=2)
    r.raise_for_status()
    return r.json()

def add_to_log(env: Environment, message):
    try:
        env.add_agent_log(message)
        env.add_reply(message)
    except Exception as e:
        print(f"Error adding to log: {e}")

def reply_with_markdown(env: Environment, data, prompt):
    try:
        messages = [{"role": "system", "content": main_prompt}, {"role": "system", "content": f"User has asked for {prompt}. Format this for markdown and give an extensive reply. {data}"}]
        reply = env.completions_and_run_tools(messages, add_responses_to_messages=False)
        message = reply.choices[0].message
        (message_without_tool_call, tool_calls) = env._parse_tool_call(message)
        if message.content:
            console = Console()
            md = Markdown(message_without_tool_call)
            with StringIO() as buf:
                console.file = buf
                console.print(md)
                env.add_reply(buf.getvalue())

        
    except Exception as e:
        print(f"Error adding to log: {e}")

async def _wallet_balance(env: Environment, account_id, data_old):
    data = (load_url("https://api-mng-console.chaindefuser.com/api/tokens"))
    if data["items"] is None:
        data = data_old
    else:   
        data = data["items"]

    try:
        # Fetch tokens (excluding NEAR)
        token_response = requests.get(f"https://api.fastnear.com/v1/account/{account_id}/ft")
        token_response.raise_for_status()  # Raise an exception for bad status codes

        
        # Fetch NEAR balance
        near_response = requests.get(f"https://api.nearblocks.io/v1/account/{account_id}")
        near_response.raise_for_status()  # Raise an exception for bad status codes
        
        tokens = token_response.json().get("tokens", [])
        near_balance = near_response.json().get("account", [{}])[0].get("amount", "0")
        
        # Process token balances
        token_balances = []
        for token in tokens:
            
            entry = [item for item in data if item.get('contract_address') == token["contract_id"]]

            if (len(entry) == 0):
                continue

            balance = (
                str(((Decimal(token["balance"]) + Decimal(near_balance) - Decimal(NEAR_BUFFER)) / Decimal(Decimal(10) ** int(entry[0]["decimals"]))))
                if token["contract_id"] == "wrap.near"
                else str((Decimal(token["balance"]) / Decimal(Decimal(10) ** int(entry[0]["decimals"]))))
            )
            
            if Decimal(balance) < 0:
                balance = "0"

            balance_usd = str((Decimal(entry[0]["price"]) * Decimal(balance)))
            
            if entry[0]["symbol"].upper() == "WNEAR":
                    entry[0]["symbol"] = "NEAR"
            
            if Decimal(balance) <= 0:
                continue
            
            token_balances.append({
                "contractId": entry[0]["defuse_asset_id"].replace("nep141:", ""),
                "symbol": entry[0]["symbol"],
                "blockchain": entry[0]["blockchain"],
                "balance": balance,
                "balance_usd": balance_usd
            })
        
        entry = [item for item in data if item.get('symbol') == "ZEC"]

        account = zcash.getAccountForAddress(env, env.env_vars.get("ZCASH_ADDRESS"))
        transparent_balance, shielded_balance = zcash.account_balance(env, account)
        zec_balance = Decimal(transparent_balance) + Decimal(shielded_balance) - Decimal("0.0004")
        if zec_balance < 0:
            zec_balance = 0
        
        balance_usd = str((Decimal(entry[0]["price"]) * Decimal(zec_balance)))
        token_balances.append({
                "contractId": entry[0]["defuse_asset_id"].replace("nep141:", ""),
                "symbol": f"{entry[0]['symbol']}",
                "blockchain": entry[0]["blockchain"],
                "balance": str(zec_balance),
                "balance_usd": balance_usd
            })

        if len(token_balances) == 0:
            return "You have no tokens in your wallet."
        
        
        return json.dumps(token_balances)
    
    except requests.RequestException as e:
        raise Exception(f"Request failed: {e}")
    except Exception as e:
        raise Exception(f"Internal server error: {e}")

async def _Intents_balance(env: Environment, account_id,data_old):
    data = (load_url("https://api-mng-console.chaindefuser.com/api/tokens"))
    if data["items"] is None:
        data = data_old
    else:
        data = data["items"]
    user_account_id = env.env_vars.get("ACCOUNT_ID")
    user_private_key = env.env_vars.get("PRIVATE_KEY")
    token_ids = [item["defuse_asset_id"] for item in data]
    
    args = {
        "account_id": account_id,
        "token_ids": token_ids,
    }
    
    near = env.set_near(user_account_id,user_private_key)
    try:
        tr = await near.view("intents.near","mt_batch_balance_of",args)
        balance = {}
        balances = []
                
        for i in range(len(token_ids)):
            if Decimal(tr.result[i]) > 0:
                token = [item for item in data if item.get('defuse_asset_id') == token_ids[i]]
                
                if token[0]["symbol"].upper() == "WNEAR":
                    token[0]["symbol"] = "NEAR"
                
                
                prev = 0
                if token[0]["symbol"] in balance:
                    prev = Decimal(balance[token[0]["symbol"]]["amt"])
                    
                current = (Decimal(tr.result[i]) / Decimal(Decimal(10) ** int(token[0]["decimals"])))
                    
                balance[token[0]["symbol"]] = {
                    "amt" : str(prev + current),
                    "usd" : str(current * (Decimal(token[0]["price"])))
                }
        
        for tk in balance:
            
            balances.append({"TOKEN":tk,
                            "AMOUNT":balance[tk]["amt"],
                            "AMOUNT_IN_USD": balance[tk]["usd"]})
                
        return balances
    except Exception as e:
        raise Exception(f"Internal server error: {e}")

def getAddressChains(env: Environment, address):
    valid_chains = []
    
    if re.match(r'^(([a-z\d]+[-_])*[a-z\d]+\.)*([a-z\d]+[-_])*[a-z\d]+$', address):
        valid_chains.append("near")
    
    if re.match(r'^0x[a-fA-F0-9]{40}$', address):
        valid_chains.extend(["eth", "base", "arb", "gnosis", "bera"])
    
    if (re.match(r'^1[1-9A-HJ-NP-Za-km-z]{25,34}$', address) or
        re.match(r'^3[1-9A-HJ-NP-Za-km-z]{25,34}$', address) or
        re.match(r'^bc1[02-9ac-hj-np-z]{11,87}$', address) or
        re.match(r'^bc1p[02-9ac-hj-np-z]{42,87}$', address)):
        valid_chains.append("btc")
    
    # try:
    #     if PublicKey(address).is_on_curve():
    #         valid_chains.append("sol")
    # except:
    #     pass
    
    if re.match(r'^[DA][1-9A-HJ-NP-Za-km-z]{25,33}$', address):
        valid_chains.append("doge")
    
    # if xrp_isValidClassicAddress(address) or xrp_isValidXAddress(address):
    #     valid_chains.append("xrp")
    
    if zcash.validate_zcash_address(env, address)["isvalid"]:
        valid_chains.append("zec")
    
    return valid_chains