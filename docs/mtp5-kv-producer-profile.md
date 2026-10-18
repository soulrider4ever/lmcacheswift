# MI210 MTP5 + LMCache `kv_producer` target profile

## Status

This is the requested GitHub launch profile. This repository update changes
source only; it does not restart or redeploy a service. The combined MTP5 +
LMCache `kv_producer` profile has **not** been runtime-validated. The last
validated hybrid profile remains MTP3 + `kv_role=kv_both`, preserved in
[`launch/docker-run-mtp3-validated.sh`](../launch/docker-run-mtp3-validated.sh)
and [`launch/mtp3-validated-args.json`](../launch/mtp3-validated-args.json).

The separate no-LMCache MTP5 benchmark measured 74.234 tok/s median versus
71.488 tok/s for its matched no-LMCache MTP3 baseline (+3.84%). Both responses
reached the 1,024-token cap and their hashes differed. That establishes a
speed result for the no-LMCache profile, not answer-quality equivalence or
performance for MTP5 with LMCache as producer. See the
[verified MTP5 run](https://www.localmaxxing.com/en/runs/cmvbnnl7401mmle0192pjwbqg).

## Target settings

- `--speculative-config`: `{"method":"mtp","num_speculative_tokens":5}`
- `--kv-transfer-config`: `LMCacheMPConnector`, with `kv_role=kv_producer`
- Retain image digest `sha256:432b6062d86507848c5fe4d57c2b161f54e9dbe207a624587544d44c2f1f4cb3`,
  AITER FA, model/checkpoint, context, sequence/batch limits, cache endpoint,
  transfer mode, and the other options recorded in the archived launch
  manifest. The MTP depth and KV role are the requested setting changes.

The candidate launcher and machine-readable arguments are
[`launch/docker-run-mtp5-kv-producer.sh`](../launch/docker-run-mtp5-kv-producer.sh)
and [`launch/mtp5-kv-producer-args.json`](../launch/mtp5-kv-producer-args.json).
The launcher targets the production inference port; it is not a parallel
smoke-test recipe. Do not use it for a live cutover without a separately
authorized handoff and the normal startup, health, model-metadata, canary, and
post-request checks.
