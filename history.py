# history.py
# -*- coding: utf-8 -*-
"""
Historial de eventos por persona (sidecar file: historial.txt)

Formato por línea:
  fecha_iso;cedula;tipo;detalle

Ejemplos:
  2005-06-01;1-1234-5678;NACIMIENTO;Nació en San José
  2024-08-31;1-5678-1234;UNION;Se unió con 1-2345-6789 - Ana Gómez
  2038-02-10;1-2345-6789;HIJO;Tuvo un hijo: 1-0001 - Bebe Pérez
  2044-05-20;1-1234-5678;VIUDEZ;Quedó viudo/a de 1-2345-6789 - Ana Gómez
  2070-11-02;1-2345-6789;FALLECIMIENTO;Falleció (70 años)

Tipos sugeridos: NACIMIENTO, UNION, HIJO, VIUDEZ, FALLECIMIENTO, CUMPLEANOS, EMOCION, OTRO
"""

import os
from datetime import date, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HIST_FILE = os.path.join(BASE_DIR, "historial.txt")

def _ensure_file():
    if not os.path.exists(HIST_FILE):
        with open(HIST_FILE, "w", encoding="utf-8") as f:
            pass

def record_event(cedula: str, tipo: str, detalle: str = "", fecha: date | None = None):
    """Registra un evento (append) en historial.txt."""
    _ensure_file()
    if fecha is None:
        fecha = date.today()
    fecha_txt = fecha.strftime("%Y-%m-%d")
    linea = f"{fecha_txt};{cedula};{tipo};{detalle}".strip()
    with open(HIST_FILE, "a", encoding="utf-8") as f:
        f.write(linea + "\n")

def get_history(cedula: str):
    """Devuelve lista de eventos de esa cédula, ordenados por fecha ascendente.
    Cada item: dict(fecha: date, tipo: str, detalle: str)"""
    _ensure_file()
    out = []
    with open(HIST_FILE, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            # fecha;ced;tipo;detalle
            parts = ln.split(";", 3)
            if len(parts) < 3:
                continue
            fecha_txt, ced, tipo = parts[0].strip(), parts[1].strip(), parts[2].strip()
            detalle = parts[3].strip() if len(parts) >= 4 else ""
            if ced != cedula:
                continue
            try:
                dt = datetime.strptime(fecha_txt, "%Y-%m-%d").date()
            except Exception:
                # Si viene YYYY o DD/MM/YYYY, trata de parsear de forma relajada
                for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%Y"):
                    try:
                        dt = datetime.strptime(fecha_txt, fmt).date()
                        break
                    except Exception:
                        dt = None
                if dt is None:
                    continue
            out.append({"fecha": dt, "tipo": tipo, "detalle": detalle})
    out.sort(key=lambda e: e["fecha"])
    return out

# Helpers semánticos
def rec_nacimiento(cedula: str, detalle: str = "", fecha: date | None = None):
    record_event(cedula, "NACIMIENTO", detalle, fecha)

def rec_union(ced_a: str, ced_b_label: str, fecha: date | None = None):
    record_event(ced_a, "UNION", f"Se unió con {ced_b_label}", fecha)

def rec_hijo(ced_padre_o_madre: str, hijo_label: str, fecha: date | None = None):
    record_event(ced_padre_o_madre, "HIJO", f"Tuvo un hijo: {hijo_label}", fecha)

def rec_viudez(cedula: str, conyuge_label: str, fecha: date | None = None):
    record_event(cedula, "VIUDEZ", f"Quedó viudo/a de {conyuge_label}", fecha)

def rec_fallecimiento(cedula: str, detalle: str = "", fecha: date | None = None):
    record_event(cedula, "FALLECIMIENTO", detalle, fecha)

def rec_cumple(cedula: str, edad: int, fecha: date | None = None):
    record_event(cedula, "CUMPLEANOS", f"Cumplió {edad}", fecha)

def rec_emocion(cedula: str, detalle: str, fecha: date | None = None):
    record_event(cedula, "EMOCION", detalle, fecha)

