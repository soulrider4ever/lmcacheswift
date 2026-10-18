#!/usr/bin/env bash
# Archived launch definition for the prior MTP3+LMCache profile on CT115.
# Captured from the MTP3 profile on 2026-10-16; retained as historical configuration.
# Non-secret fields only (no raw inspect JSON is stored in this repo).
# Normally you never need this: the live container is named with
# restart=unless-stopped. Use it only after recreating from scratch.
set -euo pipefail
IMAGE="${IMAGE:-local/vllm-mi210:lmcache-mtp3-background-commit-v1-20261016}"
NAME="qwen38-swift-w8a8-lmcache-mtp3-background-v1-20261016"

docker run -d --name "$NAME" \
  --device /dev/kfd \
  --device /dev/dri \
  -v /home/ubuntu/mi210-inductor-cache:/cache/inductor \
  -v /home/ubuntu/models/swift-qwen38-27b-w8a8:/models/swift-qwen38:ro \
  -v /home/ubuntu/mi210-triton-cache:/cache/triton \
  -v /home/ubuntu/mi210-w8-cache:/cache/vllm \
  -v /home/ubuntu/mi210-aiter-cache-dflash:/opt/aiter-jit \
  -v /home/ubuntu/mi210-aiter-cache:/cache/aiter \
  -e 'VLLM_ROCM_USE_AITER=1' \
  -e 'VLLM_CACHE_ROOT=/cache/vllm' \
  -e 'TORCHINDUCTOR_CACHE_DIR=/cache/inductor' \
  -e 'AITER_ROOT_DIR=/cache/aiter' \
  -e 'HIP_FORCE_DEV_KERNARG=1' \
  -e 'TRITON_CACHE_DIR=/cache/triton' \
  -e 'AITER_JIT_DIR=/opt/aiter-jit' \
  -e 'HSA_NO_SCRATCH_RECLAIM=1' \
  -e 'GPU_PINNED_MIN_XFER_SIZE=67108864' \
  -e 'CCACHE_DIR=/ccache' \
  -e 'PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/bin:/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/lib/llvm/bin:/opt/python/lib/python3.14/site-packages/_rocm_sdk_core/bin:/opt/python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  -e 'PYTORCH_ROCM_ARCH=gfx90a' \
  -e 'AITER_ROCM_ARCH=gfx942;gfx950' \
  -e 'MAX_JOBS=8' \
  -e 'DEBIAN_FRONTEND=noninteractive' \
  -e 'UV_PYTHON=/opt/python/bin/python' \
  -e 'UV_HTTP_TIMEOUT=500' \
  -e 'UV_INDEX_STRATEGY=unsafe-best-match' \
  -e 'UV_LINK_MODE=copy' \
  -e 'PIP_EXTRA_INDEX_URL=https://stable.repo.amd.com/rocm/whl-next' \
  -e 'SITE_PACKAGES=/opt/python/lib/python3.14/site-packages' \
  -e 'ROCM_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel' \
  -e 'ROCM_HOME=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel' \
  -e 'HIP_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel' \
  -e 'HIP_CLANG_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/lib/llvm/bin' \
  -e 'HIP_DEVICE_LIB_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_core/lib/llvm/amdgcn/bitcode' \
  -e 'LD_LIBRARY_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/lib:/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/lib/rocm_sysdeps/lib:/opt/python/lib/python3.14/site-packages/_rocm_sdk_core/lib:/opt/python/lib/python3.14/site-packages/_rocm_sdk_core/lib/rocm_sysdeps/lib' \
  -e 'PYTHONPATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_core/share/amd_smi:' \
  -e 'CMAKE_PREFIX_PATH=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel/lib/cmake:' \
  -e 'CMAKE_HIP_COMPILER_ROCM_ROOT=/opt/python/lib/python3.14/site-packages/_rocm_sdk_devel' \
  -e 'RAY_EXPERIMENTAL_NOSET_ROCR_VISIBLE_DEVICES=1' \
  -e 'RAY_EXPERIMENTAL_NOSET_HIP_VISIBLE_DEVICES=1' \
  -e 'ROCM_VERSION=10.0.0' \
  -e 'TOKENIZERS_PARALLELISM=false' \
  -e 'SAFETENSORS_FAST_GPU=1' \
  -e 'KINETO_CONFIG=/app/libkineto.conf' \
  -e 'VLLM_TARGET_DEVICE=rocm' \
  -e 'CCACHE_COMPILERCHECK=content' \
  -e 'CCACHE_MAXSIZE=100G' \
  -e 'CCACHE_DEPEND=1' \
  -e 'LMCACHE_TRACK_USAGE=false' \
  -e 'LMCACHE_DISABLE_BANNER=1' \
  -e 'VLLM_NO_USAGE_STATS=1' \
  -e 'DO_NOT_TRACK=1' \
  --group-add video \
  --security-opt seccomp=unconfined \
  --security-opt label=disable \
  --ipc host \
  --shm-size 17179869184 \
  --network bridge -p 8092:8092 \
  --restart unless-stopped \
  "$IMAGE" \
  vllm \
  serve \
  /models/swift-qwen38 \
  --served-model-name \
  qwen38-swift-w8a8 \
  --trust-remote-code \
  --tensor-parallel-size \
  1 \
  --max-num-seqs \
  8 \
  --max-num-batched-tokens \
  1567 \
  --max-model-len \
  262144 \
  --dtype \
  bfloat16 \
  --kv-cache-dtype \
  auto \
  --gpu-memory-utilization \
  0.99 \
  --attention-backend \
  ROCM_AITER_FA \
  --async-scheduling \
  --compilation-config \
  '{"cudagraph_mode":"FULL_DECODE_ONLY"}' \
  --enable-chunked-prefill \
  --reasoning-parser \
  qwen3 \
  --host \
  0.0.0.0 \
  --port \
  8092 \
  --seed \
  42 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser \
  qwen3_xml \
  --kv-transfer-config \
  '{"kv_connector": "LMCacheMPConnector", "kv_connector_module_path": "lmcache.integration.vllm.lmcache_mp_connector", "kv_role": "kv_both", "kv_connector_extra_config": {"lmcache.mp.host": "tcp://192.168.1.107", "lmcache.mp.port": 5556, "lmcache.mp.mp_transfer_mode": "engine_driven", "lmcache.mp.isolated_ipc": true, "lmcache.mp.lookup_replay_tokens": 800}}' \
  --mamba-cache-mode \
  align \
  --speculative-config \
  '{"method": "mtp", "num_speculative_tokens": 3}' >/dev/null

