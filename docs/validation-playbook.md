# Validation Playbook — how every number was measured, and how to re-verify

All scripts in `scripts/` (experiment copies also under `results/hybrid/mtp-aiter/`).
Harnesses assume CT115 paths (`/home/ubuntu/lmcache-integration-20261015/`) —
adjust `root=` before reuse. None of these are production health checks;
several EXIT traps intentionally restore fallback profiles.

## Canonical contracts

- **Health:** `GET http://127.0.0.1:8092/health` on CT115; `GET
  http://127.0.0.1:8081/healthcheck` + `/status` on CT125 (expect
  `chunk_size:800`, blake3, `memory_configured_bytes:42949672960`).
- **Decode benchmark (synthetic counting):**
  `scripts/decode_count_benchmark.py <phase>` — 3× "count 1–100" at
  `max_tokens=512, temperature=0, seed=42, enable_thinking=false`; asserts the
  printed sequence is exactly 1..100 and `finish_reason=stop`; decode tok/s =
  `(completion_tokens-1)/Δvllm:request_decode_time_seconds_sum` from
  `/metrics` deltas with `Δcount==1` enforced. Live stack: **92.800 tok/s**.
- **Functional cache canaries:** `scripts/replay_cap_functional.py` (final),
  earlier `replay_retention_functional.py`, `lookup_replay_functional.py` —
  N fresh ~4K prompts then repeats; parse LMCache `/metrics` for
  local-vs-external token accounting; assert repeats return the prefix-
  dependent synthetic phrase and report 3,200 local / 0 extra remote.
- **Restart probe:** `scripts/restart_probe_qwen_group.py` — full campaign:
  fresh→repeat→`docker restart` vLLM only→cold refetch→repeat. Expected
  11.927/0.629/6.770/0.628 s medians (±noise). A **cache**-service restart
  must instead cold-refill (RAM L1 is volatile; that is by design).
- **Promotion verifier:** `scripts/verify_promoted_mtp.py` — exact image ID,
  MTP3/AITER/5556/replay800 args, sole port-8092 owner, restart policy.
- **Unit tests (CPU):** `test_replay_cap.py`, `test_replay_retention.py`,
  `test_lookup_replay.py` + LMCache layout tests from patch 1 (22 total green).

## LocalMaxxing canonical run (the headline numbers)

Contract: canonical `reasoning-v1` prompt (SHA-256
`9000edaadb16fc77ab78b39917245a03d4d7585c3ba770cb045a47a0e0683445`),
greedy seed 42, thinking disabled, max 1024 / min 256 output; one excluded
warmup + three serial requests; **no restarts/tuning between**; representative
= median-decode request (measured-2 here) with all submitted metrics from that
single request. Formulas: decode `(out-1)/serverDecodeSeconds`, prefill
fresh/server-prefill, TTFT server histogram, total client wall; peak from
timestamp-scoped 1 s AMD-SMI device samples (device-wide, not
process-attributed). Result: **71.768 tok/s median decode**
(71.624–72.148), 1142.98 prefill, 246.33 ms TTFT, 64.489 GB peak, MTP
696/987 (70.5%). Note the 266-token prompt < 800 chunk → 0 prefix hits is
expected. Evidence + scripts: `results/localmaxxing-20261015/`
(`run_benchmark.py` reproduces measurement; `localmaxxing_call.py` shows
dry-run→submit flow; API credential lives in a protected file, never here).
Public run: `cmvab17cq0182le01jj43pl4b` APPROVED/verified.

## MTP depth sweep (pre-LMCache profile, ROCM_ATTN)

`results/mtp-depth-sweep/report.md` + `summary.json`: depths 1–8, one warmup
+ three samples each, late repeats for leaders. **MTP=3 winner** — 55.06/55.08
decode tok/s vs MTP=1 46.73; ~18% decode gain for <1% prefill loss. This is
why the live profile is `num_speculative_tokens: 3`.

## What counts as regression

Any of: repeat wall > 2 s for a ~4K prompt that was served twice since cache
start; repeats reporting nonzero "extra remote" tokens or zero local tokens on
second serving; `read_locked_count`/`pending_keys_count` non-draining after
idle; localmaxxing-style decode < 60 tok/s; MTP acceptance < 50%. First check
chunk-size/port pairing (5556/800 for MTP profile!) and whether anything
restarted the **cache** (empties L1) vs just vLLM.
