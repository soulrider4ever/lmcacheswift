# lmcacheswift — MI210 Swift-Qwen3.8 MTP5 + LMCache `kv_producer` target

This repository preserves the last validated MI210 hybrid stack and tracks the
requested target launch profile: **MTP5 + LMCache `kv_role=kv_producer`**. The
new profile is source-only; the combined MTP5/producer runtime has not been
deployed or validated. The previously measured MTP5 speed result used no
LMCache, so it does not establish performance for the combined profile. See the
[target-profile notes](docs/mtp5-kv-producer-profile.md).

## Last validated hybrid deployment snapshot

MTP3 + `kv_role=kv_both`, captured 2026-10-16 after the bounded-transfer repair.
See the [repair details](docs/bounded-transfer-fix-20261016.md). Historical
benchmark figures below apply to that profile, not to the new target.

| Piece | Last validated hybrid value |
|---|---|
| GPU host (CT115) | `192.168.1.106`, AMD Instinct MI210 (gfx90a/CDNA2) |
| Inference | `http://192.168.1.106:8092/v1`, model `qwen38-swift-w8a8` |
| Model | `rovangju/Swift-Qwen3.8-27b-W8A8` @ `bf37ab853e8dafbd531dee9cb6d0fbe813b69873` |
| vLLM | `0.1.dev1+g12dadcb41` (davetha/vllm MI210 fork, SHA `12dadcb4134ab41cf99b60a22e1222b7479e1a58`) |
| Base image | `local/vllm-mi210:lmcache-hybrid-3360d957` (LMCache engine-driven hybrid @ `3360d9570b29620e18ef264a411d2fbfee5f3915`) |
| Image | `local/vllm-mi210:lmcache-mtp3-bounded-transfer-v1-20261016` = `sha256:76acbdb4186b2311c65f29287f1e8a6d60e59f086cb181bcffaf184092cf280c` |
| Container | `qwen38-swift-w8a8-lmcache-mtp3-bounded-v1-20261016`, `restart=unless-stopped` |
| Decode/cache role | MTP depth 3, `kv_role=kv_both` |
| Attention | `ROCM_AITER_FA` (with one unvalidated gfx942 Triton config on gfx90a) |
| Cache host (CT125) | `192.168.1.107`, LMCache `0.5.7.dev22` @ `3e11e10812b448142c6cdb177a3058652bd826fa` |
| Cache service | `lmcache-mtp-server.service`, port **5556**, 40 GiB RAM L1/LRU, chunk **800**, active+enabled at capture |
| Fallback cache | `lmcache-server.service`, port 5555, chunk 784 — **stopped+disabled** (retained) |
| Fallback inference | no-MTP container `qwen38-swift-w8a8-lmcache-layout-20261015` — stopped, `restart=no` |

Last verified hybrid performance (LocalMaxxing canonical reasoning-v1):
**median decode 71.768 tok/s**, prefill 1142.98 tok/s, TTFT 246.33 ms,
peak device-used VRAM 64.489 GB, MTP accepted/proposed 696/987 (70.5%). Public
verified run: <https://www.localmaxxing.com/en/runs/cmvab17cq0182le01jj43pl4b>
(`APPROVED`, `verifiedRun=true`, zero verification issues).

Validated hybrid prefix reuse after the repairs: fresh ~4K prompts median
**11.927 s** → repeat **0.629 s** (3,200 local tokens, zero extra remote);
after a vLLM-only restart, 6.770 s cold / 0.628 s repeat; 16K repeat **0.790 s**
with 15,200 local tokens.

The separate no-LMCache MTP5 run measured 74.234 tok/s median versus 71.488
tok/s for its matched no-LMCache MTP3 baseline (+3.84%). Both reached the
1,024-token cap; their output hashes differed. This is speed evidence, not
answer-quality equivalence or validation of the LMCache producer profile. See
<https://www.localmaxxing.com/en/runs/cmvbnnl7401mmle0192pjwbqg>.

## Repository map

```
README.md                    ← you are here
docs/
  mtp5-kv-producer-profile.md ← requested target settings and validation boundary
  reimplementation.md        ← rebuild guide for the validated MTP3 hybrid archive
  patch-notes.md             ← per-patch rationale + full diffs are in patches/
  validation-playbook.md     ← how historical results were measured
  troubleshooting.md         ← failure modes found & fixes during integration
patches/                     ← contextual diffs of local customizations
overlay/
  live/                      ← exact bytes from the validated MTP3/kv_both stack
  vllm/  lmcache/  aiter/    ← per-stage candidate files by patch stage
docker/                      ← Dockerfiles + captured build logs
systemd/                     ← CT125 cache units (validated + fallback) + history
launch/
  docker-run-mtp5-kv-producer.sh ← requested MTP5/producer target launcher
  mtp5-kv-producer-args.json     ← matching machine-readable target args
  docker-run-mtp3-validated.sh   ← preserved MTP3 hybrid launcher
  mtp3-validated-args.json       ← preserved MTP3 hybrid args
scripts/                     ← canaries, restart probes, metric harnesses, staging scripts
results/                     ← historical validation and benchmark artifacts
```

## Golden rule

`overlay/live/` contains the exact bytes from the last validated MTP3/kv_both
hybrid container. It does not validate the new MTP5/producer target; the target
launch settings are separate. The archived live SHA-256s are pinned in
`docs/reimplementation.md` §6.

## What this is NOT

- Not an upstream LMCache/vLLM contribution fork — these are site-local file
  overlays applied by layered `COPY` Dockerfiles (kept intentionally surgical).
- No credentials, tokens, raw `docker inspect` dumps, or Proxmox details are in
  this repo by design. Private inspect backups stay on CT115 only.
- The LMCache RAM cache is volatile: objects do **not** survive a cache-service
  or guest restart, and there is no disk L2.
