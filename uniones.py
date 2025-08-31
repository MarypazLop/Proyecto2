# uniones.py
from __future__ import annotations

import threading
import time
import random
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import os
import io
import shutil

Persona   = Dict[str, Any]
OnChange  = Optional[Callable[[], None]]
OnEvent   = Optional[Callable[[str, Dict], None]]
GetYearCB = Optional[Callable[[], int]]  # para sincronizar con BirthdayEngine si se pasa


# ---------- Utilidades ----------
def _safe_int(x, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return default

def _parse_date_any(s: str) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, f).date()
        except Exception:
            pass
    return None

def _id_from_combo(text: str) -> str:
    """'123 - Nombre' -> '123' ; '123' -> '123' ; '' -> ''"""
    if not text:
        return ""
    t = str(text).strip()
    return t.split(" - ")[0].strip()

def _idname(ced: str, nombre: str) -> str:
    return f"{ced} - {nombre or ''}".strip()

def _norm_gender(g: str) -> Optional[str]:
    if not g:
        return None
    t = str(g).strip().lower()
    # Acepta formatos comunes
    if t in {"m", "masculino", "h", "hombre"}:
        return "M"
    if t in {"f", "femenino", "mujer"}:
        return "F"
    # heurística por inicial
    if t.startswith(("m", "h")):
        return "M"
    if t.startswith(("f", "muj")):
        return "F"
    return None

def _is_dead(p: Persona, year_now: int) -> bool:
    raw = str(p.get("falle", "") or "").strip().lower()
    if not raw:
        return False
    if raw in ("si", "sí", "true", "1", "y", "yes"):
        return True
    if raw in ("no", "false", "0", "n"):
        return False
    d = _parse_date_any(raw)
    return bool(d and year_now >= d.year)

def _age_of(p: Persona, year_now: int) -> Optional[int]:
    e = _safe_int(p.get("edad"), None)
    if e is not None:
        return max(0, e)
    d = _parse_date_any(p.get("nac", ""))
    return max(0, year_now - d.year) if d else None

def _list_from_csv(val: Any) -> List[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(x).strip().lower() for x in val if str(x).strip()]
    return [x.strip().lower() for x in str(val).split(",") if x.strip()]

def _compute_compatibility(a: Persona, b: Persona) -> float:
    """
    Índice 0..1:
    - Afinidades/intereses en común (hasta 0.8)
    - Bonificación cercanía de edad (0.1)
    - Bonificación misma provincia (0.1)
    Considera *al menos dos tipos de afinidad* si existen en datos.
    """
    A = set(_list_from_csv(a.get("afinidades") or a.get("intereses")))
    B = set(_list_from_csv(b.get("afinidades") or b.get("intereses")))
    if A or B:
        inter = len(A & B)
        union = max(1, len(A | B))
        aff = inter / union
        if inter >= 2:
            aff = min(1.0, aff + 0.1)
    else:
        aff = 0.5  # desconocido → término medio

    ea = _age_of(a, datetime.now().year) or 0
    eb = _age_of(b, datetime.now().year) or 0
    age_bonus = 1.0 - min(1.0, (abs(ea - eb) / 20.0))   # 0..1
    age_bonus *= 0.1

    prov_bonus = 0.1 if (a.get("provincia") and a.get("provincia") == b.get("provincia")) else 0.0
    score = 0.8 * aff + age_bonus + prov_bonus
    return max(0.0, min(1.0, score))


# ---------- Reglas anti-incesto ampliadas ----------
def _parents_of(p: Persona) -> Tuple[str, str]:
    return (_id_from_combo(p.get("padre", "")), _id_from_combo(p.get("madre", "")))

def _build_ancestors(personas: Dict[str, Persona], start_id: str, depth: int = 2) -> set:
    """
    Retorna IDs de ancestros hasta 'depth' generaciones.
    depth=1 -> padres; depth=2 -> abuelos también.
    """
    seen = set()
    frontier = {start_id}
    for _ in range(depth):
        nxt = set()
        for pid in list(frontier):
            p = personas.get(pid)
            if not p:
                continue
            fa, mo = _parents_of(p)
            for x in (fa, mo):
                if x and x not in seen:
                    seen.add(x)
                    nxt.add(x)
        frontier = nxt
        if not frontier:
            break
    return seen

def _siblings(personas: Dict[str, Persona], a_id: str, b_id: str) -> bool:
    A = personas.get(a_id) or {}
    B = personas.get(b_id) or {}
    ap = _parents_of(A)
    bp = _parents_of(B)
    # hermanos o medio hermanos (comparten padre o madre)
    if (ap[0] and ap[0] == bp[0]) or (ap[1] and ap[1] == bp[1]):
        return True
    # si ambos padres coinciden y existen
    return ap == bp and any(ap)

def _aunt_uncle_niece_nephew(personas: Dict[str, Persona], a_id: str, b_id: str) -> bool:
    """True si A es tío/tía de B o B de A."""
    # A es hermano de un padre de B  -> tío/tía
    B = personas.get(b_id) or {}
    bp = set([_id_from_combo(B.get("padre","")), _id_from_combo(B.get("madre",""))])
    for parent_id in [x for x in bp if x]:
        if _siblings(personas, a_id, parent_id):
            return True
    # simétrico
    A = personas.get(a_id) or {}
    ap = set([_id_from_combo(A.get("padre","")), _id_from_combo(A.get("madre",""))])
    for parent_id in [x for x in ap if x]:
        if _siblings(personas, b_id, parent_id):
            return True
    return False

def _first_cousins(personas: Dict[str, Persona], a_id: str, b_id: str) -> bool:
    """Primos hermanos: los padres de A y B son hermanos entre sí."""
    A = personas.get(a_id) or {}
    B = personas.get(b_id) or {}
    ap = [x for x in _parents_of(A) if x]
    bp = [x for x in _parents_of(B) if x]
    for pa in ap:
        for pb in bp:
            if _siblings(personas, pa, pb):
                return True
    return False

def _genetically_safe(personas: Dict[str, Persona], a: Persona, b: Persona, a_id: str, b_id: str) -> bool:
    """Reglas para evitar consanguinidad directa y de 1er grado extendida."""
    # padre/madre con hijo
    for parent, child in ((a, b), (b, a)):
        pid = _id_from_combo(parent.get("cedula","") or (a_id if parent is a else b_id))
        if _id_from_combo(child.get("padre","")) == pid:
            return False
        if _id_from_combo(child.get("madre","")) == pid:
            return False

    # hermanos o medio hermanos
    if _siblings(personas, a_id, b_id):
        return False

    # abuelo/a ↔ nieto/a (ancestros hasta 2 generaciones)
    a_anc = _build_ancestors(personas, a_id, depth=2)
    b_anc = _build_ancestors(personas, b_id, depth=2)
    if (a_id in b_anc) or (b_id in a_anc):
        return False

    # tíos ↔ sobrinos
    if _aunt_uncle_niece_nephew(personas, a_id, b_id):
        return False

    # primos hermanos
    if _first_cousins(personas, a_id, b_id):
        return False

    return True


def _is_single(p: Persona) -> bool:
    """Disponible: sin pareja actual. Viudo/a permitido, divorciado/a, soltero/a."""
    pareja = str(p.get("pareja","") or "").strip()
    if pareja:
        return False
    est = str(p.get("estado","") or "").strip().lower()
    if est in {"casado", "casada", "casado/a", "unión libre", "union libre"}:
        return False
    return True

def _id_or_empty(x: Any) -> str:
    return str(x or "").strip()


# ---------- Persistencia TXT ----------
@dataclass
class TxtSchema:
    sep: str = ";"
    familia_idx: int = 0   # "4351 - López Sánchez"
    persona_id_idx: int = 1 # "001"
    nombre_idx: int = 2     # "Ofelia Esquivel"
    pareja_idx: int = 9     # "002 - Manuel Ángel"  (10ma columna en tus ejemplos)

def _update_pareja_in_lines(lines: List[str], schema: TxtSchema, p: Persona, pareja_text: str) -> None:
    """
    Intenta ubicar la línea de 'p' y poner pareja_text en columna pareja_idx.
    Criterios de match:
      - familia (texto exacto, con nombre): p["familia"]
      - id de persona (cedula/id): p["cedula"] o p["id"]
      - fallback por nombre si hiciera falta
    """
    fam_txt = str(p.get("familia","")).strip()
    pid = str(p.get("cedula") or p.get("id") or "").strip()
    pname = str(p.get("nombre","")).strip().lower()

    for i, raw in enumerate(lines):
        if not raw.strip():
            continue
        parts = raw.rstrip("\n").split(schema.sep)
        # Asegura longitud suficiente
        need = max(schema.familia_idx, schema.persona_id_idx, schema.nombre_idx, schema.pareja_idx)
        if len(parts) <= need:
            parts += [""] * (need + 1 - len(parts))

        fam_ok = fam_txt and parts[schema.familia_idx].strip() == fam_txt
        id_ok  = pid and parts[schema.persona_id_idx].strip() == pid
        name_ok = pname and parts[schema.nombre_idx].strip().lower() == pname

        if (fam_ok and (id_ok or name_ok)) or (id_ok and name_ok):
            parts[schema.pareja_idx] = pareja_text
            lines[i] = schema.sep.join(parts) + "\n"
            break

def _atomic_write(path: str, content: str, encoding: str = "utf-8") -> None:
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding=encoding, newline="") as f:
        f.write(content)
    try:
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


# ---------- Motor de Uniones ----------
class UnionsEngine:
    """
    Crea uniones entre personas cumpliendo:
    - >18 años, vivos, sin pareja, sexos opuestos, gap de edad ≤ 15,
    - compatibilidad emocional ≥ umbral (default 0.28),
    - seguridad genética ampliada.
    Cruce de familias: si familias distintas → añade el id de la otra familia en 'familias_extra'.

    Correcciones clave:
    - Tope de uniones por año real (mapa _unions_by_year).
    - Persistencia al TXT (columna 'pareja') si se pasa personas_file.
    - Mínimo de 1 unión cada 2 años (si los 2 previos fueron 0, fuerza una en el año actual).
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        familias: Optional[List[Tuple[str, str]]] = None,
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        get_anio_sim: GetYearCB = None,
        umbral_compat: float = 0.20,        # más permisivo para asegurar uniones
        prob_union_por_par: float = 0.8,
        max_uniones_por_anio: int = 5,
        min_uniones_cada_dos_anios: int = 1,  # <= NUEVO
        personas_file: Optional[str] = None,
        txt_schema: Optional[TxtSchema] = None,
        encoding: str = "utf-8",
    ):
        self.personas = personas
        self.familias = familias or []
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.on_change = on_change
        self.on_event = on_event
        self.get_anio_sim = get_anio_sim
        self.umbral = float(umbral_compat)
        self.p_union = max(0.0, min(1.0, prob_union_por_par))
        self.max_uniones = max(1, int(max_uniones_por_anio))
        self.min_uniones_2y = max(0, int(min_uniones_cada_dos_anios))

        # Persistencia
        self.personas_file = personas_file
        self.txt_schema = txt_schema or TxtSchema()
        self._encoding = encoding

        # Año base
        if self.get_anio_sim is not None:
            base_year = int(self.get_anio_sim())
        else:
            years = []
            for p in self.personas.values():
                d = _parse_date_any(p.get("nac", ""))
                if d:
                    years.append(d.year)
            base_year = max(years) if years else datetime.now().year

        self._anio_sim = base_year

        # Contador robusto por año
        self._unions_by_year: Dict[int, int] = {}

        # Hilo
        self._stop_evt = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    # ---- API ----
    @property
    def anio_sim(self) -> int:
        return int(self.get_anio_sim()) if self.get_anio_sim else self._anio_sim

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop_evt.clear()
        self._thr = threading.Thread(target=self._run, name="UnionsEngineThread", daemon=True)
        self._thr.start()

    def stop(self, wait: bool = False, timeout: Optional[float] = 1.5):
        self._stop_evt.set()
        if wait and self._thr is not None:
            try:
                self._thr.join(timeout=timeout)
            except Exception:
                pass

    # ---- Bucle ----
    def _run(self):
        while not self._stop_evt.is_set():
            t0 = time.time()
            try:
                self._tick()
            except Exception:
                pass

            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    pass

            elapsed = time.time() - t0
            rest = max(0.05, self.segundos_por_tick - elapsed)
            self._sleep_cancellable(rest)

    def _sleep_cancellable(self, secs: float):
        end = time.time() + secs
        while time.time() < end and not self._stop_evt.is_set():
            time.sleep(0.05)

    # ---- Helpers de emparejamiento ----
    def _collect_candidates(self, y: int, eligibles: List[str]) -> List[Tuple[float, str, str]]:
        """Devuelve lista (score, a_id, b_id) para parejas M-F elegibles y seguras."""
        cand: List[Tuple[float, str, str]] = []
        n = len(eligibles)
        for i in range(n):
            a_id = eligibles[i]
            A = self.personas[a_id]
            ga = _norm_gender(A.get("genero", ""))
            if not ga:
                continue
            for j in range(i + 1, n):
                b_id = eligibles[j]
                B = self.personas[b_id]
                gb = _norm_gender(B.get("genero", ""))
                if not gb or ga == gb:
                    continue
                ea = _age_of(A, y); eb = _age_of(B, y)
                if ea is None or eb is None or abs(ea - eb) > 15:
                    continue
                if not _genetically_safe(self.personas, A, B, a_id, b_id):
                    continue
                score = _compute_compatibility(A, B)
                if score >= self.umbral:
                    # asegura que el orden sea siempre (M,F) indiferente; no importa realmente
                    cand.append((score, a_id, b_id))
        cand.sort(key=lambda t: t[0], reverse=True)
        return cand

    # ---- Lógica por tick ----
    def _tick(self):
        with self._lock:
            # avanza el año si no hay callback externo
            self._anio_sim = int(self.get_anio_sim()) if self.get_anio_sim else (self._anio_sim + 1)
            y = self._anio_sim

            # --- chequeo mínimo 1/2 años: si dos años previos tuvieron 0, forzamos en este ---
            y_prev1, y_prev2 = y - 1, y - 2
            if self.min_uniones_2y > 0:
                if self._unions_by_year.get(y_prev1, 0) == 0 and self._unions_by_year.get(y_prev2, 0) == 0:
                    self._force_minimum_union(y)
                    # si ya alcanzamos el tope tras forzar, salir
                    if self._unions_by_year.get(y, 0) >= self.max_uniones:
                        return

            # si alcanzamos el tope del año, nada
            if self._unions_by_year.get(y, 0) >= self.max_uniones:
                return

            # construir lista de solteros elegibles
            eligibles = self._eligible_singles(y)
            if not eligibles:
                return

            # candidatos por compatibilidad
            candidates = self._collect_candidates(y, eligibles)
            if not candidates:
                return

            made_any_this_tick = False
            used: set = set()

            for score, a_id, b_id in candidates:
                if self._unions_by_year.get(y, 0) >= self.max_uniones:
                    break
                if a_id in used or b_id in used:
                    continue
                if random.random() > self.p_union:
                    continue
                if self._make_union(a_id, b_id, y, score, forced=False):
                    used.add(a_id); used.add(b_id)
                    self._unions_by_year[y] = self._unions_by_year.get(y, 0) + 1
                    made_any_this_tick = True

            # Si no se logró ninguna por probabilidad, y seguimos debajo del tope,
            # hacemos un "rescate suave": tomamos la mejor y la unimos (no cuenta como forzada por 2 años,
            # pero ayuda a que sí haya uniones normales).
            if not made_any_this_tick and self._unions_by_year.get(y, 0) < self.max_uniones:
                best = candidates[0]
                if self._make_union(best[1], best[2], y, best[0], forced=False):
                    self._unions_by_year[y] = self._unions_by_year.get(y, 0) + 1

    # ---- Elegibles ----
    def _eligible_singles(self, year_now: int) -> List[str]:
        out: List[str] = []
        for ced, p in list(self.personas.items()):
            if _is_dead(p, year_now):
                continue
            age = _age_of(p, year_now)
            if age is None or age < 18:
                continue
            if not _is_single(p):
                continue
            # Debe tener familia asignada (para cruzar si aplica)
            fam = _id_or_empty(p.get("familia"))
            if not fam:
                continue
            # Género reconocido
            if not _norm_gender(p.get("genero","")):
                continue
            out.append(ced)
        return out

    # ---- Forzar 1 unión por regla de mínimo 1/2 años ----
    def _force_minimum_union(self, y: int):
        """Forzar al menos una unión este año si los 2 previos tuvieron 0 y hay elegibles."""
        if self._unions_by_year.get(y, 0) >= self.max_uniones:
            return
        eligibles = self._eligible_singles(y)
        if not eligibles:
            return
        candidates = self._collect_candidates(y, eligibles)
        if not candidates:
            return
        best = candidates[0]
        if self._make_union(best[1], best[2], y, best[0], forced=True):
            self._unions_by_year[y] = self._unions_by_year.get(y, 0) + 1
            if self.on_event:
                try:
                    self.on_event("union_min_2y", {"cedula": best[1], "detalle": "Se fuerza unión por regla de mínimo 1 cada 2 años"})
                except Exception:
                    pass

    # ---- Persistencia TXT ----
    def _persist_union_to_txt(self, A: Persona, B: Persona):
        """Escribe la pareja en el TXT si se configuró personas_file."""
        if not self.personas_file:
            return
        path = self.personas_file
        if not os.path.exists(path):
            return
        try:
            with io.open(path, "r", encoding=self._encoding) as f:
                lines = f.readlines()

            pareja_A = _idname(str(B.get("cedula") or ""), str(B.get("nombre","")))
            pareja_B = _idname(str(A.get("cedula") or ""), str(A.get("nombre","")))

            _update_pareja_in_lines(lines, self.txt_schema, A, pareja_A)
            _update_pareja_in_lines(lines, self.txt_schema, B, pareja_B)

            _atomic_write(path, "".join(lines), encoding=self._encoding)
        except Exception:
            # No rompe la simulación si falla el I/O
            pass

    # ---- Crear unión ----
    def _make_union(self, a_id: str, b_id: str, year_now: int, score: float, forced: bool = False) -> bool:
        """
        Devuelve True si se concretó, False si se abortó (por tope anual u otra causa).
        Lleva *doble* guard-rail del tope anual para que también aplique si alguien
        llama a _make_union() directamente.
        """
        # tope anual duro
        if not forced and self._unions_by_year.get(year_now, 0) >= self.max_uniones:
            return False

        A = self.personas.get(a_id)
        B = self.personas.get(b_id)
        if not A or not B:
            return False

        # verificación final anti-incesto
        if not _genetically_safe(self.personas, A, B, a_id, b_id):
            return False

        # 1) Actualiza 'pareja' de ambos con el formato "cedula - nombre"
        A["pareja"] = _idname(b_id, B.get("nombre", ""))
        B["pareja"] = _idname(a_id, A.get("nombre", ""))

        # 2) Estado civil visible para que el tree los considere pareja
        A["estado"] = "Unión libre"
        B["estado"] = "Unión libre"

        # 3) Si son de familias distintas, agrégalos a 'familias_extra'
        fam_a = str(A.get("familia") or "").strip()
        fam_b = str(B.get("familia") or "").strip()
        if fam_a and fam_b and fam_a != fam_b:
            for P, fam_other in ((A, fam_b), (B, fam_a)):
                extras = P.get("familias_extra")
                if not isinstance(extras, list):
                    extras = []
                if fam_other not in extras:
                    extras.append(fam_other)
                P["familias_extra"] = extras

        # 4) Historial
        for P, other_id, other_name in ((A, b_id, B.get("nombre","")), (B, a_id, A.get("nombre",""))):
            hist = P.get("_hist")
            if not isinstance(hist, list):
                hist = []
            flag = " (forzada)" if forced else ""
            hist.append({"anio": year_now, "tipo": "union", "detalle": f"Se une con {other_id} - {other_name}{flag}"})
            P["_hist"] = hist

        # 5) Evento visual
        if self.on_event:
            detalle = f"{A.get('nombre','¿?')} y {B.get('nombre','¿?')} se unieron (compatibilidad: {int(round(score*100))}%){' [forzada]' if forced else ''}"
            try:
                self.on_event("union", {"cedula": a_id, "detalle": detalle})
            except Exception:
                pass
            try:
                self.on_event("union", {"cedula": b_id, "detalle": detalle})
            except Exception:
                pass

        # 6) Persistir al TXT si procede
        #   Requisitos: cada Persona debe tener:
        #     - "familia": p.ej. "4351 - López Sánchez"
        #     - "cedula" (o "id"): "001", "002", ...
        self._persist_union_to_txt(A, B)

        # 7) Refrescar UI
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

        return True
