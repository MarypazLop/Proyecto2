from __future__ import annotations
import threading
import time
import random
import re
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional, Set, Tuple

from kinship import Kinship  # ya existe en tu proyecto

# --------------------------- Utilidades de fecha ---------------------------

def _parse_iso(iso: str) -> Optional[date]:
    if not iso:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            return datetime.strptime(iso, fmt).date()
        except Exception:
            pass
    try:
        return date.fromisoformat(iso)
    except Exception:
        return None

def _iso(d: Optional[date]) -> str:
    return d.isoformat() if d else ""

def _today_with_year(y: int) -> date:
    # día fijo (1/julio) para evitar edge-cases de fecha exacta
    return date(y, 7, 1)

# --------------------------- Datos auxiliares ---------------------------

@dataclass
class ExtraPersona:
    intereses: Set[str] = field(default_factory=set)
    salud_emocional: float = 1.0
    last_salud: float = 1.0
    anios_soltera: int = 0
    historial: List[Tuple[int, str, str]] = field(default_factory=list)  # (año, tipo, detalle)
    tutor_legal: Optional[str] = None
    viudo: bool = False
    adoptado: bool = False

# --------------------------- Gestor principal ---------------------------

class GestorFamilia:
    """
    - Cada tick (segundos_por_tick) avanza 1 año sim.
    - Cumpleaños, uniones, separaciones, nacimientos, fallecimientos.
    - Tutoría/adopción con reglas pedidas.
    - Cruces entre familias: al unirse, ambos agregan 'familias_extra' con la familia del cónyuge.
    - Salud emocional por rangos de edad, soledad, y eventos; avisos y cambio de avatar .happy/.sad.
    - Eventos: 'cumpleanios', 'union', 'separacion', 'hijo', 'nace', 'viudez', 'fallece', 'adopcion', 'tutoria', 'salud_baja'.
    """

    INTERESES_POOL = [
        "música", "deporte", "lectura", "tecnología", "cocina",
        "arte", "viajes", "naturaleza", "videojuegos", "voluntariado"
    ]

    def __init__(
        self,
        personas: Dict[str, Dict],
        familias: Optional[List[Tuple[str, str]]] = None,
        segundos_por_tick: int = 10,
        umbral_compatibilidad: float = 0.70,
        on_change: Optional[Callable[[], None]] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
        rng: Optional[random.Random] = None,
    ):
        self.personas = personas
        self.familias = familias or []
        self.segundos_por_tick = max(1, int(segundos_por_tick))
        self.umbral_compat = umbral_compatibilidad
        self.on_change = on_change
        self.on_event = on_event
        self._rng = rng or random.Random()
        self._lock = threading.RLock()

        # Extras y normalización de campos
        self._extra: Dict[str, ExtraPersona] = {}
        for ced, p in self.personas.items():
            self._extra[ced] = ExtraPersona()
            p.setdefault("adoptivos", [])          # lista de cédulas tutoras
            p.setdefault("adoptado", "")           # flag legible por el visor
            p.setdefault("familias_extra", [])     # aparecer también en otras familias (por unión)

        self._anio_sim = date.today().year
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._reconstruir_kin()

    # --------------------- Infraestructura ---------------------

    def _reconstruir_kin(self):
        self._kin = Kinship(self.personas)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while not self._stop_evt.is_set():
            time.sleep(self.segundos_por_tick)
            try:
                self.tick()
            except Exception as e:
                self._emit("error", {"detalle": str(e)})

    def _emit(self, tipo: str, payload: Dict):
        if self.on_event:
            try:
                self.on_event(tipo, payload)
            except Exception:
                pass

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # --------------------- Helpers ---------------------

    @staticmethod
    def _id_from_combo(text: str) -> str:
        if not text:
            return ""
        return text.split(" - ")[0].strip()

    def _combo(self, ced: str) -> str:
        p = self.personas.get(ced, {})
        return f"{ced} - {p.get('nombre','')}"

    def edad(self, ced: str) -> int:
        p = self.personas[ced]
        nac = _parse_iso(p.get("nac", ""))
        if not nac:
            return 0
        return max(0, self._anio_sim - nac.year)

    def vivo(self, ced: str) -> bool:
        return not self.personas[ced].get("falle", "").strip()

    def casado(self, ced: str) -> bool:
        est = (self.personas[ced].get("estado") or "").lower()
        return "casado" in est or "unión libre" in est

    def soltero(self, ced: str) -> bool:
        return (self.personas[ced].get("estado") or "").lower().startswith("soltero")

    # --------------------- Salud emocional ---------------------

    @staticmethod
    def _delta_salud_por_edad(edad: int) -> float:
        # Menor edad -> cae poco; mayor edad -> cae más (por estrés crónico)
        if edad < 20: return -0.010
        if edad < 30: return -0.015
        if edad < 40: return -0.020
        if edad < 50: return -0.030
        if edad < 60: return -0.040
        return -0.050

    def _ajustar_salud_por_soledad(self, ced: str):
        e = self._extra[ced]
        if not self.soltero(ced):
            e.anios_soltera = 0
            return
        e.anios_soltera += 1
        base = self._delta_salud_por_edad(self.edad(ced))
        factor = min(1.0, 0.2 + 0.1 * max(0, e.anios_soltera - 1))  # 0.2..1.0
        e.salud_emocional = max(0.0, e.salud_emocional + base * factor)

    def _reforzar_salud(self, ced: str, bonus: float):
        e = self._extra[ced]
        e.salud_emocional = min(1.0, e.salud_emocional + bonus)

    def _avatar_set_mood(self, ced: str, mood: str):
        """Cambia el avatar a .happy o .sad conservando nombre/base/ext."""
        p = self.personas[ced]
        avatar = (p.get("avatar") or "").strip()
        if not avatar:
            return
        # Captura [base][.happy|.sad][.ext] (case-insensitive)
        m = re.match(r"^(.*?)(?:\.(happy|sad))?(\.[A-Za-z0-9]+)?$", avatar, flags=re.IGNORECASE)
        if not m:
            return
        base, old, ext = m.group(1), m.group(2), m.group(3) or ".png"
        p["avatar"] = f"{base}.{mood.lower()}{ext}"

    def _avisar_cambio_salud_si_umbral(self, ced: str):
        e = self._extra[ced]
        prev = e.last_salud
        cur = e.salud_emocional
        # Umbrales 0.4 y 0.2
        niveles = [
            (0.4, "moderada"),
            (0.2, "severa"),
        ]
        for umbral, etiqueta in niveles:
            # cruzó hacia abajo el umbral
            if prev >= umbral and cur < umbral:
                self._emit("salud_baja", {"cedula": ced, "nivel": etiqueta, "valor": round(cur, 2)})
                # Cambia avatar a sad
                self._avatar_set_mood(ced, "sad")
                self._registrar_evento(ced, "salud_baja", f"Salud emocional {etiqueta} ({cur:.2f})")
                self._changed()
                break
            # cruzó hacia arriba (recuperación) y venía de debajo de ese umbral
            if prev < umbral and cur >= umbral:
                # Sube a happy si recuperó por encima de 0.5
                if cur >= 0.5:
                    self._avatar_set_mood(ced, "happy")
                    self._registrar_evento(ced, "salud_recupera", f"Recupera salud emocional ({cur:.2f})")
                    self._changed()
                break
        e.last_salud = cur

    # --------------------- Compatibilidad y restricciones ---------------------

    def _intereses(self, ced: str) -> Set[str]:
        e = self._extra[ced]
        if not e.intereses:
            e.intereses = set(self._rng.sample(self.INTERESES_POOL, k=3))
        return e.intereses

    def indice_compatibilidad(self, a: str, b: str) -> float:
        ia, ib = self._intereses(a), self._intereses(b)
        inter = len(ia & ib)
        if inter < 2:
            return 0.0
        jaccard = len(ia & ib) / len(ia | ib) if (ia | ib) else 0.0
        proxim_edad = max(0.0, 1.0 - (abs(self.edad(a) - self.edad(b)) / 15.0))
        score = 0.60 * jaccard + 0.40 * proxim_edad
        if self._extra[a].viudo or self._extra[b].viudo:
            score *= 0.90
        if self._extra[a].salud_emocional < 0.5 or self._extra[b].salud_emocional < 0.5:
            score *= 0.75
        return max(0.0, min(1.0, score))

    def _riesgo_genetico(self, a: str, b: str) -> bool:
        if a == b:
            return True
        if a in self._kin.ancestors(b) or b in self._kin.ancestors(a):
            return True
        sibs_a = set(self._kin.full_siblings(a)) | set(self._kin.half_siblings(a))
        if b in sibs_a:
            return True
        if b in set(self._kin.uncles_aunts(a, include_inlaws=False)) or a in set(self._kin.uncles_aunts(b, include_inlaws=False)):
            return True
        if b in set(self._kin.cousins(a)) or a in set(self._kin.cousins(b)):
            return True
        return False

    # --------------------- TICK ---------------------
    def tick(self):
        with self._lock:
            self._anio_sim += 1  # Avanzar el año

            # Cumpleaños: hacer crecer la edad de cada persona
            for ced, p in list(self.personas.items()):
                if not self.vivo(ced):
                    continue
                self._registrar_evento(ced, "cumpleanios", f"Cumple {self.edad(ced)} años")  # Aquí se registra el cumpleaños
                self._ajustar_salud_por_soledad(ced)  # Ajustar salud en función de la soledad

            # Luego de los cumpleaños, sigue el proceso de las separaciones, uniones, nacimientos y muertes
            self._intentar_separaciones(prob_base=0.03)
            self._intentar_uniones(max_intentos=6)
            self._intentar_nacimientos(prob_por_pareja=0.15)
            self._intentar_fallecimientos()
            self._asignar_tutorias()

            self._changed()

    # --------------------- Historial ---------------------

    def _registrar_evento(self, ced: str, tipo: str, detalle: str):
        self._extra.setdefault(ced, ExtraPersona())
        self._extra[ced].historial.append((self._anio_sim, tipo, detalle))
        self._emit(tipo, {"cedula": ced, "anio": self._anio_sim, "detalle": detalle})

    def get_historial(self, ced: str) -> List[Tuple[int, str, str]]:
        return sorted(self._extra.get(ced, ExtraPersona()).historial, key=lambda x: x[0])

    # --------------------- Uniones / Separaciones ---------------------

    def _candidatos_solteros(self) -> List[str]:
        out = []
        for ced, p in self.personas.items():
            if not self.vivo(ced):
                continue
            if self.soltero(ced) and self.edad(ced) >= 18 and not self._id_from_combo(p.get("pareja", "")):
                out.append(ced)
        return out

    def _intentar_uniones(self, max_intentos: int = 6):
        cands = self._candidatos_solteros()
        self._rng.shuffle(cands)
        intentos = 0
        for i in range(len(cands)):
            if intentos >= max_intentos:
                break
            a = cands[i]
            for j in range(i + 1, len(cands)):
                b = cands[j]
                if abs(self.edad(a) - self.edad(b)) > 15:  # Aseguramos que la diferencia de edad no sea grande
                    continue
                if self._riesgo_genetico(a, b):
                    continue
                score = self.indice_compatibilidad(a, b)
                if score >= 0.75:  # Aumentamos el umbral de compatibilidad a 0.75
                    self._unir(a, b, score)
                    intentos += 1
                    break

    def _unir(self, a: str, b: str, score: float):
        pa, pb = self.personas[a], self.personas[b]
        pa["estado"] = "Casado/a"
        pb["estado"] = "Casado/a"
        pa["pareja"] = self._combo(b)
        pb["pareja"] = self._combo(a)
        self._extra[a].viudo = False
        self._extra[b].viudo = False
        self._reforzar_salud(a, 0.08)
        self._reforzar_salud(b, 0.08)

        # Cruce entre familias: asegurar visibilidad en ambos árboles
        pa.setdefault("familias_extra", [])
        pb.setdefault("familias_extra", [])
        fam_a = pa.get("familia") or ""
        fam_b = pb.get("familia") or ""
        if fam_b and fam_b != fam_a and fam_b not in pa["familias_extra"]:
            pa["familias_extra"].append(fam_b)
        if fam_a and fam_a != fam_b and fam_a not in pb["familias_extra"]:
            pb["familias_extra"].append(fam_a)

        self._registrar_evento(a, "union", f"Se unió con {pb.get('nombre','')} (compat {int(score*100)}%)")
        self._registrar_evento(b, "union", f"Se unió con {pa.get('nombre','')} (compat {int(score*100)}%)")
        self._reconstruir_kin()

    def _intentar_separaciones(self, prob_base: float = 0.03):
        """Controlar separaciones por baja salud emocional o compatibilidad baja."""
        vistos = set()
        for ced, p in list(self.personas.items()):
            if not self.vivo(ced):
                continue
            pareja_id = self._id_from_combo(p.get("pareja", ""))
            if not pareja_id or pareja_id in vistos or pareja_id not in self.personas:
                continue
            if not self.vivo(pareja_id):
                continue
            
            salud_emocional_pareja = self._extra[ced].salud_emocional
            salud_emocional_otro = self._extra[pareja_id].salud_emocional
            compatibilidad = self.indice_compatibilidad(ced, pareja_id)

            # Solo separan si la salud emocional está por debajo de 0.3 o si la compatibilidad es muy baja
            if salud_emocional_pareja < 0.3 or salud_emocional_otro < 0.3: 
                prob = 0.08  # Probabilidad más alta si la salud emocional está muy baja
            elif compatibilidad < 0.5:  # Baja compatibilidad
                prob = 0.1
            else:
                prob = prob_base  # Probabilidad base

            if self._rng.random() <= prob:
                self._separar(ced, pareja_id)
            vistos.add(ced)
            vistos.add(pareja_id)

    def _separar(self, a: str, b: str):
        pa, pb = self.personas[a], self.personas[b]
        # Estado resultante
        def estado_sep(x): 
            return "Divorciado/a" if "casado" in (x.get("estado","").lower()) else "Separado/a"
        pa["estado"] = estado_sep(pa)
        pb["estado"] = estado_sep(pb)
        pa["pareja"] = ""
        pb["pareja"] = ""
        # impactar salud
        self._extra[a].salud_emocional = max(0.0, self._extra[a].salud_emocional - 0.05)
        self._extra[b].salud_emocional = max(0.0, self._extra[b].salud_emocional - 0.05)
        self._avisar_cambio_salud_si_umbral(a)
        self._avisar_cambio_salud_si_umbral(b)
        self._registrar_evento(a, "separacion", f"Se separó de {pb.get('nombre','')}")
        self._registrar_evento(b, "separacion", f"Se separó de {pa.get('nombre','')}")
        self._reconstruir_kin()
        self._changed()

    # --------------------- Nacimientos ---------------------

    def _intentar_nacimientos(self, prob_por_pareja: float = 0.10):
        """Generar nacimientos solo si la salud emocional es adecuada y la compatibilidad es alta."""
        vistos = set()
        for ced, p in list(self.personas.items()):
            if not self.vivo(ced):
                continue
            pareja_id = self._id_from_combo(p.get("pareja", ""))
            if not pareja_id or pareja_id in vistos or pareja_id not in self.personas:
                continue
            if not self.vivo(pareja_id):
                continue

            madre = ced if (p.get("genero","").lower().startswith("f")) else pareja_id
            padre = pareja_id if madre == ced else ced
            if madre not in self.personas or padre not in self.personas:
                vistos.add(ced); vistos.add(pareja_id); 
                continue

            edad_madre = self.edad(madre)
            if not (18 <= edad_madre <= 45):  # Solo si la madre está en edad fértil
                vistos.add(ced); vistos.add(pareja_id); 
                continue

            compat = self.indice_compatibilidad(ced, pareja_id)
            if compat < 0.75:  # Aseguramos que las parejas tengan compatibilidad alta
                vistos.add(ced); vistos.add(pareja_id); 
                continue

            if self._rng.random() <= prob_por_pareja:
                self._nacer_hijo(padre, madre)
            vistos.add(ced); vistos.add(pareja_id)


    def _nacer_hijo(self, padre: str, madre: str):
        """Genera un bebé con avatar aleatorio y asigna familia."""
        nombres_m = ["Sofía", "Valentina", "Camila", "Isabella", "María", "Daniela"]
        nombres_h = ["Santiago", "Mateo", "Sebastián", "Nicolás", "Diego", "Samuel"]
        genero = "Femenino" if self._rng.random() < 0.5 else "Masculino"
        nombre = self._rng.choice(nombres_m if genero == "Femenino" else nombres_h)
        ced = self._gen_cedula()

        fam_id = self.personas.get(padre, {}).get("familia") or self.personas.get(madre, {}).get("familia") or ""
        provincia = self.personas.get(self._rng.choice([padre, madre]), {}).get("provincia", "")

        avatar_bebe = self._rng.choice(["bebe1.png", "bebe2.png"])

        self.personas[ced] = {
            "familia": fam_id,
            "cedula": ced,
            "nombre": nombre,
            "nac": _iso(_today_with_year(self._anio_sim)),
            "falle": "",
            "genero": genero,
            "provincia": provincia,
            "estado": "Soltero/a",
            "avatar": avatar_bebe,
            "padre": self._combo(padre),
            "madre": self._combo(madre),
            "pareja": "",
            "filiacion": "Biológico/a",
            "adoptivos": [],
            "adoptado": "",
            "familias_extra": [],
        }
        self._extra[ced] = ExtraPersona()
        self._registrar_evento(padre, "hijo", f"Nació {nombre}")
        self._registrar_evento(madre, "hijo", f"Nació {nombre}")
        self._registrar_evento(ced, "nace", "Nacimiento")
        self._reforzar_salud(padre, 0.05)
        self._reforzar_salud(madre, 0.07)
        self._changed()
        self._reconstruir_kin()


    def _gen_cedula(self) -> str:
        while True:
            ced = f"B{self._rng.randint(100000, 999999)}"
            if ced not in self.personas:
                return ced

    # --------------------- Fallecimientos ---------------------

    def _prob_morir(self, ced: str) -> float:
        """Probabilidad de morir por salud/emocional o edad."""
        if not self.vivo(ced):
            return 0.0
        edad = self.edad(ced)
        base = 0.001
        if edad < 20: base = 0.0003
        elif edad < 40: base = 0.001
        elif edad < 60: base = 0.004
        elif edad < 75: base = 0.012
        elif edad < 80: base = 0.020
        else: base = 0.050  # Mucho mayor probabilidad para personas mayores de 80

        salud = self._extra[ced].salud_emocional
        factor_salud = 1.0 + (1.0 - salud)  # peor salud duplica el riesgo
        return min(0.50, base * factor_salud)


    def _intentar_fallecimientos(self):
        for ced, p in list(self.personas.items()):
            if not self.vivo(ced):
                continue
            if self._rng.random() <= self._prob_morir(ced):
                p["falle"] = _iso(_today_with_year(self._anio_sim))
                self._registrar_evento(ced, "fallece", "Fallecimiento")

                # Viudez del cónyuge
                pareja_id = self._id_from_combo(p.get("pareja",""))
                if pareja_id and pareja_id in self.personas and self.vivo(pareja_id):
                    self.personas[pareja_id]["estado"] = "Viudo/a"
                    self.personas[pareja_id]["pareja"] = ""
                    self._extra[pareja_id].viudo = True
                    self._registrar_evento(pareja_id, "viudez", f"Viudez por {p.get('nombre','')}")
                self._reconstruir_kin()

    # --------------------- Tutoría / Adopción ---------------------

    def _asignar_tutorias(self):
        for ced, p in list(self.personas.items()):
            if not self.vivo(ced):
                continue
            if self.edad(ced) >= 18:
                continue
            padre = self._id_from_combo(p.get("padre",""))
            madre = self._id_from_combo(p.get("madre",""))
            if not padre or not madre:
                continue
            padre_falle = (padre in self.personas) and (not self.vivo(padre))
            madre_falle = (madre in self.personas) and (not self.vivo(madre))
            if not (padre_falle and madre_falle):
                continue
            if self._extra[ced].tutor_legal:
                continue
            cand = self._mejor_tutor_para(ced)
            if cand:
                self._aplicar_adopcion(ced, cand)

    def _mejor_tutor_para(self, menor: str) -> Optional[str]:
        pools: List[List[str]] = []
        pools.append(self._kin.grandparents(menor))
        pools.append(self._kin.uncles_aunts(menor, include_inlaws=True))
        sibs = set(self._kin.full_siblings(menor)) | set(self._kin.half_siblings(menor))
        pools.append([s for s in sibs if self.edad(s) >= 18])
        pools.append([c for c in self._kin.cousins(menor) if self.edad(c) >= 21])

        for pool in pools:
            cand = [c for c in pool if c in self.personas and self.vivo(c) and self.edad(c) >= 18 and self._extra[c].salud_emocional > 0.5]
            if not cand:
                continue
            cand.sort(key=lambda c: (0 if self.casado(c) else 1, -self._extra[c].salud_emocional, -self.edad(c)))
            return cand[0]
        return None

    def _aplicar_adopcion(self, menor: str, tutor: str):
        p_menor = self.personas[menor]
        p_menor.setdefault("adoptivos", [])
        if tutor not in p_menor["adoptivos"]:
            p_menor["adoptivos"].append(tutor)
        self._extra[menor].tutor_legal = tutor
        self._extra[menor].adoptado = True
        p_menor["adoptado"] = "1"
        self._registrar_evento(menor, "adopcion", f"Tutoría/adopción por {self.personas[tutor].get('nombre','')}")
        self._registrar_evento(tutor, "tutoria", f"Asume tutoría de {p_menor.get('nombre','')}")
        self._reforzar_salud(tutor, 0.04)
