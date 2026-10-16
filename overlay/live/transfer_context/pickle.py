# SPDX-License-Identifier: Apache-2.0
"""Pickle-based EngineDrivenContext implementation for multiprocess mode."""

# Standard
from dataclasses import replace
from math import prod
import pickle

# Third Party
import torch

# First Party
from lmcache.v1.multiprocess.custom_types import IPCCacheServerKey
from lmcache.v1.multiprocess.transfer_context.base import (
    EngineDrivenContext,
    EngineDrivenContextMetadata,
)
from lmcache.v1.multiprocess.transport.base import RequestClient


class EngineDrivenContextPickle(EngineDrivenContext):
    """Pickle-based implementation of :class:`EngineDrivenContext`.

    Transport mechanism:
    - **Store**: ``prepare_store`` sends ``PREPARE_STORE`` (returns empty slots
      for pickle mode); ``commit_store`` serialises chunks and sends
      ``COMMIT_STORE``.
    - **Retrieve**: ``prepare_retrieve`` sends ``PREPARE_RETRIEVE`` and
      deserialises the returned bytes; ``commit_retrieve`` sends
      ``COMMIT_RETRIEVE`` (no-op for pickle).
    """

    def __init__(
        self,
        metadata: EngineDrivenContextMetadata,
        req_client: RequestClient,
        mq_timeout: float,
    ) -> None:
        super().__init__(metadata, req_client, mq_timeout)

    # Leave ample room below MessagePack's 4-GiB binary-object limit.
    MAX_PAYLOAD_BYTES = 512 * 1024 * 1024

    def _batch_keys(self, key):
        layouts = self.metadata.group_layouts or [self.metadata.layout_desc]
        chunk_tokens = self.metadata.chunk_tokens
        if chunk_tokens <= 0:
            raise ValueError("Pickle batching requires logical chunk_tokens")
        if key.start % chunk_tokens or key.end % chunk_tokens:
            raise ValueError("Pickle transfer range must be chunk aligned")
        # Include conservative pickle metadata/storage overhead per tensor.
        per_chunk = sum(
            prod(shape) * torch.empty((), dtype=dtype).element_size() + 65536
            for layout in layouts
            for shape, dtype in zip(layout.shapes, layout.dtypes, strict=True)
        )
        if per_chunk > self.MAX_PAYLOAD_BYTES:
            raise ValueError("One LMCache chunk exceeds the pickle RPC budget")
        batch_chunks = max(1, self.MAX_PAYLOAD_BYTES // max(1, per_chunk))
        span = batch_chunks * chunk_tokens
        for start in range(key.start, key.end, span):
            yield replace(key, start=start, end=min(key.end, start + span))

    def prepare_store(
        self, key: IPCCacheServerKey, instance_id: int
    ) -> tuple[list[torch.Tensor], list[int]] | None:
        """Send PREPARE_STORE RPC. For pickle, returns no pre-allocated buffers."""
        future = self.req_client.prepare_store(key, instance_id)
        try:
            future.result(timeout=self.mq_timeout)
        except TimeoutError:
            pass
        return None

    def commit_store(
        self,
        key: IPCCacheServerKey,
        instance_id: int,
        chunks: "list[torch.Tensor] | list[list[torch.Tensor]]",
    ) -> bool:
        """Serialize chunks and send via COMMIT_STORE.

        Single-group callers pass a flat chunk list; multi-group callers pass
        a group-major ``chunks[group][chunk]`` list (the server side picks the
        shape from its registered group count).

        Returns:
            ``True`` on success, ``False`` on failure or timeout.
        """
        grouped = bool(self.metadata.group_layouts and len(self.metadata.group_layouts) > 1)
        groups = chunks if grouped else [chunks]
        count = (key.end - key.start) // self.metadata.chunk_tokens
        if len(groups) != (len(self.metadata.group_layouts) if grouped else 1):
            raise ValueError("Pickle store group count mismatch")
        if any(len(group) != count for group in groups):
            raise ValueError("Pickle store chunk count mismatch")
        for batch_key in self._batch_keys(key):
            lo = (batch_key.start - key.start) // self.metadata.chunk_tokens
            hi = (batch_key.end - key.start) // self.metadata.chunk_tokens
            batch = [group[lo:hi] for group in groups]
            # Clone to avoid serializing an oversized shared backing storage.
            batch = [[t.clone() for t in group] for group in batch]
            serialised = pickle.dumps(batch if grouped else batch[0])
            if len(serialised) > self.MAX_PAYLOAD_BYTES:
                raise ValueError("Serialized pickle batch exceeds RPC budget")
            future = self.req_client.commit_store(batch_key, instance_id, serialised)
            try:
                if not future.result(timeout=self.mq_timeout):
                    return False
            except TimeoutError:
                return False
        return True

    def prepare_retrieve(
        self, key: IPCCacheServerKey, instance_id: int
    ) -> list[torch.Tensor] | None:
        """Send PREPARE_RETRIEVE and deserialize the response data.

        Returns:
            Chunks on hit, or None on miss/timeout.
        """
        groups = self._retrieve_batches(key, instance_id, grouped=False)
        return None if groups is None else groups[0]

    def prepare_retrieve_multigroup(
        self, key: IPCCacheServerKey, instance_id: int
    ) -> list[list[torch.Tensor]] | None:
        """Retrieve bounded group-major RPCs, retaining all-or-nothing semantics."""
        return self._retrieve_batches(key, instance_id, grouped=True)

    def _retrieve_batches(self, key, instance_id, grouped):
        group_count = len(self.metadata.group_layouts or []) if grouped else 1
        groups = [[] for _ in range(group_count)]
        for batch_key in self._batch_keys(key):
            future = self.req_client.prepare_retrieve(batch_key, instance_id)
            try:
                response = future.result(timeout=self.mq_timeout)
            except TimeoutError:
                return None
            if not response.success or not response.data:
                return None
            if len(response.data) > self.MAX_PAYLOAD_BYTES:
                raise ValueError("Received pickle batch exceeds RPC budget")
            payload = pickle.loads(response.data)
            batch = payload if grouped else [payload]
            expected = (batch_key.end - batch_key.start) // self.metadata.chunk_tokens
            if len(batch) != group_count or any(len(g) != expected for g in batch):
                return None
            for target, source in zip(groups, batch, strict=True):
                target.extend(source)
        return groups

    def commit_retrieve(self, key: IPCCacheServerKey, instance_id: int) -> bool:
        """Send COMMIT_RETRIEVE (no-op for pickle path)."""
        future = self.req_client.commit_retrieve(key, instance_id)
        try:
            future.result(timeout=self.mq_timeout)
        except TimeoutError:
            pass
        return True

    def close(self) -> None:
        """No-op: the pickle path holds no persistent resources."""
