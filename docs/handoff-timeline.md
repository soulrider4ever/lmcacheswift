# Handoff Timeline — how this came to be (2026-10-15 → 10-16 ET)

Compressed narrative for whoever picks this up. Raw logs throughout
`results/hybrid/` tell the full story; this is the signpost version.

1. **Baseline.** MI210 (CT115) serving Swift-Qwen3.8-27b-W8A8 via the
   davetha/vllm MI210 fork; AITER FA had just been qualified; an MTP depth
   sweep (results/mtp-depth-sweep/) selected **MTP=3** (55.06/55.08 decode
   tok/s, ~18% over MTP=1 for <1% prefill).
2. **Goal.** Add CPU-side LMCache remote KV store (CT125) for cross-restart
   prompt reuse, without losing MTP3 or AITER FA.
3. **LMCache hybrid image.** Built `lmcache-hybrid-3360d957` (engine-driven MP
   connector + hybrid lineage incl. PR4410 work). No-MTP bring-up needed the
   layout fix (patch 1) → `lmcache-layout-20261015`; no-MTP profile went live
   first (chunk 784 / port 5555).
4. **MTP+AITER attempt.** With MTP3: local reuse zero. Diagnostic chain:
   group-detection patch (2) → coordinator split (3) → both still zero →
   read-only fixedpoint diag found the Mamba shifted-checkpoint retention
   mismatch → retention patch (4) restored fresh local hits → lookup-replay
   knob (5) stopped double-fetch → replay-cap locks/accounting (6) made it
   stable. Candidate chain: qwen-group → coordinator → [diag] →
   replay-retention → lookup-replay → replay-cap → **replay-cap-v2 (live)**.
5. **Validation.** 41 bounded requests (text/vision/tools/counting/16K/
   concurrency/red-blue image-KV separation) + CPU tests; restart campaign
   medians 11.927/0.629/6.770/0.628 s; owner promoted MTP profile to default
   (`unless-stopped`); no-MTP kept stopped as fallback.
6. **Capacity.** Owner approved L1 resize 8→**40 GiB** (chunk 800 preserved);
   persistent `lmcache-mtp-server.service` enabled; ≈23 GiB RAM headroom after.
7. **Publication.** Canonical LocalMaxxing reasoning-v1 run on the unchanged
   live stack: dry-run valid/verified, submitted, **APPROVED + verified, zero
   issues** — run `cmvab17cq0182le01jj43pl4b` (public): median decode
   **71.768 tok/s**, prefill 1,142.98, TTFT 246.33 ms, MTP 696/987, peak
   device VRAM 64.489 GB; post-run health unchanged (same PID, 0 restarts).
8. **This backup.** Repo `lmcacheswift` assembled 2026-10-16 with all patches,
   live overlay bytes (hash-pinned), units, launch profile, harnesses, and
   every measured artifact, for full reimplementation from bare hosts.

**Pending/declared-open as of backup:** upstreaming patches 1–3; tuning the
gfx90a AITER copy; full-256K / sustained-concurrency / eviction-pressure
validation; optional disk-L2 for the cache (currently RAM-only by choice).
