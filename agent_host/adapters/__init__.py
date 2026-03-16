"""Adapters layer — Ring 3 of the Hexagonal Architecture.

Concrete implementations of port interfaces defined in
``agent_host.contracts.ports``.  Each adapter handles external I/O,
error translation, retries, and connection management.

Adapters import only from ``agent_host.contracts`` (Ring 1).
They never import from ``core/`` (Ring 2) or from sibling adapters.
"""
