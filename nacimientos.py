# nacimientos.py
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
def _safe_int(x, default: Optional[int] = 0) -> Optional[int]:
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

def _today_real() -> str:
    return datetime.now().strftime("%Y-%m-%d")

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

def _not_close_relatives(a: Persona, b: Persona) -> bool:
    """Evita consanguinidad directa: no compartir padre/madre inmediatos."""
    ap = (_id_from_combo(a.get("padre","")), _id_from_combo(a.get("madre","")))
    bp = (_id_from_combo(b.get("padre","")), _id_from_combo(b.get("madre","")))
    if ap == bp and any(ap):  # hermanos completos
        return False
    if (ap[0] and ap[0] == bp[0]) or (ap[1] and ap[1] == bp[1]):  # medio hermanos
        return False
    return True

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
    """
    A = set(_list_from_csv(a.get("afinidades") or a.get("intereses")))
    B = set(_list_from_csv(b.get("afinidades") or b.get("intereses")))
    if A or B:
        inter = len(A & B)
        union = max(1, len(A | B))
        aff = inter / union
    else:
        aff = 0.5  # desconocido → término medio

    ea = _safe_int(a.get("edad"), None)
    eb = _safe_int(b.get("edad"), None)
    age_bonus = 1.0 - min(1.0, (abs((ea or 0) - (eb or 0)) / 20.0))  # 0..1
    age_bonus *= 0.1

    prov_bonus = 0.1 if (a.get("provincia") and a.get("provincia") == b.get("provincia")) else 0.0

    score = 0.8 * aff + age_bonus + prov_bonus
    return max(0.0, min(1.0, score))

def _compatible_age_gap(a_edad: Optional[int], b_edad: Optional[int], max_gap: int = 15) -> bool:
    if a_edad is None or b_edad is None:
        return True
    return abs(a_edad - b_edad) <= max_gap

def _age_of(p: Persona, year_now: int) -> Optional[int]:
    """Edad desde p['edad'] o a partir de 'nac'."""
    e = _safe_int(p.get("edad"), None)
    if e is not None:
        return max(0, e)
    d = _parse_date_any(p.get("nac", ""))
    return max(0, year_now - d.year) if d else None

def _unique_cedula(existing: Dict[str, Persona]) -> str:
    # número pseudo-único no usado
    while True:
        n = random.randint(10_000_000, 99_999_999) * 10 + random.randint(0, 9)
        c = str(n)
        if c not in existing:
            return c

def _pick_baby_avatar() -> str:
    # Solo nombres válidos que existan en Assets/personas/
    return random.choice(["bebe1.png", "bebe2.png"])

def _pick_baby_name(gender: str) -> str:
    boys = ["Daniel", "Mateo", "Santiago", "Gabriel", "Adrián", "Benjamín", "Lucas", "Leo", "Álvaro", "Diego"]
    girls = ["Sofía", "Valentina", "Isabella", "Emma", "Camila", "Martina", "Victoria", "Mía", "Lucía", "Ana"]
    return random.choice(boys if gender == "M" else girls)


# ---------- Motor de Nacimientos (solo parejas existentes) ----------
class BirthEngine:
    """
    - SOLO trabaja con parejas YA EXISTENTES (campo 'pareja' enlazando IDs).
    - Nacimientos normales: compatibilidad >= 30% y AMBOS ≤ 46 años.
    - Límite: máx. 1 nacimiento por año (ajustable).
    - Enfriamiento por pareja: 5 años entre hijos de la misma pareja (ajustable).
    - GARANTÍA: si pasan 2 años sin nacimientos, se fuerza 1 con la pareja de mayor
      compatibilidad existente (aunque sea <30%), respetando: vivos, sexos opuestos,
      gap ≤ 15, NO parientes, y AMBOS ≤ 46. NO crea uniones nuevas.
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        familias: Optional[List[Tuple[str, str]]] = None,
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        get_anio_sim: GetYearCB = None,
        min_compatibilidad_nacimiento: float = 0.30,  # 30%
        max_anios_sin_nacer: int = 2,                 # garantía
        prob_nacimiento_por_pareja: float = 0.03,     # muy bajo para evitar exceso
        max_nacimientos_por_anio: int = 3,            # tope global anual
        min_anios_entre_hijos: int = 3                # enfriamiento por pareja
    ):
        self.personas = personas
        self.familias = familias or []
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.on_change = on_change
        self.on_event = on_event
        self.get_anio_sim = get_anio_sim

        self.min_compat = float(min_compatibilidad_nacimiento)
        self.max_gap_years = int(max_anios_sin_nacer)
        self.p_nacer = max(0.0, min(1.0, prob_nacimiento_por_pareja))
        self.max_births_per_year = max(1, int(max_nacimientos_por_anio))
        self.cooldown_years = max(0, int(min_anios_entre_hijos))

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

        # control de garantía y contador anual
        self._last_birth_year: Optional[int] = base_year - (self.max_gap_years - 1)
        self._counter_year = self._anio_sim
        self._births_this_year = 0

        # último hijo por pareja (a,b) ordenados
        self._couple_last_baby_year: Dict[Tuple[str, str], int] = {}
        self._bootstrap_last_babies_from_existing()

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
        self._thr = threading.Thread(target=self._run, name="BirthEngineThread", daemon=True)
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
            # año sim y reseteo de contador anual
            self._anio_sim = int(self.get_anio_sim()) if self.get_anio_sim else (self._anio_sim + 1)
            y = self._anio_sim
            if y != self._counter_year:
                self._counter_year = y
                self._births_this_year = 0

            couples_all = self._eligible_couples(y)          # [(a,b,score)] orden desc
            couples_ok  = [(a,b,s) for (a,b,s) in couples_all if s >= self.min_compat]

            did_birth = False

            # Nacimientos “normales” (respetan tope anual y cooldown)
            for (a_id, b_id, score) in couples_ok:
                if self._births_this_year >= self.max_births_per_year:
                    break
                if random.random() <= self.p_nacer and self._can_couple_have_child(a_id, b_id, y):
                    self._create_birth(a_id, b_id, y, forced=False)
                    self._births_this_year += 1
                    did_birth = True

            # GARANTÍA: al menos 1 cada max_gap_years
            # Si no hubo nacimientos en el periodo, forzamos 1 con la mejor pareja existente,
            # IGNORANDO cooldown, pero respetando resto de reglas (≤46, gap, no parientes...).
            if (self._last_birth_year is None) or (y - self._last_birth_year >= self.max_gap_years):
                if self._births_this_year == 0 and couples_all:
                    a_id, b_id, score = couples_all[0]
                    self._create_birth(a_id, b_id, y, forced=True)  # ignora cooldown por garantía
                    self._births_this_year += 1
                    did_birth = True

            if did_birth:
                self._last_birth_year = y

    # ---- Elegibilidad (parejas existentes) ----
    def _eligible_couples(self, year_now: int) -> List[Tuple[str, str, float]]:
        out: List[Tuple[str, str, float]] = []
        seen = set()

        for ced, p in list(self.personas.items()):
            pareja_raw = str(p.get("pareja", "") or "")
            if not pareja_raw:
                continue
            mate_id = _id_from_combo(pareja_raw)
            if not mate_id or mate_id not in self.personas:
                continue

            # evitar duplicados (a,b) ~ (b,a)
            a, b = (ced, mate_id) if ced < mate_id else (mate_id, ced)
            if (a, b) in seen:
                continue
            seen.add((a, b))

            A = self.personas[a]
            B = self.personas[b]

            # Reglas mínimas
            if _is_dead(A, year_now) or _is_dead(B, year_now):
                continue

            ea = _age_of(A, year_now)
            eb = _age_of(B, year_now)
            # Ambos deben existir y estar ≤ 46 (estricto)
            if ea is None or eb is None:
                continue
            if ea > 46 or eb > 46:
                continue

            ga = _norm_gender(A.get("genero", ""))
            gb = _norm_gender(B.get("genero", ""))
            if not (ga and gb) or ga == gb:
                continue

            if not _compatible_age_gap(ea, eb, max_gap=15):
                continue
            if not _not_close_relatives(A, B):
                continue

            score = _compute_compatibility(A, B)
            out.append((a, b, score))

        out.sort(key=lambda t: t[2], reverse=True)
        return out

    # ---- Cooldown por pareja ----
    def _can_couple_have_child(self, a_id: str, b_id: str, year_now: int) -> bool:
        key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        last = self._couple_last_baby_year.get(key)
        if last is None:
            return True
        return (year_now - last) >= self.cooldown_years

    def _remember_couple_birth(self, a_id: str, b_id: str, year_now: int):
        key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        self._couple_last_baby_year[key] = year_now

    def _bootstrap_last_babies_from_existing(self):
        """Escanea personas para detectar hijos existentes y calcular el último año por pareja."""
        for cid, child in self.personas.items():
            pid = _id_from_combo(child.get("padre",""))
            mid = _id_from_combo(child.get("madre",""))
            if not pid or not mid:
                continue
            if pid not in self.personas or mid not in self.personas:
                continue
            d = _parse_date_any(child.get("nac",""))
            if not d:
                continue
            key = (pid, mid) if pid < mid else (mid, pid)
            prev = self._couple_last_baby_year.get(key)
            if prev is None or d.year > prev:
                self._couple_last_baby_year[key] = d.year

    # ---- Crear bebé ----
    def _create_birth(self, a_id: str, b_id: str, y: int, forced: bool):
        A = self.personas[a_id]
        B = self.personas[b_id]

        ga = _norm_gender(A.get("genero", ""))
        gb = _norm_gender(B.get("genero", ""))

        # padre/madre según género
        padre_id, madre_id = (a_id, b_id)
        if ga == "F" and gb == "M":
            padre_id, madre_id = (b_id, a_id)
        elif ga == "M" and gb == "F":
            padre_id, madre_id = (a_id, b_id)

        padre = self.personas[padre_id]
        madre = self.personas[madre_id]

        baby_gender = random.choice(["M", "F"])
        baby_name   = _pick_baby_name(baby_gender)
        baby_id     = _unique_cedula(self.personas)
        provincia   = random.choice([padre.get("provincia"), madre.get("provincia")]) or ""
        familia     = padre.get("familia") or madre.get("familia") or (self.familias[0][0] if self.familias else "")
        avatar      = _pick_baby_avatar()
        nac         = _today_real()   # fecha ACTUAL (real)

        bebe: Persona = {
            "familia": familia,
            "cedula": baby_id,
            "nombre": baby_name,
            "nac": nac,
            "falle": "",  # VACÍO → NO muestra cruz
            "genero": "Masculino" if baby_gender == "M" else "Femenino",
            "provincia": provincia,
            "estado": "Soltero/a",
            "avatar": avatar,
            "padre": _idname(padre_id, padre.get("nombre", "")),
            "madre": _idname(madre_id, madre.get("nombre", "")),
            "pareja": "",
            "filiacion": "Hijo" if baby_gender == "M" else "Hija",
            "edad": "0",
            "_hist": [
                {"anio": y, "tipo": "nacimiento", "detalle": f"Nace en {nac}{' (forzado)' if forced else ''}"}
            ],
        }

        self.personas[baby_id] = bebe
        self._remember_couple_birth(padre_id, madre_id, y)

        # Eventos para UI/panel
        if self.on_event:
            try:
                self.on_event("nace", {
                    "cedula": baby_id,
                    "nombre_bebe": baby_name,
                    "genero": bebe["genero"],
                    "padre": padre.get("nombre", ""),
                    "madre": madre.get("nombre", ""),
                    "avatar": avatar,
                    "detalle": f"Nació {baby_name} ({bebe['genero']}) — hijo/a de {madre.get('nombre','')} y {padre.get('nombre','')}" + (" [forzado]" if forced else "")
                })
            except Exception:
                pass
            for pid in (padre_id, madre_id):
                try:
                    self.on_event("hijo", {
                        "cedula": pid,
                        "detalle": f"Nuevo hijo: {baby_name}"
                    })
                except Exception:
                    pass
