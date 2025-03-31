## How to build:

1. Setup up near-ai (Requires Python 3.11)

   ```
   python3 -m pip install nearai
   ```
2. Login to nearAI

   ```
   nearai login
   ```

3. To Run the Agent
   ```
   cd ZAY-THE-STRATEGY
   nearai agent interactive $PWD --local
   ```

## Environment Variables

To run this project, you will need to add the following environment variables to your .env file

```bash
{
    "ACCOUNT_ID": "", 
    "PRIVATE_KEY": "",
    "ZCASH_NODE_URL": "",
    "ZCASH_USER": "",
    "ZCASH_PASS": "",
    "ZCASH_ACCOUNT_FILE": "",
    "ZCASH_ADDRESS": ""   ----> unified address only
}
```
