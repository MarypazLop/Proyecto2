# uniones.py
from __future__ import annotations
import threading
import time
import random
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Any, Tuple

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
    if t.startswith(("m", "h")):  # masculino/hombre
        return "M"
    if t.startswith(("f", "muj")):  # femenino/mujer
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
        inter = len(A & B)           # afinidades compartidas
        union = max(1, len(A | B))
        aff = inter / union
        # pequeño “boost” si hay >=2 coincidencias
        if inter >= 2:
            aff = min(1.0, aff + 0.1)
    else:
        aff = 0.5  # desconocido → término medio

    ea = _age_of(a, datetime.now().year) or 0
    eb = _age_of(b, datetime.now().year) or 0
    age_bonus = 1.0 - min(1.0, (abs(ea - eb) / 20.0))  # 0..1
    age_bonus *= 0.1

    prov_bonus = 0.1 if (a.get("provincia") and a.get("provincia") == b.get("provincia")) else 0.0

    score = 0.8 * aff + age_bonus + prov_bonus
    return max(0.0, min(1.0, score))

def _genetically_safe(a: Persona, b: Persona) -> bool:
    """Reglas básicas para evitar riesgos de consanguinidad directa."""
    a_id = a.get("cedula","")
    b_id = b.get("cedula","")

    # Prohibir emparejar padre/madre con su propio hijo
    for parent, child in ((a, b), (b, a)):
        pid = parent.get("cedula","")
        if _id_from_combo(child.get("padre","")) == pid:
            return False
        if _id_from_combo(child.get("madre","")) == pid:
            return False

    # Prohibir hermanos completos/medio hermanos (comparten padre o madre)
    ap = (_id_from_combo(a.get("padre","")), _id_from_combo(a.get("madre","")))
    bp = (_id_from_combo(b.get("padre","")), _id_from_combo(b.get("madre","")))
    if ap == bp and any(ap):
        return False
    if (ap[0] and ap[0] == bp[0]) or (ap[1] and ap[1] == bp[1]):
        return False

    return True

def _is_single(p: Persona) -> bool:
    """Disponible: sin pareja actual. Viudo/a permitido, divorciado/a, soltero/a."""
    pareja = str(p.get("pareja","") or "").strip()
    if pareja:
        return False
    est = str(p.get("estado","") or "").strip().lower()
    # Estados que NO permiten nueva unión (si quieres restringirlo más, cámbialo aquí)
    if est in {"casado", "casada", "casado/a", "unión libre", "union libre"}:
        return False
    return True

def _id_or_empty(x: Any) -> str:
    return str(x or "").strip()


# ---------- Motor de Uniones ----------
class UnionsEngine:
    """
    Crea uniones entre personas cumpliendo:
      - >18 años, vivos, sin pareja, sexos opuestos, gap de edad ≤ 15,
      - compatibilidad emocional ≥ umbral (default 0.70),
      - seguridad genética básica (sin padre↔hijo, sin hermanos).
    Cruce de familias: si familias distintas → añade el id de la otra familia en
    'familias_extra' para que se visualicen en ambos árboles.
    Emite evento: 'union' con detalle y compatibilidad.

    Parámetros ajustables:
      - prob_union_por_par: probabilidad de concretar una unión cuando se detecta una pareja válida.
      - max_uniones_por_anio: límite de uniones creadas por año sim.
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        familias: Optional[List[Tuple[str, str]]] = None,
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        get_anio_sim: GetYearCB = None,
        umbral_compat: float = 0.70,
        prob_union_por_par: float = 0.25,
        max_uniones_por_anio: int = 2
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

        self._counter_year = self._anio_sim
        self._unions_this_year = 0

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

    # ---- Lógica por tick ----
    def _tick(self):
        with self._lock:
            # año sim y reseteo anual
            self._anio_sim = int(self.get_anio_sim()) if self.get_anio_sim else (self._anio_sim + 1)
            y = self._anio_sim
            if y != self._counter_year:
                self._counter_year = y
                self._unions_this_year = 0

            # si alcanzamos el tope del año, nada
            if self._unions_this_year >= self.max_uniones:
                return

            # construir lista de solteros elegibles
            eligibles = self._eligible_singles(y)
            if not eligibles:
                return

            # Intento de emparejar: greedy por mejor compatibilidad
            used = set()  # para no repetir personas en el mismo tick
            # genera todas las posibles combinaciones M-F
            candidates: List[Tuple[float, str, str]] = []  # (score, a_id, b_id)
            for a_id in eligibles:
                if a_id in used:
                    continue
                A = self.personas[a_id]
                ga = _norm_gender(A.get("genero",""))
                for b_id in eligibles:
                    if b_id == a_id or b_id in used:
                        continue
                    B = self.personas[b_id]
                    gb = _norm_gender(B.get("genero",""))
                    # solo sexos opuestos
                    if not (ga and gb) or ga == gb:
                        continue
                    # gap de edad ≤ 15
                    ea = _age_of(A, y); eb = _age_of(B, y)
                    if ea is None or eb is None or abs(ea - eb) > 15:
                        continue
                    # genética segura
                    if not _genetically_safe(A, B):
                        continue
                    # compatibilidad
                    score = _compute_compatibility(A, B)
                    if score >= self.umbral:
                        candidates.append((score, a_id, b_id))

            # ordenar por compat desc para elegir mejores primero
            candidates.sort(key=lambda t: t[0], reverse=True)

            for score, a_id, b_id in candidates:
                if self._unions_this_year >= self.max_uniones:
                    break
                if a_id in used or b_id in used:
                    continue
                # probabilidad de concretar
                if random.random() > self.p_union:
                    continue
                # concretar unión
                self._make_union(a_id, b_id, y, score)
                used.add(a_id); used.add(b_id)
                self._unions_this_year += 1

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
            # Genero reconocido
            if not _norm_gender(p.get("genero","")):
                continue
            out.append(ced)
        return out

    # ---- Crear unión ----
    def _make_union(self, a_id: str, b_id: str, year_now: int, score: float):
        A = self.personas[a_id]
        B = self.personas[b_id]

        # set pareja (formato "ced - nombre", como usa tu tree)
        A["pareja"] = _idname(b_id, B.get("nombre",""))
        B["pareja"] = _idname(a_id, A.get("nombre",""))

        # estado civil: Unión libre (puedes cambiar a "Casado/a" si lo prefieres)
        A["estado"] = "Unión libre"
        B["estado"] = "Unión libre"

        # si son de familias distintas → agregar a familias_extra de ambos
        fam_a = _id_or_empty(A.get("familia"))
        fam_b = _id_or_empty(B.get("familia"))
        if fam_a and fam_b and fam_a != fam_b:
            for P, fam_other in ((A, fam_b), (B, fam_a)):
                extras = P.get("familias_extra")
                if not isinstance(extras, list):
                    extras = []
                if fam_other not in extras:
                    extras.append(fam_other)
                P["familias_extra"] = extras

        # historial simple
        for P in (A, B):
            hist = P.get("_hist")
            if not isinstance(hist, list):
                hist = []
            hist.append({"anio": year_now, "tipo": "union", "detalle": f"Se une con {P.get('pareja','')}"})
            P["_hist"] = hist

        # evento visual
        if self.on_event:
            detalle = f"{A.get('nombre','¿?')} y {B.get('nombre','¿?')} se unieron (compatibilidad: {int(round(score*100))}%)"
            # enviar un único evento es suficiente, pero mando dos para que ambos aparezcan si filtras por cedula
            try:
                self.on_event("union", {"cedula": a_id, "detalle": detalle})
            except Exception:
                pass
            try:
                self.on_event("union", {"cedula": b_id, "detalle": detalle})
            except Exception:
                pass
