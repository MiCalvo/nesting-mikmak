"""Vista previa PNG de una plancha (matplotlib). Solo para comprobar resultados
desde la línea de comandos; la interfaz tendrá su propia vista."""
from __future__ import annotations

from pathlib import Path

from ..engine.nester import Layout


def sheet_png(layout: Layout, sheet: int, path: str | Path, dpi: int = 110) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = layout.params
    W, H = p.sheet_width, p.sheet_height
    names = sorted({q.part for q in layout.placements})
    color = {n: f"C{i % 10}" for i, n in enumerate(names)}
    fig, ax = plt.subplots(figsize=(11, 11 * H / W + 0.6))
    ax.add_patch(plt.Rectangle((0, 0), W, H, fc="#f4f1ea", ec="k", lw=1.2))
    ax.add_patch(plt.Rectangle((p.margin, p.margin), W - 2 * p.margin, H - 2 * p.margin,
                               fill=False, ec="0.6", ls=":", lw=0.8))
    for q in layout.on_sheet(sheet):
        x, y = q.polygon.exterior.xy
        ax.fill(x, y, color=color[q.part], alpha=0.6)
        ax.plot(x, y, "k", lw=0.5)
        for r in q.polygon.interiors:
            x, y = r.xy
            ax.fill(x, y, color="#f4f1ea")
            ax.plot(x, y, "k", lw=0.3)
        c = q.polygon.representative_point()
        ax.text(c.x, c.y, q.part, ha="center", va="center", fontsize=6)
    st = layout.stats(sheet)
    ax.set_title(f"Plancha {sheet + 1}/{layout.sheets}: {W:.0f} × {H:.0f} mm · separación {p.separation} mm · "
                 f"margen {p.margin} mm · zona libre {st['free'][0]:.0f} × {st['free'][1]:.0f} mm · "
                 f"aprovechamiento {100 * st['utilization']:.1f} %", fontsize=9)
    ax.set_aspect("equal")
    ax.set_xlim(-10, W + 10)
    ax.set_ylim(-10, H + 10)
    ax.set_xlabel("mm")
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path
