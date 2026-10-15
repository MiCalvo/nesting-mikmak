"""Paso 2 · Material y parámetros: parámetros del proyecto y ajustes generales de importación.

Los parámetros del proyecto se guardan en el .json del proyecto. Los ajustes
generales (tolerancia de unión, área mínima) son de la aplicación y se guardan
con QSettings; se aplican a las importaciones siguientes.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..engine.params import SIDES, NestParams
from ..engine.fill import PROBE_TIME
from ..engine.timing import MAX_TIME, describe, rotation_factor, sheet_time
from ..importers.contours import ImportOptions
from ..profiles import Profile, load_profiles, save_profiles
from . import style


def profiles_path() -> Path:
    """perfiles.json en la carpeta de datos de la aplicación (en Windows, dentro de AppData)."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "perfiles.json"

ROTATION_STEPS = [("Cada 90°", 90.0), ("Cada 45°", 45.0), ("Cada 15°", 15.0), ("Libre", None)]
# perfil de cálculo: modo automático con su finura, o tiempo fijo
CALC_MODES = [("Automático · Rápido (para tantear)", "rapido"),
              ("Automático · Normal (recomendado)", "normal"),
              ("Automático · Fino (tiradas grandes)", "fino"),
              ("Fijo (segundos por plancha)", "fijo")]


def _dspin(lo, hi, dec, suffix, step=1.0) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setSuffix(suffix)
    return w


def _find_data(combo: QComboBox, value) -> int:
    """Como QComboBox.findData, pero también encuentra el elemento cuyo dato es None."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            return i
    return -1


class ParamsPanel(QWidget):
    # True si el cambio afecta al resultado del nesting (material y espesor no)
    changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base = NestParams()
        self._loading = False

        # --- plancha -----------------------------------------------------------
        self.width = _dspin(1, 100000, 1, " mm", 10)
        self.height = _dspin(1, 100000, 1, " mm", 10)
        self.max_sheets = QSpinBox()
        self.max_sheets.setRange(0, 999)
        self.max_sheets.setSpecialValueText("Ilimitado")
        self.separation = _dspin(0, 1000, 2, " mm", 0.5)
        self.margin = _dspin(0, 1000, 2, " mm", 0.5)
        sheet = QGroupBox("Plancha")
        f = QFormLayout(sheet)
        f.addRow("Ancho (X):", self.width)
        f.addRow("Alto (Y):", self.height)
        f.addRow("Planchas disponibles:", self.max_sheets)
        f.addRow("Separación entre piezas:", self.separation)
        f.addRow("Margen al borde:", self.margin)
        note = QLabel("Separación y margen de 5 mm: provisionales hasta que los confirme el proveedor.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {style.WARN};")
        f.addRow(note)

        # --- nesting -------------------------------------------------------------
        self.rotation = QComboBox()
        for text, step in ROTATION_STEPS:
            self.rotation.addItem(text, step)
        self.part_in_part = QCheckBox("Meter piezas pequeñas en los huecos de las grandes")
        self.side = QComboBox()
        for s in SIDES:
            self.side.addItem(s.capitalize(), s)
        self.calc_mode = QComboBox()
        for text, mode in CALC_MODES:
            self.calc_mode.addItem(text, mode)
        self.time_limit = QSpinBox()       # solo en modo fijo
        self.time_limit.setRange(1, 3600)
        self.time_limit.setValue(30)
        self.time_limit.setSuffix(" s por plancha")
        self.time_estimate = QLabel()
        self.time_estimate.setWordWrap(True)
        self.parts_fn = lambda: []         # piezas del proyecto, para estimar el tiempo
        self.fix_seed = QCheckBox("Fijar")
        self.seed = QSpinBox()
        self.seed.setRange(0, 2 ** 31 - 1)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.fix_seed)
        seed_row.addWidget(self.seed, 1)
        # --- qué calcular ------------------------------------------------------------
        self.goal = QComboBox()
        self.goal.addItem("Cantidades fijas (las de cada pieza)", "cantidades")
        self.goal.addItem("Rellenar la plancha (máximo de juegos)", "rellenar")
        self.fill_with = QComboBox()
        self._fill_wanted: str | None = None
        self._fill_names: list[str] | None = None
        goal_box = QGroupBox("Qué calcular")
        gf = QFormLayout(goal_box)
        gf.addRow("Modo:", self.goal)
        gf.addRow("Rellenar el hueco con:", self.fill_with)
        self.goal_hint = QLabel()
        self.goal_hint.setWordWrap(True)
        self.goal_hint.setObjectName("muted")
        gf.addRow(self.goal_hint)
        self.goal_box = goal_box

        nest_box = QGroupBox("Nesting")
        f = QFormLayout(nest_box)
        f.addRow("Rotaciones permitidas:", self.rotation)
        f.addRow("Pieza dentro de pieza:", self.part_in_part)
        f.addRow("Compactar hacia:", self.side)
        f.addRow("Perfil de cálculo:", self.calc_mode)
        f.addRow("Tiempo fijo:", self.time_limit)
        f.addRow("", self.time_estimate)
        calc_hint = QLabel("Automático: el tiempo crece con el nº de copias y con las rotaciones permitidas "
                           f"(45° ×2; 15° o libre ×3), hasta {MAX_TIME} s por plancha. Medido con tus juntas: "
                           "pasar de Normal a Fino mejora el largo menos de un 1 %.")
        calc_hint.setWordWrap(True)
        calc_hint.setObjectName("muted")
        f.addRow(calc_hint)
        f.addRow("Semilla (avanzado):", seed_row)
        hint = QLabel("Con la semilla fijada, el mismo proyecto da siempre el mismo resultado.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        f.addRow(hint)

        # --- perfiles de material --------------------------------------------------
        self.profiles: list[Profile] = []
        self.profile_combo = QComboBox()
        b_apply = QPushButton("Aplicar al proyecto")
        b_apply.setToolTip("Copia plancha, separación, margen, material y espesor del perfil al proyecto.")
        b_apply.clicked.connect(self.apply_selected_profile)
        b_save = QPushButton("Guardar como perfil…")
        b_save.clicked.connect(self.save_as_profile)
        self.b_delete_profile = QPushButton("Eliminar perfil")
        self.b_delete_profile.clicked.connect(self.delete_selected_profile)
        prof = QGroupBox("Perfil de material (plantilla reutilizable)")
        pv = QVBoxLayout(prof)
        pv.addWidget(self.profile_combo)
        pb = QHBoxLayout()
        pb.addWidget(b_apply)
        pb.addWidget(b_save)
        pb.addWidget(self.b_delete_profile)
        pv.addLayout(pb)
        self.reload_profiles()

        # --- material (informativo) ---------------------------------------------
        self.material = QLineEdit()
        self.thickness = QLineEdit()
        mat = QGroupBox("Material (informativo)")
        f = QFormLayout(mat)
        f.addRow("Material:", self.material)
        f.addRow("Espesor:", self.thickness)

        # --- ajustes generales de importación ------------------------------------
        self.tolerance = _dspin(0, 10, 3, " mm", 0.005)
        self.min_area = _dspin(0, 1e6, 2, " mm²", 0.5)
        imp = QGroupBox("Ajustes generales de importación (de la aplicación, no del proyecto)")
        f = QFormLayout(imp)
        f.addRow("Tolerancia de unión de trazos:", self.tolerance)
        f.addRow("Área mínima de contorno:", self.min_area)
        imp_hint = QLabel("Se aplican a las importaciones siguientes; no cambian piezas ya importadas.")
        imp_hint.setWordWrap(True)
        imp_hint.setObjectName("muted")
        f.addRow(imp_hint)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(12)
        right.setSpacing(12)
        left.addWidget(prof)
        left.addWidget(sheet)
        left.addWidget(mat)
        left.addStretch(1)
        right.addWidget(goal_box)
        right.addWidget(nest_box)
        right.addWidget(imp)
        right.addStretch(1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 6, 16, 14)
        cl.addLayout(cols)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(style.page_scroll(content))

        self.set_params(NestParams())
        self._load_settings()

        for w in (self.width, self.height, self.separation, self.margin):
            w.valueChanged.connect(lambda *_: self._emit(True))
        for w in (self.max_sheets, self.time_limit, self.seed):
            w.valueChanged.connect(lambda *_: self._emit(True))
        self.calc_mode.currentIndexChanged.connect(lambda *_: self._emit(True))
        self.goal.currentIndexChanged.connect(lambda *_: self._emit(True))
        self.fill_with.activated.connect(self._fill_with_chosen)
        for w in (self.rotation, self.side):
            w.currentIndexChanged.connect(lambda *_: self._emit(True))
        self.part_in_part.toggled.connect(lambda *_: self._emit(True))
        self.fix_seed.toggled.connect(self._seed_toggled)
        for w in (self.material, self.thickness):
            w.textEdited.connect(lambda *_: self._emit(False))
        self.tolerance.valueChanged.connect(self._save_settings)
        self.min_area.valueChanged.connect(self._save_settings)

    def _seed_toggled(self, on: bool):
        self.seed.setEnabled(on)
        self._emit(True)

    def _emit(self, affects: bool):
        self.refresh_estimate()
        if not self._loading:
            self.changed.emit(affects)

    def _fill_with_chosen(self, *_):
        self._fill_wanted = self.fill_with.currentData()
        self._emit(True)

    def refresh_parts(self) -> None:
        """Lista de referencias para rellenar el hueco (cambia al importar o renombrar piezas)."""
        names = [q.name for q in self.parts_fn()]
        if names != self._fill_names:
            self._fill_names = names
            self.fill_with.blockSignals(True)
            self.fill_with.clear()
            self.fill_with.addItem("Nada: solo juegos completos", None)
            for n in names:
                self.fill_with.addItem(n, n)
            self.fill_with.setCurrentIndex(max(0, _find_data(self.fill_with, self._fill_wanted)))
            self.fill_with.blockSignals(False)
        filling = self.goal.currentData() == "rellenar"
        self.fill_with.setEnabled(filling)
        self.goal_hint.setText(
            "Las cantidades de las piezas se leen como PROPORCIÓN (2, 1, 1 = juegos de 2 de la primera y 1 de "
            "cada otra) y se busca cuántos juegos completos caben en UNA plancha; después, el hueco que quede se "
            f"rellena con la referencia elegida. Varios intentos de {PROBE_TIME} s y la colocación final con el "
            "perfil de cálculo. Resultado: «caben al menos N»." if filling else
            "Se colocan las cantidades pedidas de cada pieza, en tantas planchas como haga falta.")

    def refresh_estimate(self) -> int | None:
        """Pone (y devuelve) los segundos estimados para la primera plancha."""
        self.refresh_parts()
        fixed = self.calc_mode.currentData() == "fijo"
        self.time_limit.setEnabled(fixed)
        p = self.params()
        if p.mode == "rellenar":
            self.time_estimate.setText(f"Rellenar: intentos de {PROBE_TIME} s (normalmente entre 5 y 15) y "
                                       f"colocación final «{describe(p.time_limit, p.fineness)}».")
            return None
        items = [(q.quantity, q.rotations if q.rotations is not None else p.angles())
                 for q in self.parts_fn() if q.quantity > 0]
        secs = sheet_time(p.time_limit, p.fineness, items)
        if fixed:
            self.time_estimate.setText(f"{secs} s por plancha, sin ajuste automático.")
        elif not items:
            self.time_estimate.setText("El tiempo se calculará según las piezas que importes.")
            return None
        else:
            copies = sum(n for n, _ in items)
            f = sum(n * rotation_factor(a) for n, a in items) / copies
            self.time_estimate.setText(f"≈ {secs} s por plancha ({copies} copias"
                                       + (f", rotaciones ×{f:.1f}".replace(".", ",") if f > 1 else "")
                                       + (f"; máximo {MAX_TIME} s" if secs >= MAX_TIME else "") + ").")
        return secs

    # --- parámetros del proyecto ----------------------------------------------------
    def params(self) -> NestParams:
        return replace(
            self._base,
            sheet_width=self.width.value(), sheet_height=self.height.value(),
            max_sheets=self.max_sheets.value() or None,
            separation=self.separation.value(), margin=self.margin.value(),
            rotation_step=self.rotation.currentData(),
            part_in_part=self.part_in_part.isChecked(),
            compact_side=self.side.currentData(),
            time_limit=self.time_limit.value() if self.calc_mode.currentData() == "fijo" else None,
            fineness=(self.calc_mode.currentData() if self.calc_mode.currentData() != "fijo"
                      else self._base.fineness),
            seed=self.seed.value() if self.fix_seed.isChecked() else None,
            material=self.material.text(), thickness=self.thickness.text(),
            mode=self.goal.currentData(), fill_with=self._fill_wanted)

    def set_params(self, p: NestParams) -> None:
        self._loading = True
        try:
            self._base = p
            self.width.setValue(p.sheet_width)
            self.height.setValue(p.sheet_height)
            self.max_sheets.setValue(p.max_sheets or 0)
            self.separation.setValue(p.separation)
            self.margin.setValue(p.margin)
            i = _find_data(self.rotation, p.rotation_step)
            if i < 0:  # paso no estándar (p. ej. puesto desde la línea de comandos)
                self.rotation.addItem(f"Cada {p.rotation_step:g}°", p.rotation_step)
                i = self.rotation.count() - 1
            self.rotation.setCurrentIndex(i)
            self.part_in_part.setChecked(p.part_in_part)
            self.side.setCurrentIndex(max(0, _find_data(self.side, p.compact_side)))
            self.goal.setCurrentIndex(max(0, _find_data(self.goal, p.mode)))
            self._fill_wanted = p.fill_with
            self._fill_names = None          # rehacer la lista con la selección guardada
            mode = "fijo" if p.time_limit is not None else p.fineness
            self.calc_mode.setCurrentIndex(max(0, _find_data(self.calc_mode, mode)))
            if p.time_limit is not None:
                self.time_limit.setValue(int(p.time_limit))
            self.fix_seed.setChecked(p.seed is not None)
            self.seed.setValue(p.seed or 0)
            self.seed.setEnabled(p.seed is not None)
            self.material.setText(p.material)
            self.thickness.setText(p.thickness)
        finally:
            self._loading = False
        self.refresh_estimate()

    # --- perfiles ---------------------------------------------------------------------
    def reload_profiles(self):
        try:
            self.profiles = load_profiles(profiles_path())
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Perfiles", f"No se pudieron leer los perfiles ({e}).")
            self.profiles = []
        self.profile_combo.clear()
        for pr in self.profiles:
            self.profile_combo.addItem(pr.name)
        self.b_delete_profile.setEnabled(bool(self.profiles))

    def apply_profile(self, pr: Profile):
        self.set_params(pr.apply_to(self.params()))
        self.changed.emit(True)

    def apply_selected_profile(self):
        i = self.profile_combo.currentIndex()
        if 0 <= i < len(self.profiles):
            self.apply_profile(self.profiles[i])

    def save_as_profile(self):
        name, ok = QInputDialog.getText(self, "Guardar perfil", "Nombre del perfil:",
                                        text=self.profile_combo.currentText())
        name = name.strip()
        if not ok or not name:
            return
        new = Profile.from_params(name, self.params())
        existing = [i for i, pr in enumerate(self.profiles) if pr.name == name]
        if existing:
            r = QMessageBox.question(self, "Guardar perfil", f"Ya existe el perfil «{name}». ¿Sustituirlo?")
            if r != QMessageBox.StandardButton.Yes:
                return
            self.profiles[existing[0]] = new
        else:
            self.profiles.append(new)
        save_profiles(profiles_path(), self.profiles)
        self.reload_profiles()
        self.profile_combo.setCurrentText(name)

    def delete_selected_profile(self):
        i = self.profile_combo.currentIndex()
        if not 0 <= i < len(self.profiles):
            return
        r = QMessageBox.question(self, "Eliminar perfil", f"¿Eliminar el perfil «{self.profiles[i].name}»?")
        if r != QMessageBox.StandardButton.Yes:
            return
        del self.profiles[i]
        save_profiles(profiles_path(), self.profiles)
        self.reload_profiles()

    # --- ajustes generales ------------------------------------------------------------
    def import_options(self) -> ImportOptions:
        return ImportOptions(join_tolerance=self.tolerance.value(), min_area=self.min_area.value())

    def _load_settings(self):
        d = ImportOptions()
        s = QSettings()
        self.tolerance.setValue(float(s.value("import/join_tolerance", d.join_tolerance)))
        self.min_area.setValue(float(s.value("import/min_area", d.min_area)))

    def _save_settings(self, *_):
        s = QSettings()
        s.setValue("import/join_tolerance", self.tolerance.value())
        s.setValue("import/min_area", self.min_area.value())
