# What is DEX abstraction?

DEX abstraction is a setting for trading HIP-3 perps. To simplify user experience, enabling DEX abstraction hides the notion of different balances for each HIP-3 DEX. This is the default setting for users.&#x20;

### DEX abstraction enabled (default setting)

* With DEX abstraction enabled, you will not see separate balances for each HIP-3 DEX in which you have positions or open orders.

<div align="left"><figure><img src="/files/kzkkPogMXHLVtIRPLaed" alt=""><figcaption></figcaption></figure></div>

* Collateral for USDC positions will come from your USDC (Perps) available balance. Collateral for non-USDC quote assets (E.g. USDT or USDH) will come from the respective spot balances.

### DEX abstraction disabled

* With DEX abstraction disabled, you will see separate balances for each HIP-3 DEX. The balance can be used to open new positions just like the regular USDC perps balance you might be familiar with.

<figure><img src="/files/OvDqs1SXgOHOihyPxvfH" alt=""><figcaption></figcaption></figure>

* To open a new position, you will need to first transfer funds to that HIP-3 DEX. You will see the "Transfer to Perps" option in your order form or "Perps to Spot Transfer" button on the Portfolio page after selecting a new HIP-3 asset in the token selector.&#x20;
* When DEX abstraction is re-enabled, any available balance not used for positions or open orders is automatically transferred back to its respective Perps or Spot balance. E.g., USDC (Perps) xyz will be transferred to USDC (Perps).
* To disable HIP-3 DEX abstraction, check "Disable HIP-3 Dex Abstraction" in the Settings dropdown of app.hyperliquid.xyz or the respective frontend or app you're using. It is enabled by default.


---

# Agent Instructions: Querying This Documentation

If you need additional information that is not directly available in this page, you can query the documentation dynamically by asking a question.

Perform an HTTP GET request on the current page URL with the `ask` query parameter:

```
GET https://hyperliquid.gitbook.io/hyperliquid-docs/support/faq/hip-3/what-is-dex-abstraction.md?ask=<question>
```

The question should be specific, self-contained, and written in natural language.
The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
