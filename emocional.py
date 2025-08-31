# emocional.py
from __future__ import annotations
import threading
import time
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Any

Persona   = Dict[str, Any]
OnChange  = Optional[Callable[[], None]]
OnEvent   = Optional[Callable[[str, Dict], None]]
GetYearCB = Optional[Callable[[], int]]  # sincroniza con BirthdayEngine si se pasa


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

def _today_with_year(y: int) -> str:
    """Fecha 'actual' = año de simulación + mes/día del sistema."""
    now = datetime.now()
    return f"{y:04d}-{now.month:02d}-{now.day:02d}"

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

def _is_single_now(p: Persona) -> bool:
    """Cuenta como soltero/a solo cuando estado es 'Soltero/a' y no hay pareja."""
    estado = str(p.get("estado", "") or "").strip().lower()
    pareja = str(p.get("pareja", "") or "").strip()
    return (("soltero" in estado) or ("soltera" in estado)) and not pareja

def _sadify_avatar(name: str) -> str:
    """
    Inserta '.SAD' antes de la extensión.
      'ADULTA1.png' -> 'ADULTA1.SAD.png'
      'foto.perfil.jpg' -> 'foto.perfil.SAD.jpg'
    Si ya está triste, lo deja igual.
    """
    if not name:
        return name
    lower = name.lower()
    if ".sad." in lower or lower.endswith(".sad"):
        return name  # ya triste
    if "." in name:
        base, ext = name.rsplit(".", 1)
        return f"{base}.SAD.{ext}"
    return name + ".SAD"

def _unsadify_avatar(name: str) -> str:
    """Quita el marcador .SAD si existe."""
    if not name:
        return name
    if ".SAD." in name:
        return name.replace(".SAD.", ".", 1)
    if name.endswith(".SAD"):
        return name[:-4]
    # prudencia con minúsculas
    low = name.lower()
    if ".sad." in low:
        i = low.index(".sad.")
        return name[:i] + "." + name[i+5:]  # salta ".sad."
    if low.endswith(".sad"):
        return name[: -4]
    return name


# ---------- Motor de Salud Emocional ----------
class EmotionalHealthEngine:
    """
    Reglas:
      - Si una persona permanece 'Soltero/a' durante 'years_threshold' años consecutivos,
        entra en estado emocional bajo: se cambia a avatar triste ('.SAD') y empieza a
        perder salud emocional cada año. La caída acelera con el tiempo.
      - Si deja de estar soltero/a, se restaura avatar base y se emite mejora.
      - Si la salud emocional cae por debajo de 'mortality_threshold' (p.ej., 5%),
        la persona muere de inmediato (se marca 'falle' con fecha actual, estado, historial y evento).

    Eventos:
      - 'salud_baja'   {cedula, nivel:'baja', valor:int, detalle:str}
      - 'salud_mejora' {cedula, nivel:'recupera', valor:int, detalle:str}
      - 'fallece'      {cedula, nombre, edad, fecha, motivo:'emocional'}
    """

    def __init__(
        self,
        personas: Dict[str, Persona],
        segundos_por_tick: int = 10,
        on_change: OnChange = None,
        on_event: OnEvent = None,
        get_anio_sim: GetYearCB = None,
        years_threshold: int = 5,        # a partir de 5 años soltero/a
        base_decay: int = 8,             # caída inicial anual (%) tras alcanzar el umbral
        accel_decay: int = 2,            # aceleración de la caída cada año extra
        mortality_threshold: int = 5,    # < 5% => muerte
        mortality_bias_on_low: float = 0.05,  # sesgo para otros módulos de mortalidad
    ):
        self.personas = personas
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.on_change = on_change
        self.on_event = on_event
        self.get_anio_sim = get_anio_sim

        self.years_threshold = max(1, int(years_threshold))
        self.base_decay = max(1, int(base_decay))
        self.accel_decay = max(0, int(accel_decay))
        self.mortality_threshold = max(0, int(mortality_threshold))
        self.mortality_bias_on_low = float(mortality_bias_on_low)

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

        # Hilo
        self._stop_evt = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Inicializa campos auxiliares
        with self._lock:
            for p in self.personas.values():
                if "_years_single" not in p:
                    p["_years_single"] = 0
                if "_avatar_base" not in p:
                    p["_avatar_base"] = p.get("avatar", "")
                if "salud_emocional" not in p:
                    p["salud_emocional"] = 100  # base
                if "_emo_low" not in p:
                    p["_emo_low"] = False

    # ---- API ----
    @property
    def anio_sim(self) -> int:
        return int(self.get_anio_sim()) if self.get_anio_sim else self._anio_sim

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop_evt.clear()
        self._thr = threading.Thread(target=self._run, name="EmotionalHealthEngineThread", daemon=True)
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

    # ---- Lógica por tick (1 “año” sim) ----
    def _tick(self):
        with self._lock:
            self._anio_sim = int(self.get_anio_sim()) if self.get_anio_sim else (self._anio_sim + 1)
            y = self._anio_sim

            for ced, p in list(self.personas.items()):
                if _is_dead(p, y):
                    continue

                if _is_single_now(p):
                    p["_years_single"] = int(p.get("_years_single", 0)) + 1

                    # Al llegar al umbral, activar estado emocional bajo y avatar triste
                    if not p.get("_emo_low", False) and p["_years_single"] >= self.years_threshold:
                        self._activate_low_emotion(ced, p, y)

                    # Si está en bajo estado emocional, degradar salud cada año
                    if p.get("_emo_low", False):
                        self._degrade_health_or_die(ced, p, y)

                else:
                    # Restablecer si ya no está soltero
                    if int(p.get("_years_single", 0)) != 0:
                        p["_years_single"] = 0
                    if p.get("_emo_low", False):
                        self._revert_emotional(ced, p, y)

    # ---- Acciones ----
    def _activate_low_emotion(self, ced: str, p: Persona, year_now: int):
        p["_emo_low"] = True

        # guardar avatar base una sola vez
        if "_avatar_base" not in p or p["_avatar_base"] == "":
            p["_avatar_base"] = p.get("avatar", "")

        # cambiar a versión triste
        current_avatar = str(p.get("avatar", "") or "")
        if current_avatar:
            p["avatar"] = _sadify_avatar(current_avatar)

        # bajar salud inicial si está muy alta
        cur = _safe_int(p.get("salud_emocional"), 100) or 100
        if cur > 70:
            p["salud_emocional"] = 70

        # sesgo de mortalidad para otros módulos
        mb = float(p.get("_mortality_bias", 0) or 0.0)
        if mb < self.mortality_bias_on_low:
            p["_mortality_bias"] = self.mortality_bias_on_low

        # historial
        hist = p.get("_hist")
        if not isinstance(hist, list):
            hist = []
        hist.append({
            "anio": year_now,
            "tipo": "salud_baja",
            "detalle": f"Activa estado emocional bajo tras {self.years_threshold} años de soltería",
        })
        p["_hist"] = hist

        # evento visual
        if self.on_event:
            try:
                self.on_event("salud_baja", {
                    "cedula": ced,
                    "nivel": "baja",
                    "valor": int(p.get("salud_emocional", 70)),
                    "detalle": f"{p.get('nombre','¿?')} alcanza {self.years_threshold} años soltero/a",
                })
            except Exception:
                pass

    def _degrade_health_or_die(self, ced: str, p: Persona, year_now: int):
        """Aplica caída acelerada y comprueba muerte por < mortality_threshold%."""
        years_single = int(p.get("_years_single", 0))
        over = max(0, years_single - self.years_threshold)  # 0 el primer año del umbral
        # Caída acelerada: base + over*accel
        drop = self.base_decay + over * self.accel_decay

        cur = max(0, _safe_int(p.get("salud_emocional"), 0) or 0)
        new_val = max(0, cur - drop)
        p["salud_emocional"] = new_val

        # evento de caída anual (para panel)
        if self.on_event:
            try:
                self.on_event("salud_baja", {
                    "cedula": ced,
                    "nivel": "baja",
                    "valor": int(new_val),
                    "detalle": f"Salud emocional cae a {int(new_val)}% tras {years_single} años soltero/a",
                })
            except Exception:
                pass

        # ¿muerte por salud emocional muy baja?
        if new_val < self.mortality_threshold:
            self._kill_due_to_emotion(ced, p, year_now)

    def _kill_due_to_emotion(self, ced: str, p: Persona, year_now: int):
        fecha = _today_with_year(year_now)
        p["falle"] = fecha
        p["estado"] = "Fallecido/a"

        # Historial
        hist = p.get("_hist")
        if not isinstance(hist, list):
            hist = []
        hist.append({
            "anio": year_now,
            "tipo": "fallecimiento",
            "detalle": f"Fallece por salud emocional (<{self.mortality_threshold}%) en {fecha}",
        })
        p["_hist"] = hist

        # Evento visual
        if self.on_event:
            try:
                # calcula edad para el evento
                d = _parse_date_any(p.get("nac",""))
                edad_val = max(0, year_now - d.year) if d else (_safe_int(p.get("edad"), 0) or 0)
                self.on_event("fallece", {
                    "cedula": ced,
                    "nombre": p.get("nombre", "¿?"),
                    "edad": edad_val,
                    "fecha": fecha,
                    "motivo": "emocional",
                })
            except Exception:
                pass

    def _revert_emotional(self, ced: str, p: Persona, year_now: int):
        p["_emo_low"] = False

        # restaurar avatar
        base = str(p.get("_avatar_base", "") or "")
        if base:
            p["avatar"] = _unsadify_avatar(base)

        # mejora leve de salud y baja de sesgo
        cur = _safe_int(p.get("salud_emocional"), 60) or 60
        p["salud_emocional"] = min(100, cur + 20)
        mb = float(p.get("_mortality_bias", 0) or 0.0)
        if mb > 0:
            p["_mortality_bias"] = max(0.0, mb - self.mortality_bias_on_low)

        # historial
        hist = p.get("_hist")
        if not isinstance(hist, list):
            hist = []
        hist.append({
            "anio": year_now,
            "tipo": "salud_mejora",
            "detalle": "Recupera salud emocional al dejar la soltería",
        })
        p["_hist"] = hist

        # evento
        if self.on_event:
            try:
                self.on_event("salud_mejora", {
                    "cedula": ced,
                    "nivel": "recupera",
                    "valor": int(p.get("salud_emocional", 80)),
                    "detalle": f"{p.get('nombre','¿?')} sale de soltería",
                })
            except Exception:
                pass
