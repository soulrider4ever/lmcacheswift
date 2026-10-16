# MI210 Swift Qwen3.8 W8A8 — MTP depth sweep

Date: 2026-10-15  
Hardware/runtime: AMD Instinct MI210 (gfx90a), CT115, vLLM 0.1.dev1+g12dadcb41  
Checkpoint: rovangju/Swift-Qwen3.8-27b-W8A8, revision bf37ab853e8dafbd531dee9cb6d0fbe813b69873  
Endpoint/model: http://192.168.1.106:8092/v1, qwen38-swift-w8a8  
Fixed profile: context 262144, max sequences 2, max batched tokens 4096, BF16 KV auto, ROCM_ATTN, async scheduling, chunked prefill, FULL_DECODE_ONLY; only num_speculative_tokens varied.

## Result

MTP=3 is the selected decode-oriented profile. It led decode in both passes: 55.06 tok/s in the initial run and 55.08 tok/s late. MTP=1 had the highest single-run prefill median (2,002.41 tok/s), but its late repeat was 1,991.76 tok/s—essentially tied with MTP=2 at 1,990.81. MTP=3 gave up less than 1% prefill versus MTP=1 on pooled rows while delivering about 18% more decode throughput.

| MTP depth | First-pass prefill tok/s (range) | First-pass decode tok/s (range) | Accepted / proposed |
|---:|---:|---:|---:|
| 1 | 2,002.41 (1,997.04–2,002.65) | 47.77 (45.97–48.09) | 320 / 445 (71.9%) |
| 2 | 1,997.42 (1,987.17–1,997.62) | 45.52 (43.70–47.59) | 426 / 684 (62.3%) |
| 3 | 1,987.51 (1,984.60–1,988.81) | 55.06 (51.17–61.98) | 459 / 936 (49.0%) |
| 4 | 1,980.70 (1,978.93–1,981.61) | 36.02 (35.72–36.43) | 482 / 1152 (41.8%) |
| 5 | 1,965.15 (1,960.95–1,968.37) | 52.71 (52.67–54.47) | 499 / 1350 (37.0%) |
| 6 | 1,962.92 (1,962.50–1,965.43) | 48.32 (48.26–49.98) | 501 / 1656 (30.3%) |
| 7 | 1,953.68 (1,953.11–1,957.48) | 44.38 (43.43–52.60) | 495 / 1890 (26.2%) |
| 8 | 1,952.96 (1,946.67–1,955.89) | 43.66 (41.84–44.17) | 494 / 2208 (22.4%) |

## Late repeat checks

The MTP=2 baseline and initial leaders were repeated with the same one-warmup/three-sample contract. These pooled rows include six measured requests per phase for the repeated depths.

| Depth | Repeat prefill tok/s (range) | Repeat decode tok/s (range) | Pooled prefill median | Pooled decode median |
|---:|---:|---:|---:|---:|
| 1 | 1,991.76 (1,987.50–1,995.76) | 44.91 (43.18–47.50) | 1,996.40 | 46.73 |
| 2 | 1,990.81 (1,987.42–1,992.39) | 45.51 (43.72–47.65) | 1,991.60 | 45.52 |
| 3 | 1,976.90 (1,970.72–1,979.01) | 55.08 (51.18–59.72) | 1,981.80 | 55.07 |
| 5 | 1,957.65 (1,953.19–1,961.79) | 52.87 (52.83–54.59) | 1,961.37 | 52.85 |

| Comparison | Prefill change | Decode change |
|---|---:|---:|
| MTP=3 vs MTP=1 (pooled) | -0.73% | +17.84% |
| MTP=3 vs MTP=2 (pooled) | -0.49% | +20.99% |
| MTP=3 vs MTP=5 (pooled) | +1.04% | +4.21% |

## Method and verification

Each depth used one discarded warmup and three serial measured requests per phase; temperature 0, seed 42, thinking disabled, concurrency 1. Prefill used 3,533–3,538 fresh prompt tokens and one output token. Decode used a 111–112 token prompt and exactly 256 output tokens. Timing came from per-request vLLM Prometheus histogram deltas; prompts had unique leading nonces, and all measured prefix-cache-hit deltas were zero. Every candidate passed health, model, arithmetic 323, and structured ready_check(status=ok) canaries; queues were idle after measurement, with zero container restarts and no OOM.

After the late repeat, MTP=3 was controlled-restarted as the persistent profile. It again passed health/model checks and both canaries. Final startup admitted 433,340 KV tokens (1.65× a 262,144-token request); its live policy is unless-stopped. DFlash2 is stopped with restart disabled; the preserved MTP=2 container remains stopped as rollback.

Runtime caveats: vLLM warns that depths above 1 repeat the same MTP layer, which can lower acceptance. The runtime also disables prefix-cache reuse because it cannot identify the MTP KV group across Qwen Mamba groups; the 4,096 scheduled-token setting is warned as potentially suboptimal. No full 256K prompt or human answer-quality evaluation was performed. The benchmark is a controlled short-request comparison, not Joey’s full production workload.

## Artifacts

- Per-depth first runs and outputs: mtp1/ through mtp8/.
- Late repeats: repeats/mtp1/, repeats/mtp2/, repeats/mtp3/, repeats/mtp5/.
- Final post-restart canaries: final_mtp3/canaries.json.
- Raw combined summary: summary.json; full per-request timing/counter rows are in each results.json.
- Harnesses: run_benchmark.py, canary.py, run_remaining.py, run_late_repeats.py.
