# Manage Public Pools

Something to keep in mind is that Lighter considers Public Pools as a special type of Subaccount, where multiple users in addition to its owner can deposit in exchange for pool shares. Hence, you can trade on it via API as you would with a subaccount. Users can participate in Public Pools by creating and modifying them (on a whitelist basis), but also mint and burn shares via API. The corresponding transaction types are:

* [TxTypeL2CreatePublicPool (10)](https://github.com/elliottech/lighter-python/blob/main/examples/public_pool_create_modify.py)
* [TxTypeL2UpdatePublic Pool (11)](https://github.com/elliottech/lighter-python/blob/main/examples/public_pool_create_modify.py)
* [TxL2TypeMintShares (18)](https://github.com/elliottech/lighter-python/blob/main/examples/public_pool_deposit.py)
* [TxL2TypeBurnShares (19)](https://github.com/elliottech/lighter-python/blob/main/examples/public_pool_withdraw.py)

In the hyperlinks, you can find the corresponding examples on the Python SDK using wrapper functions.

You can monitor your shares using the [account](https://apidocs.lighter.xyz/reference/account-1) endpoint, the [publicPoolsMetadata](https://apidocs.lighter.xyz/reference/publicpoolsmetadata) endpoint, or any Websocket channel that contains the [PoolShares JSON](https://apidocs.lighter.xyz/docs/websocket-reference#poolshares-json). Note that `entry_usdc`  represents the USDC used to acquire pool shares - if you're looking to get an accurate price per share to date, you can query the [publicPoolsMetadata](https://apidocs.lighter.xyz/reference/publicpoolsmetadata) endpoint using `account_id` plus one. Staking pools are to be considered similar to public pools in structure, wth `principal_amount` representing the number of coins staked.

This is what a request to fetch LLP's (281474976710654) metadata would look like:

```shell
curl --request GET \
     --url 'https://mainnet.zklighter.elliot.ai/api/v1/publicPoolsMetadata?index=281474976710655&limit=1' \
     --header 'accept: application/json'
```

The response will look like this:

```json
{
  "code": 200,
  "public_pools": [
    {
      "code": 0,
      "account_index": 281474976710654,
      "created_at": 1737098583,
      "master_account_index": 1,
      "account_type": 3,
      "name": "Lighter Liquidity Provider (LLP)",
      "l1_address": "0x0000000000000000000000000000000000000000",
      "annual_percentage_yield": 30.733724772746875,
      "sharpe_ratio": 5.004736993685667,
      "status": 0,
      "operator_fee": "0.0000",
      "total_asset_value": "693552603.614245",
      "total_shares": 208742636824
    }
  ]
}
```

If you provide `auth`, you can fetch your account's data as well from this endpoint without having to query the `account` one.

To obtain `price_per_share` you can then simply calculate `total_asset_value`/`total_shares`.

<br />