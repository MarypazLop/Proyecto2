# -*- coding: utf-8 -*-
import os
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from kinship import Kinship

# Reutilizamos rutas como en tree.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAMILIAS_FILE = os.path.join(BASE_DIR, "familias.txt")
PERSONAS_FILE = os.path.join(BASE_DIR, "personas.txt")

# ------------------ Utilidades ------------------

def _id_from_combo(text: str) -> str:
    if not text:
        return ""
    return text.split(" - ")[0].strip()

def _load_familias():
    out = []
    if os.path.exists(FAMILIAS_FILE):
        with open(FAMILIAS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                partes = line.split(";")
                if len(partes) >= 2:
                    out.append((partes[0].strip(), partes[1].strip()))
    return out

def _load_personas():
    p = {}
    if os.path.exists(PERSONAS_FILE):
        with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = line.split(";")
                if len(d) < 13:
                    continue
                fam_id = d[0].split(" - ")[0].strip()
                p[d[1].strip()] = {
                    "familia": fam_id,
                    "cedula": d[1].strip(),
                    "nombre": d[2].strip(),
                    "nac": d[3].strip(),
                    "falle": d[4].strip(),
                    "genero": d[5].strip(),
                    "provincia": d[6].strip(),
                    "estado": d[7].strip(),
                    "avatar": d[8].strip(),
                    "padre": d[9].strip(),
                    "madre": d[10].strip(),
                    "pareja": d[11].strip(),
                    "filiacion": d[12].strip()
                }
    return p

def _person_label(ced: str, personas: dict) -> str:
    if not ced:
        return ""
    p = personas.get(ced, {})
    return f"{ced} - {p.get('nombre', ced)}"

def _parse_date_relaxed(s: str):
    """Acepta 'YYYY-MM-DD', 'YYYY/MM/DD', 'DD/MM/YYYY' o 'YYYY'. Devuelve date o None."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _strip_accents_lower(s: str) -> str:
    table = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return (s or "").translate(table).lower().strip()

def _is_alive(p: dict) -> bool:
    return not (p.get("falle") or "").strip()

# ------------------ Ventana ------------------

class QueriesApp(tk.Toplevel):
    """
    Ventana de consultas de parentesco:
    - Persona A: consultas de 1 entrada (padres, hijos, etc.)
    - Persona B: etiqueta de relación A ↔ B
    - Filtro por familia para listas más cortas
    - Consultas globales (b, c, d) que no dependen de A/B
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Family Tree - Queries")
        self.geometry("980x640")
        self.minsize(880, 560)
        self.configure(bg="#f5f5dc")

        # Data
        self.familias = _load_familias()
        self.personas = _load_personas()
        self.kin = Kinship(self.personas)

        # --- UI layout ---
        container = tk.Frame(self, bg="#f5f5dc")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # Fila superior: selects
        top = tk.Frame(container, bg="#f5f5dc")
        top.pack(fill="x", pady=(0, 10))

        tk.Label(top, text="Familia:", bg="#f5f5dc").grid(row=0, column=0, sticky="w")
        self.sel_familia = tk.StringVar()
        fam_values = [f"{fid} - {name}" for fid, name in self.familias]
        self.cmb_familia = ttk.Combobox(top, textvariable=self.sel_familia, values=fam_values, state="readonly", width=40)
        self.cmb_familia.grid(row=0, column=1, padx=6, sticky="w")
        self.cmb_familia.bind("<<ComboboxSelected>>", self._refill_people)

        tk.Label(top, text="Persona A:", bg="#f5f5dc").grid(row=0, column=2, padx=(16, 0), sticky="e")
        self.sel_a = tk.StringVar()
        self.cmb_a = ttk.Combobox(top, textvariable=self.sel_a, state="readonly", width=44)
        self.cmb_a.grid(row=0, column=3, padx=6, sticky="w")

        tk.Label(top, text="Persona B:", bg="#f5f5dc").grid(row=0, column=4, padx=(16, 0), sticky="e")
        self.sel_b = tk.StringVar()
        self.cmb_b = ttk.Combobox(top, textvariable=self.sel_b, state="readonly", width=44)
        self.cmb_b.grid(row=0, column=5, padx=6, sticky="w")

        # Botonera (consultas de una persona)
        cmds = tk.LabelFrame(container, text="Consultas (Persona A)", bg="#fff8dc")
        cmds.pack(fill="x", pady=(0, 10))

        btns = [
            ("Padres", self.q_parents),
            ("Hijos", self.q_children),
            ("Cónyuge", self.q_spouse),
            ("Hermanos (completos)", self.q_full_sibs),
            ("Medios hermanos", self.q_half_sibs),
            ("Abuelos", self.q_grandparents),
            ("Nietos", self.q_grandchildren),
            ("Tíos/Tías", self.q_uncles_aunts),
            ("Primos", self.q_cousins),
            ("Sobrinos", self.q_nieces_nephews),
        ]
        for i, (txt, fn) in enumerate(btns):
            tk.Button(cmds, text=txt, command=fn, width=20).grid(row=i//3, column=i%3, padx=6, pady=6, sticky="w")

        # Segunda fila: relación A ↔ B
        relation = tk.LabelFrame(container, text="Relación entre A y B", bg="#fff8dc")
        relation.pack(fill="x", pady=(0, 10))
        tk.Button(relation, text="Etiquetar relación A ↔ B", command=self.q_relation, width=25).grid(row=0, column=0, padx=6, pady=6, sticky="w")

        # NUEVO: Consultas globales (b, c, d)
        global_box = tk.LabelFrame(container, text="Consultas globales", bg="#fff8dc")
        global_box.pack(fill="x", pady=(0, 10))

        tk.Button(global_box, text="(b) Nacidos últimos 10 años", command=self.q_births_last_10y, width=28)\
            .grid(row=0, column=0, padx=6, pady=6, sticky="w")

        tk.Button(global_box, text="(c) Parejas actuales con ≥2 hijos", command=self.q_couples_two_plus_children, width=32)\
            .grid(row=0, column=1, padx=6, pady=6, sticky="w")

        tk.Button(global_box, text="(d) Fallecidos antes de 50 años", command=self.q_died_before_50, width=30)\
            .grid(row=0, column=2, padx=6, pady=6, sticky="w")

        # Resultados
        results = tk.LabelFrame(container, text="Resultados", bg="#fff8dc")
        results.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(results, bg="#fffaf0")
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)

        # Cargar combos
        if self.familias:
            self.sel_familia.set(fam_values[0])
        self._refill_people()

    # ---------------- helpers ----------------
    def _people_for_family(self, fam_id: str):
        ceds = [
            ced for ced, p in self.personas.items()
            if p.get("familia", "") == fam_id or fam_id in (p.get("familias_extra") or [])
        ]
        # Orden por nombre
        ceds = sorted(set(ceds), key=lambda c: self.personas[c]["nombre"].lower())
        return [ _person_label(c, self.personas) for c in ceds ]

    def _refill_people(self, *_):
        fam_id = _id_from_combo(self.sel_familia.get())
        values = self._people_for_family(fam_id) if fam_id else [
            _person_label(c, self.personas) for c in sorted(self.personas.keys())
        ]
        self.cmb_a["values"] = values
        self.cmb_b["values"] = values
        if values:
            self.sel_a.set(values[0])
            if len(values) > 1:
                self.sel_b.set(values[1])

    def _get_ced_a(self):
        return _id_from_combo(self.sel_a.get())

    def _get_ced_b(self):
        return _id_from_combo(self.sel_b.get())

    def _fill(self, rows):
        self.listbox.delete(0, tk.END)
        if not rows:
            self.listbox.insert(tk.END, "— Sin resultados —")
            return
        for r in rows:
            self.listbox.insert(tk.END, r)

    # ---------------- consultas (A) ----------------
    def q_parents(self):
        a = self._get_ced_a()
        fa, ma = self.kin.get_parents(a)   # Kinship.get_parents
        out = []
        if fa: out.append("Padre:  " + _person_label(fa, self.personas))
        if ma: out.append("Madre:  " + _person_label(ma, self.personas))
        self._fill(out)

    def q_children(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.get_children(a)) ]
        self._fill(rows)

    def q_spouse(self):
        a = self._get_ced_a()
        b = self.kin.get_spouse(a)
        self._fill([_person_label(b, self.personas)] if b else [])

    def q_full_sibs(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.full_siblings(a)) ]
        self._fill(rows)

    def q_half_sibs(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.half_siblings(a)) ]
        self._fill(rows)

    def q_grandparents(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.grandparents(a)) ]
        self._fill(rows)

    def q_grandchildren(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.grandchildren(a)) ]
        self._fill(rows)

    def q_uncles_aunts(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.uncles_aunts(a, include_inlaws=True)) ]
        self._fill(rows)

    def q_cousins(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.cousins(a)) ]
        self._fill(rows)

    def q_nieces_nephews(self):
        a = self._get_ced_a()
        rows = [ _person_label(c, self.personas) for c in sorted(self.kin.nieces_nephews(a)) ]
        self._fill(rows)

    # ---------------- relación A ↔ B ----------------
    def q_relation(self):
        a = self._get_ced_a()
        b = self._get_ced_b()
        label = self.kin.relation_label(a, b)
        self._fill([f"{_person_label(a, self.personas)}  ↔  {_person_label(b, self.personas)} :  {label}"])

    # ---------------- Consultas globales (b, c, d) ----------------
    def q_births_last_10y(self):
        """(b) ¿Cuántas personas nacieron en los últimos 10 años? + listado."""
        today = date.today()
        # threshold = today - 10 años (ajuste por 29 de febrero)
        try:
            threshold = today.replace(year=today.year - 10)
        except ValueError:
            threshold = today.replace(year=today.year - 10, month=2, day=28)

        hits = []
        for ced, p in self.personas.items():
            d = _parse_date_relaxed(p.get("nac", ""))
            if d and d >= threshold:
                hits.append(ced)

        hits_sorted = sorted(hits, key=lambda c: self.personas[c]["nombre"].lower())
        rows = [f"Total (últimos 10 años): {len(hits_sorted)}"]
        rows += [_person_label(c, self.personas) for c in hits_sorted]
        self._fill(rows)

    def _current_couples(self):
        """Parejas 'vigentes' por estado civil y pareja mutua."""
        allowed = {"casado/a", "casado", "casada", "union libre"}
        pairs = set()
        for a, pa in self.personas.items():
            estado_a = _strip_accents_lower(pa.get("estado", ""))
            pareja_txt = pa.get("pareja", "")
            if estado_a in allowed and pareja_txt:
                b = _id_from_combo(pareja_txt)
                if not b or b not in self.personas:
                    continue
                pb = self.personas[b]
                estado_b = _strip_accents_lower(pb.get("estado", ""))
                pareja_b = _id_from_combo(pb.get("pareja", ""))
                if estado_b in allowed and pareja_b == a:
                    pair = tuple(sorted((a, b)))
                    pairs.add(pair)
        return pairs

    def q_couples_two_plus_children(self):
        """(c) ¿Cuáles parejas actuales tienen 2 o más hijos en común?"""
        pairs = self._current_couples()
        rows = []
        for a, b in sorted(pairs, key=lambda t: (self.personas[t[0]]["nombre"].lower(), self.personas[t[1]]["nombre"].lower())):
            ca = set(self.kin.get_children(a))
            cb = set(self.kin.get_children(b))
            comunes = sorted(ca & cb)
            if len(comunes) >= 2:
                hijos_txt = ", ".join(_person_label(c, self.personas) for c in comunes)
                rows.append(f"{_person_label(a, self.personas)}  ↔  {_person_label(b, self.personas)}  — hijos en común: {len(comunes)} [{hijos_txt}]")
        if not rows:
            rows = ["— Sin resultados —"]
        self._fill(rows)

    def q_died_before_50(self):
        """(d) ¿Cuántas personas fallecieron antes de cumplir 50 años? + listado."""
        hits = []
        for ced, p in self.personas.items():
            dn = _parse_date_relaxed(p.get("nac", ""))
            df = _parse_date_relaxed(p.get("falle", ""))
            if not dn or not df:
                continue
            # Edad exacta por comparación (sin librerías extra)
            age = df.year - dn.year - ((df.month, df.day) < (dn.month, dn.day))
            if age < 50:
                hits.append(ced)

        hits_sorted = sorted(hits, key=lambda c: self.personas[c]["nombre"].lower())
        rows = [f"Total (fallecieron < 50 años): {len(hits_sorted)}"]
        rows += [_person_label(c, self.personas) for c in hits_sorted]
        self._fill(rows)

