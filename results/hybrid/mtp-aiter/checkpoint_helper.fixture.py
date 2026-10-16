# Exact installed vLLM helper: 0.1.dev1+g12dadcb41, kv_cache_interface.py
def get_mamba_prefill_checkpoint_position(
    num_tokens: int,
    hash_block_size: int,
    drop_eagle_block: bool,
) -> int:
    """Return the reusable Mamba checkpoint boundary for a prefill."""
    checkpoint_position = (num_tokens - 1) // hash_block_size * hash_block_size
    if drop_eagle_block:
        checkpoint_position -= hash_block_size
    return max(checkpoint_position, 0)
