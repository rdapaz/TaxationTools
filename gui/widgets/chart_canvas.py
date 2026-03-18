"""
Matplotlib canvas widget for embedding charts in PySide6.
"""

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class ChartCanvas(FigureCanvasQTAgg):
    """A matplotlib figure embedded in a Qt widget."""

    def __init__(self, width=5, height=4, dpi=100, parent=None):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor="white")
        self.fig.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.12)
        super().__init__(self.fig)
        self.setMinimumHeight(280)

    def clear(self):
        self.fig.clear()
        self.draw()
