"""Merkle tree helpers for evidence provenance.

Provides a deterministic, order-independent Merkle root over a set of
32-byte evidence leaf hashes.  The tree is built by sorting the leaves
before hashing pairs, which makes the root independent of insertion order.
"""

from __future__ import annotations

from .eip712 import keccak256


def evidence_merkle_root(leaves: list[bytes]) -> bytes:
    """Compute a deterministic Merkle root from a list of 32-byte leaf hashes.

    The algorithm sorts the leaves lexicographically before pairing, ensuring
    that the root is order-independent: ``root([a, b]) == root([b, a])``.

    For an odd number of nodes at any level, the last node is duplicated
    (standard Merkle padding).

    Args:
        leaves: List of 32-byte keccak256 digests.

    Returns:
        A 32-byte Merkle root digest.

    Raises:
        ValueError: If any leaf is not exactly 32 bytes.
    """
    if not leaves:
        raise ValueError("evidence_merkle_root requires at least one leaf")

    for i, leaf in enumerate(leaves):
        if len(leaf) != 32:
            raise ValueError(
                f"Leaf at index {i} must be 32 bytes, got {len(leaf)}"
            )

    # Sort to guarantee order-independence.
    level = sorted(leaves)

    while len(level) > 1:
        next_level: list[bytes] = []
        # Pad with duplicate if odd count.
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        for i in range(0, len(level), 2):
            combined = level[i] + level[i + 1]
            next_level.append(keccak256(combined))
        level = next_level

    return level[0]
