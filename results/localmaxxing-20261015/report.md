# MI210 live AITER FA + MTP3 +40GiB LMCache — Verified speed benchmark

Measured2026-10-15ET /2026-10-16UTC, **no service restart, tuning, cache reset or model change**.

## Result

[Public Verified run](https://www.localmaxxing.com/en/runs/cmvab17cq0182le01jj43pl4b) — `APPROVED`, `verifiedRun=true`, no verification issues; public page HTTP200. Persisted flags correctly retain MTP3, AITER FA and prefix caching.

| Metric | Submitted representative request |
|---|---:|
| Decode | 71.768 tokens/s |
| Prefill | 1142.98 tokens/s |
| Total prompt+output/client wall | 88.92 tokens/s |
| Server TTFT | 246.33 ms |
| Peak used device VRAM | 64.489 GB |
| Prompt/output |266/1024 tokens |
| Cached prompt |0 tokens |
| MTP accepted/proposed |696/987 (70.52%) |

Representative is measured-2, the median-decode request. All submitted timings, peak, usage, output and counters come from that request, not independent metric medians.

| Request | Decode tok/s | Prefill tok/s | TTFT ms | MTP accepted/proposed |
|---|---:|---:|---:|---:|
| measured-1 | 72.148 | 1152.18 | 246.01 | 696/987 |
| measured-2 | 71.768 | 1142.98 | 246.33 | 696/987 |
| measured-3 | 71.624 | 1075.59 | 261.29 | 696/987 |

One excluded warmup plus three serial measurements; canonical reasoning-v1 SHA256`9000edaadb16fc77ab78b39917245a03d4d7585c3ba770cb045a47a0e0683445`, greedy/seed42, thinking disabled, max1024/min256 output. Identical measured output hashes. Decode formula `(outputTokens-1)/serverDecodeSeconds`; prefill uses fresh tokens/server prefill; TTFT from server histogram; total uses client wall. vLLM before/after Prometheus deltas require exactly one request and agreeing terminal streamed usage. MTP consistency delta-1 is terminal-boundary tolerance. Peak uses timestamp-scoped one-second AMD-SMI device samples, **not process-attributed**;64,489MB/1000, device capacity65,520MB.

## Exact live stack

- HF`rovangju/Swift-Qwen3.8-27b-W8A8` revision`bf37ab853e8dafbd531dee9cb6d0fbe813b69873`; served alias`qwen38-swift-w8a8`, endpoint`192.168.1.106:8092/v1`. Pinned HF config hash matches local config; retained weight provenance, no fresh full-shard hash.
- AMD Instinct MI210/gfx90a; vLLM`0.1.dev1+g12dadcb41`, image`sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef`.
- Container`qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`, unless-stopped;262144 context, maxseq8, batch1567, ROCM_AITER_FA, MTP3, BF16 KV, prefix/Mamba align. Exact command retained in payload/preflight.
- Remote CPU LMCache`192.168.1.107:5556`,40GiB/chunk800, persistent active/enabled`lmcache-mtp-server.service`; lookup replay800. No-MTP5555 inactive/disabled.
- Local Qwen-group/coordinator/Mamba-retention/admission patches and LMCache PR4410 baseline retained. Copied gfx942 AITER config remains untuned for gfx90a; Python metadata override and CPU transfer limitations remain.

## Boundaries and final health

This266-token prompt is below one800-token cache block. All measured prefix-hit deltas were0; **this is not a long-prompt external-cache benchmark or evidence of a40GiB speedup**. Existing4K/16K reuse validation is in the [final operating report](../../mi210-lmcache-hybrid-20261015/mtp-aiter/report.md).

All responses hit1024-token limit, truncating before all four requested sections completed. Budget result13 batteries/$5.80 was correct; wheel/torque terminology is imprecise. Verified is canonical speed evidence, not a quality score. No full256K or sustained concurrent benchmark.

Post-run health200; exact same inference PID/start time/image,0 automatic restarts, OOM=false. Cache health/status and memory evidence saved; no-MTP remains disabled. No service/configuration changes were performed.

## Evidence

`results.json`, `payload.json`, `verified-receipt.json`, `public-page-verification.json`, `gpu-memory-samples.jsonl`, outputs, model identity/preflight, cache/postrun checks. Raw API context/schema and full receipt are retained locally; credential is loaded privately from the existing protected credential file, never written to benchmark artifacts. Reproduction:`python3 run_benchmark.py` (inference only), then exact payload dry-run and authorized submission via`localmaxxing_call.py`.
