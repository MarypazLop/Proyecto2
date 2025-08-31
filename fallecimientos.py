# fallecimientos.py
from __future__ import annotations
import threading
import time
import random
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Any, Tuple

Persona   = Dict[str, Any]
OnChange  = Optional[Callable[[], None]]
OnEvent   = Optional[Callable[[str, Dict], None]]
GetYearCB = Optional[Callable[[], int]]  # sincroniza con BirthdayEngine si se pasa


# --------- Utilidades ---------
def _safe_int(x, default: int = 0) -> int:
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
    if not text:
        return ""
    return str(text).split(" - ")[0].strip()

def _idname(ced: str, nombre: str) -> str:
    return f"{ced} - {nombre or ''}".strip()

def _is_dead_value(raw: str, year_now: int) -> bool:
    t = (raw or "").strip().lower()
    if not t:
        return False
    if t in ("si", "sí", "true", "1", "y", "yes"):
        return True
    if t in ("no", "false", "0", "n"):
        return False
    d = _parse_date_any(t)
    return bool(d and year_now >= d.year)

def _append_hist(p: Persona, anio: int, tipo: str, detalle: str = ""):
    p.setdefault("_hist", []).append({"anio": anio, "tipo": tipo, "detalle": detalle})


# --------- Motor de Fallecimientos ---------
class DeathEngine:
    """
    Reglas:
    - Cada tick (10 s ≈ 1 año sim) evalúa muertes.
    - Nadie llega a 100: edad >= hard_max_age (default 100) MUERE forzado.
    - Probabilidad de muerte fuertemente creciente desde 80+.
    - GARANTÍA: al menos 1 muerte cada 'max_gap_years' (default 2) años de simulación:
        si no murió nadie en ese periodo, fallece el/la más anciano/a vivo.
    - Efectos:
        * p['falle'] = fecha ACTUAL (real) YYYY-MM-DD
        * p['estado'] = 'Fallecido/a'
        * pareja (si existe y vive): queda 'Viudo/a', se limpia 'pareja'
        * reasignación de tutor a hijos <18 si ambos padres fallecidos
        * eventos: 'fallece', 'viudez', 'tutoria'
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        get_anio_sim: GetYearCB = None,
        hard_max_age: int = 100,      # Nadie cumple 100
        risk_age_floor: int = 80,     # A partir de aquí sube fuerte la prob
        max_gap_years: int = 2        # garantía de al menos 1 muerte cada 2 años
    ):
        self.personas = personas
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.on_change = on_change
        self.on_event = on_event
        self.get_anio_sim = get_anio_sim
        self.hard_max = int(hard_max_age)
        self.risk_floor = int(risk_age_floor)
        self.max_gap_years = int(max_gap_years)

        # Año base sim
        if self.get_anio_sim is not None:
            base_year = int(self.get_anio_sim())
        else:
            years = []
            for p in self.personas.values():
                d = _parse_date_any(p.get("nac", ""))
                if d: years.append(d.year)
            base_year = max(years) if years else datetime.now().year
        self._anio_sim = base_year

        # Para la garantía
        self._last_death_year: Optional[int] = base_year - (self.max_gap_years - 1)

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
        self._thr = threading.Thread(target=self._run, name="DeathEngineThread", daemon=True)
        self._thr.start()

    def stop(self, wait: bool = False, timeout: Optional[float] = 1.5):
        self._stop_evt.set()
        if wait and self._thr is not None:
            try:
                self._thr.join(timeout=timeout)
            except Exception:
                pass

    # ---- Loop ----
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
            # año sim (sincronizable con BirthdayEngine)
            self._anio_sim = int(self.get_anio_sim()) if self.get_anio_sim else (self._anio_sim + 1)
            y = self._anio_sim

            did_death = False
            # 1) Reglas duras + probabilísticas
            for ced, p in list(self.personas.items()):
                if _is_dead_value(str(p.get("falle", "")), y):
                    continue

                edad = _safe_int(p.get("edad"), None)
                if edad is None:
                    d = _parse_date_any(p.get("nac", ""))
                    edad = max(0, y - d.year) if d else 0

                # Nadie llega a 100
                if edad >= self.hard_max:
                    self._mark_death(ced, forced=True, motivo="hard_max")
                    did_death = True
                    continue

                # Probabilidad fuerte por edad
                if random.random() < self._death_prob(edad):
                    self._mark_death(ced, forced=False, motivo="prob")
                    did_death = True

            # 2) Garantía: al menos 1 muerte cada N años
            if (not did_death) and (self._last_death_year is None or (y - self._last_death_year >= self.max_gap_years)):
                # elegir el/la más anciano/a vivo/a
                oldest_id = self._pick_oldest_alive(y)
                if oldest_id:
                    self._mark_death(oldest_id, forced=True, motivo="garantia")
                    did_death = True

            if did_death:
                self._last_death_year = y

    # ---- Probabilidad por edad ----
    def _death_prob(self, edad: int) -> float:
        """
        Curva bien agresiva para 80+:
          <50:    0.001
          50-59:  0.003
          60-69:  0.015
          70-79:  0.035
          80-84:  0.150
          85-89:  0.300
          90-94:  0.600
          95-99:  0.850
          >=100:  1.0 (pero ya lo captura la regla dura)
        """
        if edad < 50:   return 0.001
        if edad < 60:   return 0.003
        if edad < 70:   return 0.015
        if edad < 80:   return 0.035
        if edad < 85:   return 0.150
        if edad < 90:   return 0.300
        if edad < 95:   return 0.600
        if edad < 100:  return 0.850
        return 1.0

    # ---- Elegir más anciano vivo ----
    def _pick_oldest_alive(self, year_now: int) -> Optional[str]:
        oldest_id = None
        oldest_age = -1
        for ced, p in self.personas.items():
            if _is_dead_value(str(p.get("falle","")), year_now):
                continue
            edad = _safe_int(p.get("edad"), None)
            if edad is None:
                d = _parse_date_any(p.get("nac",""))
                edad = max(0, year_now - d.year) if d else 0
            if edad > oldest_age:
                oldest_age = edad
                oldest_id = ced
        return oldest_id

    # ---- Registrar fallecimiento y efectos ----
    def _mark_death(self, ced: str, forced: bool, motivo: str):
        y = self.anio_sim
        p = self.personas.get(ced)
        if not p:
            return

        # Fecha ACTUAL (real) y estado
        fecha = _today_real()
        p["falle"] = fecha
        p["estado"] = "Fallecido/a"
        _append_hist(p, y, "fallecimiento", f"Fallece en {fecha}" + (f" ({motivo})" if motivo else ""))

        # --- Evento visual
        if self.on_event:
            try:
                # calcula edad para el toast
                edad_val = _safe_int(p.get("edad"), None)
                if edad_val is None:
                    d = _parse_date_any(p.get("nac",""))
                    edad_val = max(0, self.anio_sim - d.year) if d else 0

                self.on_event("fallece", {
                    "cedula": ced,
                    "nombre": p.get("nombre", "¿?"),
                    "edad": edad_val,
                    "fecha": fecha,
                    "motivo": motivo,   # 'hard_max', 'prob' o 'garantia'
                })
            except Exception:
                pass

        # Viudez del cónyuge si aplica
        pareja_id = _id_from_combo(p.get("pareja",""))
        if pareja_id and pareja_id in self.personas:
            sp = self.personas[pareja_id]
            # solo si el/la cónyuge sigue vivo/a
            raw = str(sp.get("falle","") or "")
            if not _is_dead_value(raw, y):
                sp["pareja"] = ""
                sp["estado"] = "Viudo/a"
                _append_hist(sp, y, "viudez", f"Viudez por fallecimiento de {p.get('nombre','')}")
                if self.on_event:
                    try:
                        self.on_event("viudez", {
                            "cedula": pareja_id,
                            "nombre": sp.get("nombre","¿?")
                        })
                    except Exception:
                        pass

        # Tutoría a menores si faltan ambos padres
        self._assign_tutor_to_minors_if_needed(ced)


    # ---- Tutoría de menores (abuelos > tíos > hermanos > adulto de la familia) ----
    def _assign_tutor_to_minors_if_needed(self, fallecido_id: str):
        y = self.anio_sim
        hijos = self._children_of(fallecido_id)
        for hid in hijos:
            h = self.personas.get(hid)
            if not h:
                continue
            if _safe_int(h.get("edad"), 0) >= 18:
                continue

            padre_id = _id_from_combo(h.get("padre",""))
            madre_id = _id_from_combo(h.get("madre",""))

            # ¿ambos padres fallecidos?
            ambos_muertos = True
            for pid in (padre_id, madre_id):
                if pid and pid in self.personas:
                    if not _is_dead_value(str(self.personas[pid].get("falle","")), y):
                        ambos_muertos = False
            if not ambos_muertos:
                continue

            tutor = self._find_best_tutor(hid)
            if tutor:
                tid, tp = tutor
                h["tutor"] = _idname(tid, tp.get("nombre",""))
                h["adoptado"] = h["tutor"]  # activa el puntito verde en tu UI
                _append_hist(h, y, "tutoria", f"Tutor legal: {tp.get('nombre','')}")
                if self.on_event:
                    try:
                        self.on_event("tutoria", {
                            "cedula": hid,
                            "detalle": f"Tutor legal asignado: {tp.get('nombre','')}"
                        })
                    except Exception:
                        pass

    def _find_best_tutor(self, child_id: str) -> Optional[Tuple[str, Persona]]:
        y = self.anio_sim
        child = self.personas.get(child_id)
        if not child:
            return None

        fam = child.get("familia","")
        padre_id = _id_from_combo(child.get("padre",""))
        madre_id = _id_from_combo(child.get("madre",""))

        def alive_adult(ced: str) -> bool:
            p = self.personas.get(ced)
            return bool(p and not _is_dead_value(str(p.get("falle","")), y) and _safe_int(p.get("edad"), 0) >= 21)

        def pick_first(cands: List[str]) -> Optional[Tuple[str, Persona]]:
            for cid in cands:
                if cid and alive_adult(cid):
                    return (cid, self.personas[cid])
            return None

        # Abuelos
        abuelos: List[str] = []
        for pid in (padre_id, madre_id):
            if pid and pid in self.personas:
                pp = self.personas[pid]
                abuelos.extend([_id_from_combo(pp.get("padre","")), _id_from_combo(pp.get("madre",""))])
        t = pick_first([x for x in abuelos if x])
        if t: return t

        # Tíos (hermanos de los padres)
        tios: List[str] = []
        for pid in (padre_id, madre_id):
            if pid and pid in self.personas:
                tios.extend(self._siblings_of(pid))
        t = pick_first([x for x in set(tios) if x not in (padre_id, madre_id)])
        if t: return t

        # Hermanos mayores del niño/a
        t = pick_first(self._siblings_of(child_id))
        if t: return t

        # Adulto cualquiera de la misma familia
        for cid, p in self.personas.items():
            if cid == child_id:
                continue
            if p.get("familia","") == fam and alive_adult(cid):
                return (cid, p)

        return None

    # ---- Relaciones básicas por escaneo ----
    def _children_of(self, parent_id: str) -> List[str]:
        out = []
        for cid, p in self.personas.items():
            if _id_from_combo(p.get("padre","")) == parent_id or _id_from_combo(p.get("madre","")) == parent_id:
                out.append(cid)
        return out

    def _siblings_of(self, person_id: str) -> List[str]:
        p = self.personas.get(person_id)
        if not p:
            return []
        padre = _id_from_combo(p.get("padre",""))
        madre = _id_from_combo(p.get("madre",""))
        out = []
        for cid, q in self.personas.items():
            if cid == person_id:
                continue
            if _id_from_combo(q.get("padre","")) == padre and _id_from_combo(q.get("madre","")) == madre:
                out.append(cid)
        return out
