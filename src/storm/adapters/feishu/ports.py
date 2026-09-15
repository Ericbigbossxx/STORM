"""Technology-neutral port for the STORM Feishu ledger."""

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class LedgerObjectRef:
    kind: str
    external_id: str


class FeishuLedgerPort(Protocol):
    """Boundary implemented later by MCP or Open API without changing the domain."""

    def inspect_schema(self, base_ref: LedgerObjectRef) -> Mapping[str, object]: ...

    def create_base(self, name: str) -> LedgerObjectRef: ...

    def create_table(self, base_ref: LedgerObjectRef, spec: Mapping[str, object]) -> LedgerObjectRef: ...

    def create_field(
        self,
        base_ref: LedgerObjectRef,
        table_ref: LedgerObjectRef,
        spec: Mapping[str, object],
    ) -> LedgerObjectRef: ...

    def create_view(
        self,
        base_ref: LedgerObjectRef,
        table_ref: LedgerObjectRef,
        spec: Mapping[str, object],
    ) -> LedgerObjectRef: ...

    def list_records(
        self,
        base_ref: LedgerObjectRef,
        table_ref: LedgerObjectRef,
    ) -> Sequence[Mapping[str, object]]: ...

    def create_record(
        self,
        base_ref: LedgerObjectRef,
        table_ref: LedgerObjectRef,
        fields: Mapping[str, object],
    ) -> LedgerObjectRef: ...
