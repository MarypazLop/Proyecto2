import tkinter as tk
from tkinter import messagebox, ttk
import os
import random
from tkcalendar import DateEntry

# Archivos de datos
FAMILIAS_FILE = "familias.txt"
PERSONAS_FILE = "personas.txt"

# Provincias, géneros y estados civiles
PROVINCIAS = ["San José", "Alajuela", "Cartago", "Heredia", "Guanacaste", "Puntarenas", "Limón"]
GENEROS = ["Masculino", "Femenino", "Otro"]
ESTADOS_CIVILES = ["Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a"]

class RegistroApp(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Sistema Árbol Genealógico - Registro")
        self.geometry("600x650")
        self.resizable(False, False)
        self.configure(bg="#f5f5dc")

        self._crear_frames()
        self._crear_campos()
        self._crear_botones()
        self.cargar_familias()
        self.generar_id_familia()  # Genera ID inicial

        self.centrar_ventana()
        self.transient(parent)   # Hace que la ventana esté "encima" del menú
        self.grab_set()          # Modal: bloquea el menú hasta cerrar registro
        self.focus()             # Lleva el foco a la ventana de registro

    def centrar_ventana(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        x = (ws // 2) - (w // 2)
        y = (hs // 2) - (h // 2)
        self.geometry(f'{w}x{h}+{x}+{y}')


    # ------------------ FRAMES ------------------
    def _crear_frames(self):
        self.frame_familia = tk.LabelFrame(self, text="Gestión de Familias", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_familia.pack(fill="x", padx=20, pady=10)

        self.frame_persona = tk.LabelFrame(self, text="Gestión de Integrantes", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_persona.pack(fill="x", padx=20, pady=10)

    # ------------------ CAMPOS ------------------
    def _crear_campos(self):
        pad_y = 5

        # Familias
        tk.Label(self.frame_familia, text="ID Familia:", bg="#fff8dc").grid(row=0, column=0, sticky="w", pady=pad_y)
        self.entry_id_familia = tk.Entry(self.frame_familia, state="readonly")
        self.entry_id_familia.grid(row=0, column=1)
        self.btn_generar_id = tk.Button(self.frame_familia, text="Generar ID", command=self.generar_id_familia)
        self.btn_generar_id.grid(row=0, column=2, padx=5)

        tk.Label(self.frame_familia, text="Nombre Familia:", bg="#fff8dc").grid(row=1, column=0, sticky="w", pady=pad_y)
        self.entry_nombre_familia = tk.Entry(self.frame_familia)
        self.entry_nombre_familia.grid(row=1, column=1)

        # Personas
        tk.Label(self.frame_persona, text="Cédula:", bg="#fff8dc").grid(row=0, column=0, sticky="w", pady=pad_y)
        self.entry_cedula = tk.Entry(self.frame_persona)
        self.entry_cedula.grid(row=0, column=1)

        tk.Label(self.frame_persona, text="Nombre:", bg="#fff8dc").grid(row=1, column=0, sticky="w", pady=pad_y)
        self.entry_nombre = tk.Entry(self.frame_persona)
        self.entry_nombre.grid(row=1, column=1)

        tk.Label(self.frame_persona, text="Fecha Nacimiento:", bg="#fff8dc").grid(row=2, column=0, sticky="w", pady=pad_y)
        self.entry_nacimiento = DateEntry(self.frame_persona, date_pattern="yyyy-mm-dd")
        self.entry_nacimiento.grid(row=2, column=1)

        # Fallecimiento dinámico
        tk.Label(self.frame_persona, text="¿Ha fallecido?", bg="#fff8dc").grid(row=3, column=0, sticky="w", pady=pad_y)
        self.fallecido_var = tk.StringVar(value="No")
        self.combo_fallecido = ttk.Combobox(self.frame_persona, textvariable=self.fallecido_var, values=["No", "Sí"], state="readonly", width=17)
        self.combo_fallecido.grid(row=3, column=1)
        self.combo_fallecido.bind("<<ComboboxSelected>>", self._mostrar_fecha_fallecimiento)

        self.lbl_fallecimiento = tk.Label(self.frame_persona, text="Fecha Fallecimiento:", bg="#fff8dc")
        self.entry_fallecimiento = DateEntry(self.frame_persona, date_pattern="yyyy-mm-dd")
        # Oculto al inicio
        self.lbl_fallecimiento.grid_forget()
        self.entry_fallecimiento.grid_forget()

        tk.Label(self.frame_persona, text="Género:", bg="#fff8dc").grid(row=5, column=0, sticky="w", pady=pad_y)
        self.genero_var = tk.StringVar(value=GENEROS[0])
        self.menu_genero = ttk.OptionMenu(self.frame_persona, self.genero_var, *GENEROS)
        self.menu_genero.grid(row=5, column=1)

        tk.Label(self.frame_persona, text="Provincia:", bg="#fff8dc").grid(row=6, column=0, sticky="w", pady=pad_y)
        self.provincia_var = tk.StringVar(value=PROVINCIAS[0])
        self.menu_provincia = ttk.OptionMenu(self.frame_persona, self.provincia_var, *PROVINCIAS)
        self.menu_provincia.grid(row=6, column=1)

        tk.Label(self.frame_persona, text="Estado Civil:", bg="#fff8dc").grid(row=7, column=0, sticky="w", pady=pad_y)
        self.estado_var = tk.StringVar(value=ESTADOS_CIVILES[0])
        self.menu_estado = ttk.OptionMenu(self.frame_persona, self.estado_var, *ESTADOS_CIVILES)
        self.menu_estado.grid(row=7, column=1)

        tk.Label(self.frame_persona, text="Familia:", bg="#fff8dc").grid(row=8, column=0, sticky="w", pady=pad_y)
        self.combo_familias = ttk.Combobox(self.frame_persona, state="readonly", width=20)
        self.combo_familias.grid(row=8, column=1)

    # ------------------ BOTONES ------------------
    def _crear_botones(self):
        self.btn_guardar_familia = tk.Button(self.frame_familia, text="Registrar Familia", command=self.guardar_familia)
        self.btn_guardar_familia.grid(row=2, column=0, columnspan=2, pady=10)

        self.btn_guardar_persona = tk.Button(self.frame_persona, text="Registrar Persona", command=self.guardar_persona)
        self.btn_guardar_persona.grid(row=9, column=0, columnspan=2, pady=10)

    # ------------------ FUNCIONES ------------------
    def generar_id_familia(self):
        nuevo_id = str(random.randint(1000, 9999))
        self.entry_id_familia.config(state="normal")
        self.entry_id_familia.delete(0, tk.END)
        self.entry_id_familia.insert(0, nuevo_id)
        self.entry_id_familia.config(state="readonly")

    def cargar_familias(self):
        """Carga las familias desde el archivo y actualiza el combobox"""
        if not os.path.exists(FAMILIAS_FILE):
            familias = []
        else:
            with open(FAMILIAS_FILE, "r", encoding="utf-8") as f:
                familias = [line.strip().split(";") for line in f if line.strip()]
        opciones = [f"{fid} - {nombre}" for fid, nombre in familias]
        self.combo_familias['values'] = opciones
        if opciones:
            self.combo_familias.current(0)

    def _mostrar_fecha_fallecimiento(self, event=None):
        if self.fallecido_var.get() == "Sí":
            self.lbl_fallecimiento.grid(row=4, column=0, sticky="w", pady=5)
            self.entry_fallecimiento.grid(row=4, column=1)
        else:
            self.lbl_fallecimiento.grid_forget()
            self.entry_fallecimiento.grid_forget()

    def guardar_familia(self):
        fid = self.entry_id_familia.get().strip()
        nombre = self.entry_nombre_familia.get().strip()
        if not fid or not nombre:
            messagebox.showerror("Error", "Todos los campos de la familia son obligatorios.")
            return
        with open(FAMILIAS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{fid};{nombre}\n")
        messagebox.showinfo("Éxito", f"Familia '{nombre}' registrada.")
        self.entry_nombre_familia.delete(0, tk.END)
        self.generar_id_familia()
        self.cargar_familias()

    def guardar_persona(self):
        cedula = self.entry_cedula.get().strip()
        nombre = self.entry_nombre.get().strip()
        nacimiento = self.entry_nacimiento.get_date()
        fallecimiento = self.entry_fallecimiento.get_date() if self.fallecido_var.get() == "Sí" else ""
        genero = self.genero_var.get()
        provincia = self.provincia_var.get()
        estado = self.estado_var.get()
        familia = self.combo_familias.get()
        if not cedula or not nombre or not nacimiento or not genero or not provincia or not estado or not familia:
            messagebox.showerror("Error", "Todos los campos son obligatorios.")
            return
        with open(PERSONAS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{familia};{cedula};{nombre};{nacimiento};{fallecimiento};{genero};{provincia};{estado}\n")
        messagebox.showinfo("Éxito", f"Persona '{nombre}' registrada en familia {familia}.")
        self._limpiar_formulario()

    def _limpiar_formulario(self):
        self.entry_cedula.delete(0, tk.END)
        self.entry_nombre.delete(0, tk.END)
        self.entry_nacimiento.set_date("")
        self.entry_fallecimiento.set_date("")
        self.fallecido_var.set("No")
        self._mostrar_fecha_fallecimiento()
        self.genero_var.set(GENEROS[0])
        self.provincia_var.set(PROVINCIAS[0])
        self.estado_var.set(ESTADOS_CIVILES[0])
        if self.combo_familias['values']:
            self.combo_familias.current(0)
