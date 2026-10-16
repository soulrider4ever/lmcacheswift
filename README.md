# lmcacheswift — MI210 Swift-Qwen3.8 + MTP3 + LMCache hybrid KV cache (full rebuild backup)

Complete, reproducible backup of the custom MI210 inference stack that combines
**vLLM (ROCm/MI210) + Swift-Qwen3.8-27b-W8A8 + MTP3 speculative decoding +
ROCM_AITER_FA + a remote CPU LMCache KV store**, including every local patch,
overlay, launch profile, service unit, validation harness, and measured result
from 2026-10-15/16.

Live at backup time (2026-10-16):

| Piece | Value |
|---|---|
| GPU host (CT115) | `192.168.1.106`, AMD Instinct MI210 (gfx90a/CDNA2) |
| Inference | `http://192.168.1.106:8092/v1`, model `qwen38-swift-w8a8` |
| Model | `rovangju/Swift-Qwen3.8-27b-W8A8` @ `bf37ab853e8dafbd531dee9cb6d0fbe813b69873` |
| vLLM | `0.1.dev1+g12dadcb41` (davetha/vllm MI210 fork, SHA `12dadcb4134ab41cf99b60a22e1222b7479e1a58`) |
| Base image | `local/vllm-mi210:lmcache-hybrid-3360d957` (LMCache engine-driven hybrid @ `3360d9570b29620e18ef264a411d2fbfee5f3915`) |
| Live image | `local/vllm-mi210:lmcache-aiter-mtp-qwen-replay-cap-v2-20261015` = `sha256:275f7b6b258fa87a2e22cf796ea9548bab78953ebe87ce45ff65eee1cd15bdef` |
| Live container | `qwen38-swift-w8a8-lmcache-aiter-mtp3-replay-cap-v2-20261015`, `restart=unless-stopped` |
| Spec decode | MTP, `num_speculative_tokens=3` |
| Attention | `ROCM_AITER_FA` (with one unvalidated gfx942 Triton config on gfx90a) |
| Cache host (CT125) | `192.168.1.107`, LMCache `0.5.7.dev22` @ `3e11e10812b448142c6cdb177a3058652bd826fa` |
| Live cache | `lmcache-mtp-server.service`, port **5556**, 40 GiB RAM L1/LRU, chunk **800**, active+enabled |
| Fallback cache | `lmcache-server.service`, port 5555, chunk 784 — **stopped+disabled** (retained) |
| Fallback inference | no-MTP container `qwen38-swift-w8a8-lmcache-layout-20261015` — stopped, `restart=no` |

Verified performance (unchanged live config, LocalMaxxing canonical reasoning-v1):
**median decode 71.768 tok/s**, prefill 1142.98 tok/s, TTFT 246.33 ms,
peak device-used VRAM 64.489 GB, MTP accepted/proposed 696/987 (70.5%).
Public verified run: <https://www.localmaxxing.com/en/runs/cmvab17cq0182le01jj43pl4b>
(`APPROVED`, `verifiedRun=true`, zero verification issues).

Local-prefix reuse after the final repairs: fresh ~4K prompts median **11.927 s**
→ repeat **0.629 s** (3,200 local tokens, zero extra remote); survives a
vLLM-only restart (6.770 s cold / 0.628 s repeat, remote-filled); 16K repeat
**0.790 s** with 15,200 local tokens.

## Repository map

```
README.md                    ← you are here
docs/
  reimplementation.md        ← THE step-by-step rebuild guide (read this first)
  patch-notes.md             ← per-patch rationale + full diffs are in patches/
  validation-playbook.md     ← how each number above was measured; how to re-verify
  troubleshooting.md         ← failure modes found & fixes during integration
patches/                     ← 6 diff files (contextual diffs of every customization)
overlay/
  live/                      ← EXACT .py/.json files running in the live container
                               (authoritative ground truth; hashes in reimplementation.md)
  vllm/  lmcache/  aiter/    ← per-stage candidate files by patch stage
docker/                      ← one-line-layer Dockerfiles + real build logs
systemd/                     ← CT125 cache units (live + fallback) + history
launch/                      ← exact live argv/env/binds/devices + docker-run script
scripts/                     ← canaries, restart probes, metric harnesses, staging scripts
results/
  hybrid/                    ← full raw experiment archive (layout + MTP+AITER campaign)
  localmaxxing-20261015/     ← verified benchmark evidence (payload, receipt, outputs)
  mtp-depth-sweep/           ← MTP 1–8 depth sweep report (winner = MTP=3)
```

## Golden rule

`overlay/live/` contains the exact bytes running in the working container.
If a patch file and a live file ever disagree, **the live file is truth** —
the live SHA-256s are pinned in `docs/reimplementation.md` §6.

## What this is NOT

- Not an upstream LMCache/vLLM contribution fork — these are site-local file
  overlays applied by layered `COPY` Dockerfiles (kept intentionally surgical).
- No credentials, tokens, raw `docker inspect` dumps, or Proxmox details are in
  this repo by design. Private inspect backups stay on CT115 only.
- The LMCache RAM cache is volatile: objects do **not** survive a cache-service
  or guest restart, and there is no disk L2.
