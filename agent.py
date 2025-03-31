import asyncio
import json

import utils
import zcash

from nearai.agents.environment import Environment

from rich.console import Console
from rich.markdown import Markdown
from rich import print as rprint

from intents.deposit import _deposit_to_intents
from intents.swap import intent_swap
from intents.withdraw import withdraw_from_intents
from io import StringIO

import sys

# env:Environment = Environment()
console = Console()

with open("tokens.json", "r") as file:
    data = json.load(file)

with open("env", "r") as file:
    env_vars = json.load(file)
    if not env_vars["ACCOUNT_ID"] or not env_vars["PRIVATE_KEY"] or not env_vars["ZCASH_NODE_URL"]:
        print("Please set ACCOUNT_ID, PRIVATE_KEY, ZCASH_NODE_URL in env file")
        sys.exit(1)
    
    if not env_vars["ZCASH_USER"] or not env_vars["ZCASH_PASS"] or not env_vars["ZCASH_ACCOUNT_FILE"]:
        print("Please set ZCASH_USER, ZCASH_PASS, ZCASH_ACCOUNT_FILE in env file")
        sys.exit(1)
    
    if not env_vars["ZCASH_ADDRESS"] :
        print("Please set ZCASH_ADDRESS in env file")
        sys.exit(1)
    
    env.env_vars.update(env_vars)

# env:Environment

with open("tokens.json", "r") as file:
    data = json.load(file)

def get_all_tokens():
    """Gets all the tokens supported with relevant metadata. Use this tool to get the tokens supported. This tool is not intended for direct calls by users."""
    data = utils.load_url("https://api-mng-console.chaindefuser.com/api/tokens")
    return data["items"]

def wallet_balance(accountId = env.env_vars.get("ACCOUNT_ID", "")):
    """ Request Handling for Wallet Balance
        Specific Wallet Balance Request: If the user explicitly requests a wallet balance and does not intend to check the balance from the Defuse/Intents contract, call this tool.
        Account ID Handling: If the user provides an account ID (words like 'my' etc are not account id), set the accountId parameter to the provided ID. 
        Ambiguous Request: If the user simply types "balance" or you are unsure about their intent, ask them if they want to check their wallet balance. If they confirm, proceed with calling this tool.
    """
    accountId = accountId if ((accountId != "") or (accountId != None)) else  env.env_vars.get("ACCOUNT_ID", "")
    token_balances = asyncio.run(utils._wallet_balance(env, accountId, data))
    utils.reply_with_markdown(env, token_balances, f"wallet balance of {accountId}")

def Intents_balance(accountId = env.env_vars.get("ACCOUNT_ID", "")):
    """Request Handling for Intents Balance
        Specific Intents Balance Request: If the user explicitly requests a Intents/Defuse balance and does not intend to check the balance from the wallet, call this tool.
        Account ID Handling: If the user provides an account ID (words like 'my' etc are not account id), set the accountId parameter to the provided ID. 
        Ambiguous Request: If the user simply types "balance" or you are unsure about their intent, ask them if they want to check their Intents balance. If they confirm, proceed with calling this tool.
    """
    accountId = accountId if ((accountId != "") or (accountId != None)) else  env.env_vars.get("ACCOUNT_ID", "")
    token_balances = asyncio.run(utils._Intents_balance(env, accountId, data))
    utils.reply_with_markdown(env, token_balances, f"Intents balance of {accountId}")

def deposit_to_intents(amount, token_symbol="", sender = env.env_vars.get("ACCOUNT_ID", None)):
    
    """Always re-ask for user confirmation regarding the amount and the token before calling the tool each time. This tool deposits a token to the intents contract. You can call this tool if user asks to deposit into defuse/intents contract, after user confirmation regarding the amount and the token. Take the amount and token symbol from the user, and call this tool."""
    
    if token_symbol.upper() == "ZEC":
        if (sender == env.env_vars.get("ACCOUNT_ID", None)):
            sender = env.env_vars.get("ZCASH_ADDRESS", None)
        sender = sender if sender != "" else  env.env_vars.get("ZCASH_ADDRESS", None)
    else:    
        sender = sender if sender != "" else  env.env_vars.get("ACCOUNT_ID", None)
        
    with console.status(f"[bold green]Depositing {amount} {token_symbol}... This may take up to 15 minutes.[/bold green]"):
        asyncio.run(_deposit_to_intents(env, data, amount, sender, token_symbol))


def swap_in_intents(token_in, amount_in, token_out):
    """Always re-ask for user confirmation regarding the amount and the token-in and token-out before calling the tool each time. This tool swaps token-in to token-out inside defuse/intents. Remember, this is a swap inside intents, and not a swap in the user's wallet. You can call this tool if user asks to swap inside defuse/intents contract, after user confirmation regarding the amount-in, token-in and token-out. Take the amount and token symbols from the user, and call this tool."""
    with console.status(f"[bold green]Swapping {amount_in} {token_in} to {token_out}...[/bold green]"):
        asyncio.run(intent_swap(env, token_in, token_out, amount_in, data))

def _withdraw_from_intents(amount, token_symbol="", receiverId = env.env_vars.get("ACCOUNT_ID", None)):
    """Before calling the tool, always reconfirm with the user regarding the amount and token they want to withdraw. If the user requests a withdrawal from the defuse/intents contract, explicitly ask for confirmation on the amount and token symbol before proceeding.

    Additionally, verify the receiver account ID:
    If the user provides a receiver id, then set reciverId to that
    Only after receiving explicit confirmation on these details should you proceed with calling the tool."""
    
    receiverId = receiverId if receiverId else env.env_vars.get("ACCOUNT_ID", None)

    if token_symbol.upper() == "ZEC":
        if (receiverId == env.env_vars.get("ACCOUNT_ID", None)):
            receiverId = env.env_vars.get("ZCASH_ADDRESS", None)

    valid_chains = utils.getAddressChains(env, receiverId)

    if not valid_chains:
        env.add_reply(f"It seems {receiverId} is not a valid address for any chain we support")
        return False

    match = [obj for obj in data if obj["symbol"] == token_symbol.upper() and obj["blockchain"] in valid_chains]

    if not match:
      env.add_reply(f"Token {token_symbol} may not be supported for withdrawing into {receiverId} for chains {valid_chains}. Please confirm your token and address again.")
      return False

    while len(match) > 1:
        rprint(f"To which blockchain do you wish to withdraw? Do make sure to write the exact chain.")
        rprint([data["blockchain"] for data in match])
        chain = input("> ")
        match = [obj for obj in match if obj["blockchain"] == chain]
    
        if not match:
            env.add_reply(f"Token {token_symbol} may not be supported for withdrawing into {receiverId} for chain {chain}. Please confirm your token and address again.")
            return False
        
    token_data = match[0]
    
    if token_symbol.upper() == "ZEC":
        with console.status(f"[bold green]Withdrawing {amount} {token_symbol}... This may take up to 15 minutes.[/bold green]"):    
            receiverId = receiverId if receiverId else  env.env_vars.get("ZCASH_ADDRESS", None)
            asyncio.run(zcash.withdraw(env, token_symbol, amount, receiverId, data))
            return

    with console.status(f"[bold green]Withdrawing {amount} {token_symbol}... This may take up to 15 minutes.[/bold green]"):    
        asyncio.run(withdraw_from_intents(env, token_symbol, amount, receiverId, data, token_data))

def swap(token_in, amount_in, token_out, receiverId = env.env_vars.get("ACCOUNT_ID", None), sender = env.env_vars.get("ACCOUNT_ID", None)):
    """Before calling the tool, always reconfirm with the user regarding the amount and token they want to swap. This tool swaps token-in to token-out in the user's wallet. It deposits, then swaps and then withdraws to the withdrawal address. This is not to be called if the swap is in the intents contract."""
    
    with console.status(f"[bold green]Depositing {amount_in} {token_in}... This may take up to 15 minutes.[/bold green]"):
        if token_in.upper() == "ZEC":
            if (sender == env.env_vars.get("ACCOUNT_ID", None)):
                sender = env.env_vars.get("ZCASH_ADDRESS", None)
            sender = sender if sender != "" else  env.env_vars.get("ZCASH_ADDRESS", None)

        else:    
            sender = sender if sender != "" else  env.env_vars.get("ACCOUNT_ID", None)
        asyncio.run(_deposit_to_intents(env, data, amount_in, sender, token_in))

    with console.status(f"[bold green]Swapping {amount_in} {token_in} to {token_out}...[/bold green]"):
        amount = asyncio.run(intent_swap(env, token_in, token_out, amount_in, data))
        
    receiverId = receiverId if receiverId else env.env_vars.get("ACCOUNT_ID", None)

    if token_out.upper() == "ZEC":
        if (receiverId == env.env_vars.get("ACCOUNT_ID", None)):
            receiverId = env.env_vars.get("ZCASH_ADDRESS", None)

    valid_chains = utils.getAddressChains(env, receiverId)

    if not valid_chains:
        env.add_reply(f"It seems {receiverId} is not a valid address for any chain we support")
        return False

    match = [obj for obj in data if obj["symbol"] == token_out.upper() and obj["blockchain"] in valid_chains]

    if not match:
        env.add_reply(f"Token {token_out} may not be supported for withdrawing into {receiverId} for chains {valid_chains}. Please confirm your token and address again.")
        return False

    while len(match) > 1:
        rprint(f"To which blockchain do you wish to withdraw? Do make sure to write the exact chain.")
        rprint([data["blockchain"] for data in match])
        chain = input("> ")
        match = [obj for obj in match if obj["blockchain"] == chain]
    
        if not match:
            env.add_reply(f"Token {token_out} may not be supported for withdrawing into {receiverId} for chain {chain}. Please confirm your token and address again.")
            return False
        
    token_data = match[0]
    
    if token_out.upper() == "ZEC":
        with console.status(f"[bold green]Withdrawing {amount} {token_out}... This may take up to 15 minutes.[/bold green]"):    
            receiverId = receiverId if receiverId else  env.env_vars.get("ZCASH_ADDRESS", None)
            asyncio.run(zcash.withdraw(env, token_out, amount, receiverId, data))
            return

    with console.status(f"[bold green]Withdrawing {amount} {token_out}... This may take up to 15 minutes.[/bold green]"):    
        asyncio.run(withdraw_from_intents(env, token_out, amount, receiverId, data, token_data))



def run(env: Environment):

    # return zcash.transfer(env, "u1rqpc382a2yxjmvqn68r226nhnmqwk38mz9wgg4rrm27vr8paes5jsywp8umkt8ks6huy7fcm2cc0ultx6ztu05ut5y4p20j48u3g8macdrda5gtuyurhqj9zsklc3l6fnjmcn30wk2rd0derh3zezs3quk7efe4xf0qm7da7tpg5vukhvvtfvfutkqm6dhtp9xy58su4j0djwuas63l", "0.0623", "zs1q7k4z0cyn2lah5m3l7aptrnssgg7f2dk6mjygqsh20s0mqhtjsjaq9l00w0qxj2cvfjk72yqhr4", args)

    tool_registry = env.get_tool_registry(new=True)
    tool_registry.register_tool(deposit_to_intents)
    tool_registry.register_tool(swap_in_intents)
    tool_registry.register_tool(_withdraw_from_intents)
    tool_registry.register_tool(wallet_balance)
    tool_registry.register_tool(Intents_balance)
    tool_registry.register_tool(swap)
    
    user = env.env_vars.get("ACCOUNT_ID", "NEAR_ACCOUNID_NOT_IN_ENV")
    zec_addr = env.env_vars.get("ZCASH_ADDRESS", "ZCASH_ADDRESS_NOT_IN_ENV")
    
    messages = [{"role": "system", "content": utils.main_prompt}, {"role": "user", "content": f"The thread is in terminal. My near account id is {user}. My zec address is {zec_addr}. Make sure to follow the Guidelines below {utils.main_prompt}."}] + env.list_messages()
    
    # asyncio.run(zcash.withdraw(env, "ZEC", "0.03", "u1pdzlp4w6rj6umsmkj5kc5te3thg3wenlnec56t7l085th7hc7degw7ysqkfr97ldwky8jlaf4zfdyd74dkl4pemdncgsn30grq925mn5y0lt6hed6kpld7pr564lxahppp6kvp5h28x0ca69cyed5x2yv9ahlx302sxav4p2cqx5zhd9d42pch9425newaaaf0hhk27gjeftxt5yyr4", data))

    all_tools = env.get_tool_registry().get_all_tool_definitions()
    reply = env.completions_and_run_tools(messages, tools=all_tools, add_responses_to_messages=False)
    message = reply.choices[0].message
    (message_without_tool_call, tool_calls) = env._parse_tool_call(message)
    if message_without_tool_call:
        console = Console()
        md = Markdown(message_without_tool_call)

        with StringIO() as buf:
            console.file = buf
            console.print(md)
            env.add_reply(buf.getvalue())

run(env)
