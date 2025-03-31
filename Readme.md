## How to build:

1. Setup up near-ai (Requires Python 3.11)

   ```
   python3 -m pip install nearai
   ```
2. Login to nearAI

   ```
   nearai login
   ```

3. Create an agent


   ```
   nearai agent create
   ```

    Fill the desription and agent name, and instructions as you wish. Go to the directory where the prompt shows the agent.py file is.
     Copy and paste the complete code from this repository to that folder.

* Example: ~/.nearai/


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

