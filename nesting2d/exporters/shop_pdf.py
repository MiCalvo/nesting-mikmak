"""PDF de taller (QPdfWriter de Qt: no añade dependencias; LGPL como PySide6).

Contenido (ver especificación, «Salidas»):
- Página de resumen: material, espesor, plancha, separación, margen, y la tabla
  de piezas con su número de posición, medidas, cantidad pedida y colocada por
  plancha. Avisos si hay piezas sin colocar o problemas de validación.
- Una página por plancha: dibujo a escala normalizada (1:5, 1:10…), cada pieza
  con su número de posición, el retal libre y una leyenda nº → pieza → cantidad.

Las piezas se numeran por POSICIÓN (una por tipo de pieza, como en un plano de
conjunto), no una por copia: así la leyenda es corta y cada copia de la misma
pieza lleva el mismo número.
"""
from __future__ import annotations

import datetime as _dt
from collections import Counter
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import polylabel

from ..engine.nester import Layout, free_rect
from ..geometry import Part

PAGE_W, PAGE_H = 297.0, 210.0       # A4 apaisado, mm
MARGIN = 12.0
DPI = 600
STANDARD_SCALES = [1, 2, 5, 10, 20, 25, 50, 100, 200]


def _ensure_qt_app():
    """QPdfWriter necesita una aplicación de Qt (para las fuentes)."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    if QCoreApplication.instance() is None:
        _ensure_qt_app.app = QGuiApplication([])   # se guarda para que no se destruya
    from PySide6.QtGui import QFontDatabase
    if not QFontDatabase.families():
        # visto en Windows con QT_QPA_PLATFORM=offscreen: el PDF saldría sin ningún texto
        raise RuntimeError("Qt no encuentra ninguna fuente (¿plataforma 'offscreen' en Windows?); "
                           "el PDF de taller saldría sin texto.")


def choose_scale(w: float, h: float, avail_w: float, avail_h: float) -> int:
    """Menor denominador normalizado con el que w × h mm cabe en el hueco disponible."""
    for d in STANDARD_SCALES:
        if w / d <= avail_w and h / d <= avail_h:
            return d
    return STANDARD_SCALES[-1]


def _num(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def positions(layout: Layout, parts: list[Part]) -> dict[str, int]:
    """Número de posición de cada pieza: el orden de la lista de piezas del proyecto
    (las que no estén en la lista, detrás, por nombre)."""
    names = [p.name for p in parts if any(q.part == p.name for q in layout.placements)]
    extra = sorted({q.part for q in layout.placements} - set(names))
    return {n: i + 1 for i, n in enumerate(names + extra)}


def export_shop_pdf(layout: Layout, parts: list[Part], path: str | Path, title: str = "",
                    issues_count: int = 0, rotation_warnings: int = 0) -> Path:
    _ensure_qt_app()
    from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
    from PySide6.QtGui import (QBrush, QColor, QFont, QPageLayout, QPageSize, QPainter,
                               QPainterPath, QPdfWriter, QPen)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    p = layout.params
    W, H, m = p.sheet_width, p.sheet_height, p.margin
    pos = positions(layout, parts)
    by_name = {q.name: q for q in parts}

    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setResolution(DPI)
    writer.setTitle(title or "Hoja de taller")
    writer.setCreator("Nesting 2D")
    k = DPI / 25.4                       # píxeles de dispositivo por mm de papel
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    def font(size_mm: float, bold: bool = False) -> QFont:
        f = QFont("Arial")
        f.setPixelSize(max(1, int(size_mm * k)))
        f.setBold(bold)
        return f

    def pen(width_mm: float, color="#000000", style=Qt.PenStyle.SolidLine) -> QPen:
        return QPen(QColor(color), width_mm * k, style)

    def text(x, y, s, size=3.0, bold=False, color="#000000", align=Qt.AlignmentFlag.AlignLeft, width=150.0):
        """Texto con la parte superior izquierda en (x, y) mm de papel."""
        painter.setFont(font(size, bold))
        painter.setPen(QColor(color))
        painter.drawText(QRectF(x * k, y * k, width * k, size * 1.6 * k),
                         int(align | Qt.AlignmentFlag.AlignVCenter), s)

    def table(x, y, cols, rows, size=2.8):
        """cols = [(título, ancho mm, alineación)], rows = [[texto…]]. Devuelve la y final."""
        h = size * 1.7
        painter.setPen(pen(0.2))
        cx = x
        for title_, wcol, al in cols:
            painter.fillRect(QRectF(cx * k, y * k, wcol * k, h * k), QColor("#e8e8e8"))
            text(cx + 1, y + 0.1, title_, size, True, align=al, width=wcol - 2)
            cx += wcol
        y += h
        for r in rows:
            cx = x
            for (title_, wcol, al), val in zip(cols, r):
                text(cx + 1, y + 0.1, str(val), size, align=al, width=wcol - 2)
                cx += wcol
            y += h
            painter.setPen(pen(0.1, "#b0b0b0"))
            painter.drawLine(QPointF(x * k, y * k), QPointF(cx * k, y * k))
        return y

    def header(subtitle: str, page_no: int, pages: int):
        text(MARGIN, MARGIN - 4, title or "Hoja de taller", 5, True, width=200)
        text(MARGIN, MARGIN + 3, subtitle, 3.5, width=200)
        text(PAGE_W - MARGIN - 80, MARGIN - 4, _dt.date.today().strftime("%d/%m/%Y"), 3,
             align=Qt.AlignmentFlag.AlignRight, width=80)
        text(PAGE_W - MARGIN - 80, PAGE_H - MARGIN + 2, f"Página {page_no} de {pages}", 2.8,
             align=Qt.AlignmentFlag.AlignRight, width=80)
        painter.setPen(pen(0.3))
        painter.drawLine(QPointF(MARGIN * k, (MARGIN + 9) * k), QPointF((PAGE_W - MARGIN) * k, (MARGIN + 9) * k))

    pages = 1 + layout.sheets
    AL, AR = Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight

    # --- página 1: resumen ---------------------------------------------------------
    header("Resumen", 1, pages)
    y = MARGIN + 13
    info = [
        ("Material", p.material or "—"), ("Espesor", p.thickness or "—"),
        ("Plancha", f"{_num(W, 0)} × {_num(H, 0)} mm"), ("Planchas", str(layout.sheets)),
        ("Separación entre piezas", f"{_num(p.separation, 2)} mm"), ("Margen al borde", f"{_num(m, 2)} mm"),
        ("Piezas colocadas", str(len(layout.placements))),
    ]
    if layout.fill is not None:     # modo rellenar
        from ..engine.fill import describe_fill
        info.append(("Rellenar plancha", "caben al menos " + describe_fill(layout.fill)))
    for label, val in info:
        text(MARGIN, y, f"{label}:", 3, True, width=50)
        text(MARGIN + 50, y, val, 3, width=120)
        y += 5
    y += 3
    placed = Counter(q.part for q in layout.placements)
    sheet_cols = [(f"Pl. {s + 1}", 14.0, AR) for s in range(min(layout.sheets, 8))]
    cols = [("Nº", 10.0, AR), ("Pieza", 70.0, AL), ("Medidas (mm)", 32.0, AR),
            ("Proporción" if layout.fill is not None else "Pedidas", 18.0, AR),
            ("Colocadas", 20.0, AR)] + sheet_cols
    if layout.sheets > 8:
        cols.append(("Resto pl.", 18.0, AR))
    rows = []
    for name, n in sorted(pos.items(), key=lambda kv: kv[1]):
        part = by_name.get(name)
        if part is not None:
            w_, h_ = part.size
            dims, ordered = f"{_num(w_)} × {_num(h_)}", str(part.quantity)
        else:
            dims, ordered = "—", "—"
        per = Counter(q.sheet for q in layout.placements if q.part == name)
        r = [n, name, dims, ordered, placed[name]] + [per.get(s, "") for s in range(min(layout.sheets, 8))]
        if layout.sheets > 8:
            r.append(sum(v for s, v in per.items() if s >= 8) or "")
        rows.append(r)
    y = table(MARGIN, y, cols, rows)
    y += 5
    warn = []
    if layout.unplaced:
        warn.append("SIN COLOCAR: " + ", ".join(f"{n} × {k_}" for k_, n in sorted(layout.unplaced.items())))
    if issues_count:
        warn.append(f"ATENCIÓN: {issues_count} problemas de validación (solape, separación o margen).")
    if rotation_warnings:
        warn.append(f"ATENCIÓN: {rotation_warnings} pieza(s) con giro fuera de sus rotaciones permitidas.")
    for wtxt in warn:
        text(MARGIN, y, wtxt, 3.2, True, "#b00000", width=PAGE_W - 2 * MARGIN)
        y += 5.5

    # --- una página por plancha ------------------------------------------------------
    legend_w = 62.0
    area_x, area_y = MARGIN, MARGIN + 22
    area_w = PAGE_W - 2 * MARGIN - legend_w - 6
    area_h = PAGE_H - area_y - MARGIN - 4
    d = choose_scale(W, H, area_w, area_h)
    s_ = 1.0 / d

    for s in range(layout.sheets):
        writer.newPage()
        st = layout.stats(s)
        fw, fh = st["free"]
        header(f"Plancha {s + 1} de {layout.sheets}", s + 2, pages)
        text(MARGIN, MARGIN + 12, f"Escala 1:{d}   ·   {len(layout.on_sheet(s))} piezas   ·   "
             f"aprovechamiento {_num(100 * st['utilization'])} %   ·   retal libre {_num(fw, 0)} × {_num(fh, 0)} mm   ·   "
             f"largo ocupado {_num(st['used_length'])} mm", 3, width=PAGE_W - 2 * MARGIN)

        ox = area_x + (area_w - W * s_) / 2
        oy = area_y + (area_h - H * s_) / 2

        def to_paper(x, y_):
            return QPointF((ox + x * s_) * k, (oy + (H - y_) * s_) * k)

        def path_of(poly: Polygon) -> QPainterPath:
            pth = QPainterPath()
            pth.setFillRule(Qt.FillRule.OddEvenFill)
            for ring in [poly.exterior, *poly.interiors]:
                pts = list(ring.coords)
                pth.moveTo(to_paper(*pts[0]))
                for pt in pts[1:]:
                    pth.lineTo(to_paper(*pt))
                pth.closeSubpath()
            return pth

        # plancha, margen y retal libre
        painter.setPen(pen(0.35))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(to_paper(0, H), to_paper(W, 0)))
        if m > 0:
            painter.setPen(pen(0.15, "#808080", Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(to_paper(m, H - m), to_paper(W - m, m)))
        fr = free_rect(layout, s)
        if fr:
            x0, y0, x1, y1 = fr
            painter.setPen(pen(0.15, "#2a7a3a", Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor("#2a7a3a"), Qt.BrushStyle.BDiagPattern))
            r = QRectF(to_paper(x0, y1), to_paper(x1, y0))
            painter.drawRect(r)
            # rótulo en dos líneas, solo si cabe dentro del retal
            bw, bh = min(40.0, r.width() / k - 2), 9.0
            if bw >= 16 and r.height() / k >= bh + 2:
                box_ = QRectF(r.center().x() - bw / 2 * k, r.center().y() - bh / 2 * k, bw * k, bh * k)
                painter.fillRect(box_, QColor("white"))
                painter.setFont(font(2.6, True))
                painter.setPen(QColor("#2a6a3a"))
                painter.drawText(box_, int(Qt.AlignmentFlag.AlignCenter),
                                 f"Retal libre\n{_num(x1 - x0, 0)} × {_num(y1 - y0, 0)} mm")

        # piezas
        painter.setPen(pen(0.2))
        painter.setBrush(QColor("#dcdcdc"))
        on_sheet = layout.on_sheet(s)
        for q in on_sheet:
            painter.drawPath(path_of(q.polygon))
        painter.setFont(font(2.6, True))
        painter.setPen(QColor("#000000"))
        for q in on_sheet:
            c = polylabel(Polygon(q.polygon.exterior), 0.5)
            pt = to_paper(c.x, c.y)
            label = str(pos[q.part])
            r = QRectF(pt.x() - 4 * k, pt.y() - 2 * k, 8 * k, 4 * k)
            painter.fillRect(r, QColor(255, 255, 255, 200))
            painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter), label)

        # cotas de la plancha
        painter.setPen(pen(0.15))
        text(ox, oy + H * s_ + 1, f"{_num(W, 0)} mm", 2.6, align=Qt.AlignmentFlag.AlignHCenter, width=W * s_)
        painter.save()
        painter.translate((ox - 1.5) * k, (oy + H * s_) * k)
        painter.rotate(-90)
        painter.setFont(font(2.6))
        painter.drawText(QRectF(0, -4 * k, H * s_ * k, 4 * k), int(Qt.AlignmentFlag.AlignCenter), f"{_num(H, 0)} mm")
        painter.restore()

        # leyenda
        counts = Counter(q.part for q in on_sheet)
        rows = [[pos[n], n, c] for n, c in sorted(counts.items(), key=lambda kv: pos[kv[0]])]
        lx = PAGE_W - MARGIN - legend_w
        table(lx, area_y, [("Nº", 9.0, AR), ("Pieza", 40.0, AL), ("Cant.", 13.0, AR)], rows, size=2.6)

    painter.end()
    return path
