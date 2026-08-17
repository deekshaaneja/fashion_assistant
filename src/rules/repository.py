"""Typed, cached repositories over the seed catalogs. Thin -- no business
logic here, just load + expose + resolve-by-name."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.domain.models.consumption import ConsumptionRule
from src.domain.models.embellishment import EmbellishmentTechnique
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment, Silhouette
from src.rules.loader import load_seed


class FabricRepository:
    def __init__(self) -> None:
        raw = load_seed("fabrics.yaml")["fabrics"]
        self._all: tuple[Fabric, ...] = tuple(Fabric(**row) for row in raw)
        self._by_id = {f.id: f for f in self._all}

    def all(self) -> tuple[Fabric, ...]:
        return self._all

    def get(self, fabric_id: str) -> Fabric | None:
        return self._by_id.get(fabric_id)

    def resolve(self, name: str) -> FabricResolution:
        """Never raises -- degrades to an unresolved generic profile rather
        than fabricating a match. `name` matching is case/space-insensitive
        exact match on id/name first, then a substring/alias pass."""
        normalized = name.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in self._by_id:
            return FabricResolution(profile=self._by_id[normalized], confidence=0.95, method="exact")

        for fabric in self._all:
            if fabric.name.lower().replace(" ", "_") == normalized:
                return FabricResolution(profile=fabric, confidence=0.9, method="exact")

        # partial: the declared name contains or is contained by a known fabric id/name
        # (handles inputs like "embroidered organza" resolving to the "organza" family).
        for fabric in self._all:
            if fabric.id in normalized or normalized in fabric.id:
                return FabricResolution(profile=fabric, confidence=0.6, method="partial")

        return FabricResolution(profile=_unknown_fabric(), confidence=0.15, method="unresolved")


@dataclass(frozen=True)
class FabricResolution:
    profile: Fabric
    confidence: float
    method: str  # exact | partial | unresolved


def _unknown_fabric() -> Fabric:
    return Fabric(
        id="unknown_fabric",
        name="Unknown fabric",
        category="unknown",
        notes="Fabric name did not resolve against the seed catalog -- properties are unknown, not assumed.",
    )


class GarmentRepository:
    def __init__(self) -> None:
        raw = load_seed("garments.yaml")["garments"]
        self._all: tuple[Garment, ...] = tuple(Garment(**row) for row in raw)
        self._by_id = {g.id: g for g in self._all}

    def all(self) -> tuple[Garment, ...]:
        return self._all

    def get(self, garment_id: str) -> Garment | None:
        return self._by_id.get(garment_id)


class SilhouetteRepository:
    def __init__(self) -> None:
        raw = load_seed("silhouettes.yaml")["silhouettes"]
        self._all: tuple[Silhouette, ...] = tuple(Silhouette(**row) for row in raw)
        self._by_id = {s.id: s for s in self._all}

    def all(self) -> tuple[Silhouette, ...]:
        return self._all

    def get(self, silhouette_id: str) -> Silhouette | None:
        return self._by_id.get(silhouette_id)

    def for_garment(self, garment_id: str) -> list[Silhouette]:
        return [s for s in self._all if garment_id in s.applicable_garment_ids]


class ConsumptionRuleRepository:
    def __init__(self) -> None:
        raw = load_seed("consumption_rules.yaml")["consumption_rules"]
        self._all: tuple[ConsumptionRule, ...] = tuple(ConsumptionRule(**row) for row in raw)
        self._by_key = {(r.garment_id, r.silhouette_id): r for r in self._all}

    def get(self, garment_id: str, silhouette_id: str) -> ConsumptionRule | None:
        return self._by_key.get((garment_id, silhouette_id))

    def all(self) -> tuple[ConsumptionRule, ...]:
        return self._all


class EmbellishmentRepository:
    def __init__(self) -> None:
        raw = load_seed("embellishments.yaml")["embellishments"]
        self._all: tuple[EmbellishmentTechnique, ...] = tuple(EmbellishmentTechnique(**row) for row in raw)
        self._by_id = {e.id: e for e in self._all}

    def all(self) -> tuple[EmbellishmentTechnique, ...]:
        return self._all

    def get(self, embellishment_id: str) -> EmbellishmentTechnique | None:
        return self._by_id.get(embellishment_id)

    def suitable_for_tolerance(self, tolerance: str) -> list[EmbellishmentTechnique]:
        order = ["low", "medium", "high"]
        max_idx = order.index(tolerance) if tolerance in order else 0
        return [e for e in self._all if order.index(e.min_fabric_embellishment_tolerance) <= max_idx]


@lru_cache
def get_fabric_repository() -> FabricRepository:
    return FabricRepository()


@lru_cache
def get_garment_repository() -> GarmentRepository:
    return GarmentRepository()


@lru_cache
def get_silhouette_repository() -> SilhouetteRepository:
    return SilhouetteRepository()


@lru_cache
def get_consumption_rule_repository() -> ConsumptionRuleRepository:
    return ConsumptionRuleRepository()


@lru_cache
def get_embellishment_repository() -> EmbellishmentRepository:
    return EmbellishmentRepository()
