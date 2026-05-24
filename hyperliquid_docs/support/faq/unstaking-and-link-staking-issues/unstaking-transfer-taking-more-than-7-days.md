# Unstaking transfer taking more than 7 days

### Troubleshoot

1. Check that you have initiated the transfer from your Staking balance to your Spot balance, not just unstaked. The 7 day unstaking queue begins after you initiate the transfer. Unstaking and transferring to Spot balance are two separate actions
2. The unstaking queue (transfer to Spot) takes exactly 7 days. As an example, if you initiate a staking to spot transfer of 100 HYPE at 08:00:00 UTC on March 11 and a transfer of 50 HYPE at 09:00:00 UTC on March 12, the 100 HYPE transfer will be finalized at 08:00:01 UTC on March 18 and the 50 HYPE transfer will be finalized at 09:00:01 UTC on March 19

It’s not possible to speed up a transfer from the staking balance to spot balance to take less than 7 days.&#x20;

\
Please refer to this Staking section in the Docs for more information: <https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking>


---

# Agent Instructions: Querying This Documentation

If you need additional information that is not directly available in this page, you can query the documentation dynamically by asking a question.

Perform an HTTP GET request on the current page URL with the `ask` query parameter:

```
GET https://hyperliquid.gitbook.io/hyperliquid-docs/support/faq/unstaking-and-link-staking-issues/unstaking-transfer-taking-more-than-7-days.md?ask=<question>
```

The question should be specific, self-contained, and written in natural language.
The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
