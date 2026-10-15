"""Barra lateral con los pasos del trabajo: 1 Piezas · 2 Material · 3 Resultado · 4 Exportar.

Cada paso muestra su número (o una marca si está completo), un título y una
línea de estado («5 piezas · 16 copias», «Sin calcular»…). Los pasos no
obligan a un orden: se puede ir a cualquiera, pero el estado dice qué falta.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy

from . import style

# estado de un paso -> color del círculo
STATE_COLORS = {"todo": "#3a475c", "done": "#2ea043", "warn": "#d29922", "bad": "#f85149"}


class StepButton(QAbstractButton):
    def __init__(self, number: int, title: str, parent=None):
        super().__init__(parent)
        self.number = number
        self.title = title
        self.subtitle = ""
        self.state = "todo"
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"Paso {number}: {title}")

    def set_status(self, subtitle: str, state: str = "todo") -> None:
        if (subtitle, state) != (self.subtitle, self.state):
            self.subtitle, self.state = subtitle, state
            self.setToolTip(f"{self.title}: {subtitle}" if subtitle else self.title)
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(220, 56)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 2, -8, -2)
        active = self.isChecked()
        if active or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(style.SIDEBAR_ACTIVE if active else "#1f2a3b"))
            p.drawRoundedRect(r, 8, 8)
        if active:
            p.setBrush(QColor("#58a6ff"))
            p.drawRoundedRect(QRectF(r.left(), r.top() + 10, 3, r.height() - 20), 1.5, 1.5)

        # círculo con el número o la marca
        d = 26
        c = QRectF(r.left() + 14, r.center().y() - d / 2, d, d)
        color = QColor(STATE_COLORS.get(self.state, STATE_COLORS["todo"]))
        if active and self.state == "todo":
            color = QColor(style.ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(c)
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        if self.state == "done":
            pen = QPen(QColor("white"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            o = c.topLeft()
            p.drawPolyline([o + QPointF(8, 13.5), o + QPointF(11.5, 17), o + QPointF(18, 9.5)])
        elif self.state in ("warn", "bad"):
            p.drawText(c, Qt.AlignmentFlag.AlignCenter, "!")
        else:
            p.drawText(c, Qt.AlignmentFlag.AlignCenter, str(self.number))

        # textos
        tx = c.right() + 12
        tw = r.right() - tx - 6
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white" if active else style.SIDEBAR_TEXT))
        fm = p.fontMetrics()
        top = r.center().y() - fm.height() + 1
        p.drawText(QRectF(tx, top, tw, fm.height()), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(tw)))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        sub_color = {"warn": "#e3b341", "bad": "#ff7b72"}.get(self.state, style.SIDEBAR_MUTED)
        p.setPen(QColor(sub_color))
        fm = p.fontMetrics()
        p.drawText(QRectF(tx, r.center().y() + 2, tw, fm.height()), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(tw)))
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)
