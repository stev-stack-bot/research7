# Historical Data

Users can fetch historical data using various REST endpoints, mainly:

* [accountInactiveOrders](https://apidocs.lighter.xyz/reference/accountinactiveorders)
* [trades](https://apidocs.lighter.xyz/reference/trades)
* [logs](https://apidocs.lighter.xyz/reference/get_accounts-param-logs)
* [tx](https://apidocs.lighter.xyz/reference/tx)
* [pnl](https://apidocs.lighter.xyz/reference/pnl)
* [deposit\_history](https://apidocs.lighter.xyz/reference/deposit_history), [transfer\_history](https://apidocs.lighter.xyz/reference/transfer_history), [withdraw\_history](https://apidocs.lighter.xyz/reference/withdraw_history)
* [candles](https://apidocs.lighter.xyz/reference/candles)
* [fundings](https://apidocs.lighter.xyz/reference/fundings), [positionFunding](https://apidocs.lighter.xyz/reference/positionfunding)
* [liquidations](https://apidocs.lighter.xyz/reference/liquidations)
* [exchangeMetrics](https://apidocs.lighter.xyz/reference/exchangemetrics), [executeStats](https://apidocs.lighter.xyz/reference/executestats)

Alternatively, you can use [export](https://apidocs.lighter.xyz/reference/export) to obtain CSVs containing up to 12 months of trades, or up to 3 months of funding payments, for a specific account index.

For interested parties, we're now able to share an S3 bucket containing all trade events going back to mainnet genesis updated daily. To obtain access, you can reach out to us via Discord #support.