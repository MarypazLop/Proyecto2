from __future__ import annotations
from collections import defaultdict
from typing import Dict, Set, Tuple, Iterable

# ------------------ Utilidades ------------------

def _ced_from_combo(value: str) -> str:
    """Extrae la cédula cuando viene como '<ced> - <nombre>'; si ya es cédula, la retorna igual."""
    if not value:
        return ""
    parts = value.split(" - ", 1)
    return parts[0].strip()

# ------------------ Núcleo ------------------

class Kinship:
    """Calcula y expone consultas de parentesco sobre un set de personas.

    `personas` es un dict: cedula -> { ...campos... }.
    Se soporta el campo 'pareja' (o 'conyuge'/'cónyuge'/'spouse') y además
    se infiere pareja si dos personas aparecen como padre y madre de alguien.
    """

    def __init__(self, personas: Dict[str, dict]):
        # Normaliza llaves por cédula real
        self.personas: Dict[str, dict] = {}
        for ced, p in personas.items():
            true_ced = _ced_from_combo(p.get("cedula", ced)) or ced
            self.personas[true_ced] = p

        # Índices
        self.father: Dict[str, str] = {}
        self.mother: Dict[str, str] = {}
        self.children: Dict[str, Set[str]] = defaultdict(set)
        self.parents: Dict[str, Tuple[str, str]] = {}
        self.full_siblings_map: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        self.half_sibs_by_parent: Dict[str, Set[str]] = defaultdict(set)

        # Parejas: vista simple (una pareja para UI) y almacenamiento real (varias posibles)
        self.spouse_of: Dict[str, str] = {}
        self._spouses_set: Dict[str, Set[str]] = defaultdict(set)

        self._build_indices()

    # ---------- Construcción de índices ----------

    def _add_spouse_link(self, a: str, b: str) -> None:
        """Crea vínculo bidireccional de pareja, evitando vacíos y auto-enlace."""
        if not a or not b or a == b:
            return
        self._spouses_set[a].add(b)
        self._spouses_set[b].add(a)

    def _finalize_spouse_single_view(self) -> None:
        """Expone 1 pareja por persona en `spouse_of` (determinista)."""
        for ced, partners in self._spouses_set.items():
            if partners:
                self.spouse_of[ced] = sorted(partners)[0]

    def _build_indices(self) -> None:
        # Padres e hijos + inferencia de pareja por co-paternidad
        for ced, p in self.personas.items():
            padre = _ced_from_combo(p.get("padre", ""))
            madre = _ced_from_combo(p.get("madre", ""))

            if padre:
                self.father[ced] = padre
                self.children[padre].add(ced)
                self.half_sibs_by_parent[padre].add(ced)

            if madre:
                self.mother[ced] = madre
                self.children[madre].add(ced)
                self.half_sibs_by_parent[madre].add(ced)

            self.parents[ced] = (padre or "", madre or "")

            if padre and madre:
                self.full_siblings_map[(padre, madre)].add(ced)
                # Inferir pareja por co-paternidad
                self._add_spouse_link(padre, madre)

        # Pareja explícita en datos
        pareja_keys = ("pareja", "conyuge", "cónyuge", "spouse")
        for ced, p in self.personas.items():
            for k in pareja_keys:
                if p.get(k):
                    sp = _ced_from_combo(p[k])
                    if sp:
                        self._add_spouse_link(ced, sp)

        # Vista simple para UI
        self._finalize_spouse_single_view()

    # ---------- Consultas básicas ----------

    def get_parents(self, ced: str) -> Tuple[str, str]:
        return self.parents.get(ced, ("", ""))

    def get_children(self, ced: str) -> Set[str]:
        return set(self.children.get(ced, set()))

    def get_spouse(self, ced: str) -> str:
        return self.spouse_of.get(ced, "")

    # Hermanos completos (comparten ambos padres)
    def full_siblings(self, ced: str) -> set[str]:
        padre, madre = self.parents.get(ced, ("", ""))
        if not padre or not madre:
            return set()
        sibs = set(self.full_siblings_map.get((padre, madre), set()))
        sibs.discard(ced)
        return sibs

    # Medios hermanos (comparten al menos un progenitor, pero no ambos)
    def half_siblings(self, ced: str) -> Set[str]:
        padre, madre = self.parents.get(ced, ("", ""))
        cand: Set[str] = set()
        if padre:
            cand |= self.half_sibs_by_parent.get(padre, set())
        if madre:
            cand |= self.half_sibs_by_parent.get(madre, set())
        full = self.full_siblings(ced) | {ced}
        return {c for c in cand if c not in full}

    # Abuelos
    def grandparents(self, ced: str) -> Set[str]:
        padre, madre = self.get_parents(ced)
        res: Set[str] = set()
        if padre:
            res |= set(self.get_parents(padre)) - {""}
        if madre:
            res |= set(self.get_parents(madre)) - {""}
        return res

    # Nietos
    def grandchildren(self, ced: str) -> Set[str]:
        res: Set[str] = set()
        for h in self.get_children(ced):
            res |= self.get_children(h)
        return res

    # Tíos y tías (consanguíneos). Si include_inlaws=True, agrega parejas de los tíos.
    def uncles_aunts(self, ced: str, include_inlaws: bool = True) -> Set[str]:
        padre, madre = self.get_parents(ced)
        res: Set[str] = set()
        for parent in (padre, madre):
            if not parent:
                continue
            for sib in self.full_siblings(parent):
                res.add(sib)
                if include_inlaws:
                    sp = self.get_spouse(sib)
                    if sp:
                        res.add(sp)
            for hs in self.half_siblings(parent):
                res.add(hs)
                if include_inlaws:
                    sp = self.get_spouse(hs)
                    if sp:
                        res.add(sp)
        # seguridad: no incluir a los padres
        res.discard(padre)
        res.discard(madre)
        return res

    # Primos (hijos de los tíos consanguíneos)
    def cousins(self, ced: str) -> Set[str]:
        res: Set[str] = set()
        for tio in self.uncles_aunts(ced, include_inlaws=False):
            res |= self.get_children(tio)
        return res

    # Sobrinos (hijos de los hermanos completos o medios)
    def nieces_nephews(self, ced: str) -> Set[str]:
        res: Set[str] = set()
        for sib in self.full_siblings(ced) | self.half_siblings(ced):
            res |= self.get_children(sib)
        return res

    # ---------- Etiquetador simple ----------

    def relation_label(self, a: str, b: str) -> str:
        """Intenta etiquetar relación básica entre `a` y `b`.
        No distingue género en el texto (usa términos neutrales) y cubre los casos comunes.
        """
        if not a or not b:
            return ""
        if a == b:
            return "Misma persona"

        # Directas
        fa, ma = self.get_parents(b)
        if a == fa or a == ma:
            return "Progenitor/a"
        fb, mb = self.get_parents(a)
        if b == fb or b == mb:
            return "Hijo/a"

        # Cónyuges
        if self.get_spouse(a) == b or self.get_spouse(b) == a:
            return "Cónyuge / Pareja"

        # Hermanos
        if b in self.full_siblings(a):
            return "Hermano/a (completo)"
        if b in self.half_siblings(a):
            return "Medio hermano/a"

        # Abuelos / Nietos
        if a in self.grandparents(b):
            return "Abuelo/a"
        if b in self.grandparents(a):
            return "Nieto/a"

        # Tíos / Sobrinos
        if a in self.uncles_aunts(b, include_inlaws=True):
            return "Tío/Tía"
        if b in self.uncles_aunts(a, include_inlaws=True):
            return "Sobrino/a"

        # Primos
        if a in self.cousins(b) or b in self.cousins(a):
            return "Primo/a"

        return "Parentesco lejano o no determinado"

    # ---------- Ayudas de presentación ----------

    def name_of(self, ced: str) -> str:
        p = self.personas.get(ced, {})
        return p.get("nombre", ced)

    def label_set(self, ceds: Iterable[str]) -> str:
        # Devuelve una lista bonita tipo "123 - Ana; 456 - Luis"
        return "; ".join(f"{c} - {self.name_of(c)}" for c in sorted(set(ceds)))


__all__ = ["Kinship"]
