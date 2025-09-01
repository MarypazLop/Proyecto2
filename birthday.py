from __future__ import annotations
import threading
import time
from datetime import date, datetime
from typing import Callable, Dict, Optional, Any

# Tipos
Persona  = Dict[str, Any]
OnChange = Optional[Callable[[], None]]
OnEvent  = Optional[Callable[[str, Dict], None]]

# ---------- Utilidades ----------
def _safe_int(x, default: int = 0) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default

def _parse_date_any(s: str) -> Optional[date]:
    """Intenta varios formatos comunes: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD."""
    if not s:
        return None
    s = str(s).strip()
    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except Exception:
            pass
    return None

def _append_hist(p: Persona, anio: int, tipo: str, detalle: str = ""):
    if "_hist" not in p or not isinstance(p["_hist"], list):
        p["_hist"] = []
    p["_hist"].append({"anio": anio, "tipo": tipo, "detalle": detalle})

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

def _initial_age(p: Persona, base_year: int) -> int:
    """
    Edad inicial al arrancar:
    - Si ya tiene 'edad' numérica, úsala.
    - Si no, y hay fecha de nacimiento válida, calcula por año.
    - Si no, 0.
    """
    edad_existente = p.get("edad")
    if edad_existente is not None and str(edad_existente).strip() != "":
        return _safe_int(edad_existente, 0)
    nac = _parse_date_any(p.get("nac", ""))
    if nac:
        return max(0, base_year - nac.year)
    return 0

# ---------- Motor de cumpleaños ----------
class BirthdayEngine:
    """
    Cada tick (10s por defecto) avanza 1 año de simulación:
    - Para cada persona VIVA:
         * p['edad'] += 1  (como str)
         * agrega evento 'cumpleaños' al _hist en memoria
         * emite on_event('cumpleaños', {...})
         * (NUEVO) registra en sidecar historial.txt: history.rec_cumple(cedula, edad)
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        anio_inicial: Optional[int] = None,
    ):
        self.personas = personas
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.on_change = on_change
        self.on_event = on_event

        # Año base de simulación
        if anio_inicial is not None:
            base = int(anio_inicial)
        else:
            years = []
            for p in self.personas.values():
                d = _parse_date_any(p.get("nac", ""))
                if d:
                    years.append(d.year)
            base = max(years) if years else datetime.now().year
        self._anio_sim = base

        # Hilo y lock
        self._stop_evt = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Inicializa edad e historial si falta
        with self._lock:
            for p in self.personas.values():
                p["edad"] = str(_initial_age(p, self._anio_sim))
                if "_hist" not in p or not isinstance(p["_hist"], list):
                    p["_hist"] = []

    # ---- API pública ----
    @property
    def anio_sim(self) -> int:
        return self._anio_sim

    def set_velocidad(self, segundos_por_tick: int):
        self.segundos_por_tick = max(1, int(segundos_por_tick))

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop_evt.clear()
        self._thr = threading.Thread(target=self._run, name="BirthdayEngineThread", daemon=True)
        self._thr.start()

    def stop(self, wait: bool = False, timeout: Optional[float] = 1.5):
        self._stop_evt.set()
        if wait and self._thr is not None:
            try:
                self._thr.join(timeout=timeout)
            except Exception:
                pass

    # ---- Bucle interno ----
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
            self._anio_sim += 1
            y = self._anio_sim

            for ced, p in self.personas.items():
                if _is_dead(p, y):
                    continue

                # Incremento directo de edad (independiente de 'nac')
                edad_actual = _safe_int(p.get("edad"), _initial_age(p, y - 1))
                nueva_edad = edad_actual + 1
                p["edad"] = str(nueva_edad)

                # Historial en memoria
                _append_hist(p, y, "cumpleaños", f"Cumple {nueva_edad} años en {y}")

                # Evento UI
                if self.on_event:
                    try:
                        self.on_event("cumpleaños", {
                            "cedula": ced,
                            "edad": nueva_edad,
                            "detalle": f"{p.get('nombre','(sin nombre)')} cumple {nueva_edad}",
                        })
                    except Exception:
                        pass

                # --- NUEVO: Sidecar historial.txt (no romper si no existe) ---
                try:
                    from history import rec_cumple
                    # Registramos con fecha "real" (hoy); el anio_sim queda en el detalle del _hist.
                    rec_cumple(ced, nueva_edad, fecha=None)
                except Exception:
                    # Silencioso: no bloquea la simulación si no está history.py
                    pass

