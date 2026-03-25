#!/usr/bin/env python3
"""
Becoming -- Atmospheric PySide6 Interface.

A shapeless, living, instrument-like interface for generative sound,
drift state, and poem emergence.
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient,
    QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget, QComboBox, QLineEdit,
    QCheckBox, QSizePolicy, QGraphicsOpacityEffect, QDialog,
    QFormLayout, QGroupBox,
)

try:
    import mido
    HAS_MIDI = True
except ImportError:
    HAS_MIDI = False

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.engine.library import SoundLibrary
from src.engine.states import STATE_NAMES

# -- Color Palette (light theme: white bg, black/gray accents) ----
BG_DEEP = "#ffffff"
BG_PANEL = "#f5f5f5"
BG_SURFACE = "#e8e8e8"
FG_PRIMARY = "#1a1a1a"
FG_DIM = "#666666"
FG_WHISPER = "#999999"
ACCENT_CYAN = "#404040"
ACCENT_VIOLET = "#555555"
ACCENT_AMBER = "#4a4a4a"
ACCENT_RED = "#333333"
ACCENT_GOLD = "#505050"
POEM_FG = "#2a2a2a"
POEM_FG_DIM = "#888888"

STATE_COLORS = {
    "submerged": "#c8c8c8",
    "tense": "#b0b0b0",
    "dissolved": "#c0c0c8",
    "rupture": "#a8a8a8",
    "drifting": "#bbb8c0",
}

# -- Global Stylesheet --
GLOBAL_SS = f"""
QMainWindow, QWidget {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    font-family: 'Avenir Next', 'Helvetica Neue', sans-serif;
    font-size: 13px;
}}
QLabel {{
    background: transparent;
    border: none;
}}
QSlider::groove:horizontal {{
    background: {BG_SURFACE};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {FG_PRIMARY};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, x2:1, stop:0 {FG_PRIMARY}, stop:1 {FG_DIM});
    border-radius: 3px;
}}
QSpinBox {{
    background: {BG_SURFACE};
    border: 1px solid {FG_WHISPER};
    border-radius: 4px;
    padding: 2px 6px;
    color: {FG_PRIMARY};
}}
QComboBox {{
    background: {BG_SURFACE};
    border: 1px solid {FG_WHISPER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {FG_PRIMARY};
}}
QComboBox::drop-down {{ border: none; }}
QLineEdit {{
    background: {BG_SURFACE};
    border: 1px solid {FG_WHISPER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {FG_PRIMARY};
}}
QCheckBox {{ color: {FG_DIM}; spacing: 6px; }}
QTextEdit {{
    background: {BG_DEEP};
    border: none;
    color: {FG_DIM};
    font-family: 'Menlo', 'Courier New', monospace;
    font-size: 11px;
}}
QScrollBar:vertical {{
    background: {BG_DEEP};
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {FG_WHISPER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


class PillButton(QPushButton):
    """Capsule-shaped button with glow hover."""

    def __init__(self, text: str, color: str = ACCENT_CYAN, parent=None):
        super().__init__(text, parent)
        self._color = color
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color}22;
                color: {color};
                border: 1px solid {color}44;
                border-radius: 15px;
                padding: 4px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {color}44;
                border-color: {color}88;
            }}
            QPushButton:pressed {{
                background-color: {color}66;
            }}
        """)


# ================================================================
# Influence Panel (left sidebar)
# ================================================================

class _SemanticSlider(QWidget):
    """Labeled slider with poetic name and value readout."""
    valueChanged = Signal(float)

    def __init__(self, label: str, lo: float, hi: float, default: float,
                 decimals: int = 2, parent=None):
        super().__init__(parent)
        self._lo, self._hi, self._dec = lo, hi, decimals
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(2)

        top = QHBoxLayout()
        self._name_lbl = QLabel(label)
        self._name_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
        self._val_lbl = QLabel(f"{default:.{decimals}f}")
        self._val_lbl.setStyleSheet(f"color: {FG_PRIMARY}; font-size: 11px;")
        self._val_lbl.setAlignment(Qt.AlignRight)
        top.addWidget(self._name_lbl)
        top.addWidget(self._val_lbl)
        lay.addLayout(top)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(self._to_slider(default))
        self._slider.valueChanged.connect(self._on_change)
        lay.addWidget(self._slider)

    def _to_slider(self, v: float) -> int:
        return int((v - self._lo) / (self._hi - self._lo) * 1000)

    def _from_slider(self, v: int) -> float:
        return self._lo + (v / 1000.0) * (self._hi - self._lo)

    def _on_change(self, v: int):
        val = self._from_slider(v)
        self._val_lbl.setText(f"{val:.{self._dec}f}")
        self.valueChanged.emit(val)

    def value(self) -> float:
        return self._from_slider(self._slider.value())

    def setValue(self, v: float):
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(v))
        self._val_lbl.setText(f"{v:.{self._dec}f}")
        self._slider.blockSignals(False)


class InfluencePanel(QWidget):
    """Left sidebar: state tokens, semantic sliders, intervention pills."""

    # Signals that the main window connects to
    sliderChanged = Signal(str, float)   # (cmd, value)
    interventionClicked = Signal(str)    # engine command string
    engineStartRequested = Signal()
    engineStopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setStyleSheet(f"background-color: {BG_PANEL};")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(6)

        # -- Title --
        title = QLabel("becoming")
        title.setStyleSheet(f"color: {FG_PRIMARY}; font-size: 20px; font-weight: 300; letter-spacing: 5px;")
        lay.addWidget(title)
        lay.addSpacing(14)

        # -- State tokens --
        state_lbl = QLabel("lean into")
        state_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(state_lbl)

        self._state_btns: dict[str, QPushButton] = {}
        state_grid = QVBoxLayout()
        state_grid.setSpacing(8)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        for i, name in enumerate(STATE_NAMES):
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            color = STATE_COLORS.get(name, BG_SURFACE)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}88;
                    color: {FG_PRIMARY};
                    border: 1px solid {color};
                    border-radius: 14px;
                    padding: 2px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background-color: {color}cc; }}
            """)
            btn.clicked.connect(lambda checked=False, n=name: self.interventionClicked.emit(f"s {n}"))
            if i < 2:
                row1.addWidget(btn, stretch=1)
            else:
                row2.addWidget(btn, stretch=1)
            self._state_btns[name] = btn
        state_grid.addLayout(row1)
        state_grid.addLayout(row2)
        lay.addLayout(state_grid)
        lay.addSpacing(18)

        # -- Semantic sliders --
        slider_lbl = QLabel("influence")
        slider_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(slider_lbl)
        lay.addSpacing(4)

        self.strain_slider = _SemanticSlider("strain", 0.0, 1.0, 0.3)
        self.strain_slider.valueChanged.connect(lambda v: self.sliderChanged.emit("t", v))
        lay.addWidget(self.strain_slider)

        self.saturation_slider = _SemanticSlider("saturation", 0.0, 1.0, 0.5)
        self.saturation_slider.valueChanged.connect(lambda v: self.sliderChanged.emit("d", v))
        lay.addWidget(self.saturation_slider)

        self.heat_slider = _SemanticSlider("heat", 0.0, 1.0, 0.5)
        self.heat_slider.valueChanged.connect(lambda v: self.sliderChanged.emit("T", v))
        lay.addWidget(self.heat_slider)

        self.timescale_slider = _SemanticSlider("time scale", 0.1, 3.0, 1.0, decimals=1)
        self.timescale_slider.valueChanged.connect(lambda v: self.sliderChanged.emit("dur", v))
        lay.addWidget(self.timescale_slider)

        lay.addSpacing(20)

        # -- Intervention pills --
        int_lbl = QLabel("interventions")
        int_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(int_lbl)
        lay.addSpacing(4)

        interventions = [
            ("introduce rupture", "m", ACCENT_RED),
            ("invite silence", "!", ACCENT_VIOLET),
            ("enter drift", "p drift", ACCENT_VIOLET),
            ("force collapse", "p collapse", ACCENT_AMBER),
            ("stabilize", "p stabilize", ACCENT_CYAN),
        ]
        for label, cmd, color in interventions:
            btn = PillButton(label, color)
            btn.clicked.connect(lambda checked=False, c=cmd: self.interventionClicked.emit(c))
            lay.addWidget(btn)
            lay.addSpacing(2)

        lay.addSpacing(20)

        # -- Engine controls --
        eng_lbl = QLabel("engine")
        eng_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(eng_lbl)
        lay.addSpacing(4)

        self.start_btn = PillButton("awaken", ACCENT_CYAN)
        self.start_btn.clicked.connect(self.engineStartRequested.emit)
        lay.addWidget(self.start_btn)

        self.stop_btn = PillButton("silence", ACCENT_RED)
        self.stop_btn.clicked.connect(self.engineStopRequested.emit)
        lay.addWidget(self.stop_btn)
        lay.addSpacing(6)

        # -- Initial state selector --
        init_row = QHBoxLayout()
        init_lbl = QLabel("initial state")
        init_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        init_row.addWidget(init_lbl)
        self.init_state_combo = QComboBox()
        self.init_state_combo.addItems(STATE_NAMES)
        self.init_state_combo.setCurrentText("submerged")
        self.init_state_combo.setFixedWidth(120)
        init_row.addWidget(self.init_state_combo)
        lay.addLayout(init_row)

        lay.addStretch()

        # -- Poem controls --
        poem_lbl = QLabel("poem")
        poem_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(poem_lbl)
        lay.addSpacing(4)

        poem_row = QHBoxLayout()
        self.poem_toggle_btn = PillButton("begin poem", ACCENT_GOLD)
        poem_row.addWidget(self.poem_toggle_btn)

        int_lbl2 = QLabel("interval")
        int_lbl2.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        poem_row.addWidget(int_lbl2)
        self.poem_interval_spin = QSpinBox()
        self.poem_interval_spin.setRange(5, 60)
        self.poem_interval_spin.setValue(15)
        self.poem_interval_spin.setSuffix("s")
        self.poem_interval_spin.setFixedWidth(60)
        poem_row.addWidget(self.poem_interval_spin)
        lay.addLayout(poem_row)

        # -- Tools buttons --
        lay.addSpacing(12)
        tools_lbl = QLabel("tools")
        tools_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 2px;")
        lay.addWidget(tools_lbl)
        lay.addSpacing(4)

        self.harvest_btn = PillButton("harvest", ACCENT_CYAN)
        lay.addWidget(self.harvest_btn)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        self.rebalance_btn = PillButton("rebalance", ACCENT_VIOLET)
        tools_row.addWidget(self.rebalance_btn)
        self.break_bal_btn = PillButton("break balance", ACCENT_AMBER)
        tools_row.addWidget(self.break_bal_btn)
        lay.addLayout(tools_row)

        tools_row2 = QHBoxLayout()
        tools_row2.setSpacing(6)
        self.autotag_btn = PillButton("auto tag", FG_DIM)
        tools_row2.addWidget(self.autotag_btn)
        self.library_btn = PillButton("library", FG_DIM)
        tools_row2.addWidget(self.library_btn)
        lay.addLayout(tools_row2)


# ================================================================
# Drift Field (center visualization)
# ================================================================

class _Particle:
    """A single orb in the drift field."""
    __slots__ = ("x", "y", "vx", "vy", "radius", "color", "alpha", "life", "max_life")

    def __init__(self, x: float, y: float, color: str, radius: float = 4.0):
        self.x = x
        self.y = y
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(-0.3, 0.3)
        self.radius = radius
        self.color = color
        self.alpha = 0.0  # fade in
        self.life = 0.0
        self.max_life = random.uniform(8.0, 20.0)


class DriftFieldWidget(QWidget):
    """Animated particle/constellation canvas showing active drift state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._particles: list[_Particle] = []
        self._phase_text = ""
        self._focus_text = ""
        self._desires: dict[str, float] = {}
        self._fatigue: dict[str, float] = {}
        self._tension = 0.3
        self._density = 0.5
        self._temperature = 0.5
        self._phase_remaining = 0.0
        self._dur_scale = 1.0

        self._breath_phase = 0.0  # slow oscillation
        self._tick = 0
        self._poem_lines: list[tuple[str, str]] = []  # (timestamp, text)
        self._max_poem_lines = 200

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_field)
        self._timer.start(33)  # ~30fps

    def add_poem_line(self, timestamp: str, text: str):
        """Add a poem line to the drift field overlay."""
        self._poem_lines.append((timestamp, text))
        if len(self._poem_lines) > self._max_poem_lines:
            self._poem_lines = self._poem_lines[-self._max_poem_lines:]

    def update_snapshot(self, snap: dict):
        """Called when a [drift-snapshot] arrives from engine."""
        self._phase_text = snap.get("phase", "")
        self._focus_text = snap.get("focus", "") or ""
        self._desires = snap.get("desires", {})
        self._fatigue = snap.get("fatigue", {})
        self._phase_remaining = snap.get("phase_remaining", 0)
        self._dur_scale = snap.get("duration_scale", 1.0)

    def set_params(self, tension: float, density: float, temperature: float):
        self._tension = tension
        self._density = density
        self._temperature = temperature

    def _update_field(self):
        self._tick += 1
        self._breath_phase += 0.02

        # Spawn particles based on density
        target_count = int(10 + self._density * 40)
        while len(self._particles) < target_count:
            w, h = self.width(), self.height()
            cx, cy = w / 2, h / 2
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0, min(w, h) * 0.35)
            x = cx + math.cos(angle) * dist
            y = cy + math.sin(angle) * dist
            color = random.choice(["#1a1a1a", "#404040", "#606060", "#808080"])
            r = random.uniform(2.0, 5.0 + self._tension * 4)
            self._particles.append(_Particle(x, y, color, r))

        # Update particles
        dt = 0.033
        for p in self._particles:
            p.life += dt
            # Fade in / out
            if p.life < 1.0:
                p.alpha = min(1.0, p.life)
            elif p.life > p.max_life - 2.0:
                p.alpha = max(0.0, (p.max_life - p.life) / 2.0)
            else:
                p.alpha = 0.7 + 0.3 * math.sin(p.life * 0.5)

            # Motion — tension increases speed, temperature adds jitter
            speed = 0.2 + self._tension * 1.5
            jitter = self._temperature * 0.4
            p.vx += random.uniform(-jitter, jitter) * dt
            p.vy += random.uniform(-jitter, jitter) * dt
            # Gentle pull toward center
            cx, cy = self.width() / 2, self.height() / 2
            dx, dy = cx - p.x, cy - p.y
            dist = math.sqrt(dx * dx + dy * dy) + 1
            p.vx += dx / dist * 0.02
            p.vy += dy / dist * 0.02
            # Damping
            p.vx *= 0.98
            p.vy *= 0.98
            p.x += p.vx * speed
            p.y += p.vy * speed

        # Remove dead particles
        self._particles = [p for p in self._particles if p.life < p.max_life]

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background gradient (light)
        grad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.6)
        grad.setColorAt(0, QColor("#fafafa"))
        grad.setColorAt(1, QColor("#eeeeee"))
        painter.fillRect(0, 0, w, h, grad)

        # Draw particles
        for p in self._particles:
            c = QColor(p.color)
            c.setAlphaF(p.alpha * 0.8)
            painter.setPen(Qt.NoPen)

            # Glow
            glow = QRadialGradient(p.x, p.y, p.radius * 3)
            gc = QColor(p.color)
            gc.setAlphaF(p.alpha * 0.15)
            glow.setColorAt(0, gc)
            gc2 = QColor(p.color)
            gc2.setAlphaF(0)
            glow.setColorAt(1, gc2)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(p.x, p.y), p.radius * 3, p.radius * 3)

            # Core
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(p.x, p.y), p.radius, p.radius)

        # Phase text (floating, center-top)
        if self._phase_text:
            breath = 0.5 + 0.5 * math.sin(self._breath_phase)
            font = QFont("Avenir Next", 14)
            font.setWeight(QFont.Light)
            painter.setFont(font)
            c = QColor(FG_DIM)
            c.setAlphaF(0.3 + 0.2 * breath)
            painter.setPen(c)
            phase_str = self._phase_text
            if self._focus_text:
                phase_str += f"  :  {self._focus_text}"
            painter.drawText(QRectF(0, 20, w, 30), Qt.AlignHCenter, phase_str)

        # Desire bars (bottom area, subtle)
        if self._desires:
            bar_y = h - 80
            bar_h = 4
            names = sorted(self._desires, key=lambda n: -self._desires[n])
            for i, name in enumerate(names[:6]):
                d = self._desires[name]
                f = self._fatigue.get(name, 0)
                bar_w = min(d / 5.0, 1.0) * (w * 0.5)
                x0 = (w - w * 0.5) / 2
                y0 = bar_y + i * 12

                # Desire bar
                c = QColor("#404040")
                c.setAlphaF(0.25)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawRoundedRect(QRectF(x0, y0, bar_w, bar_h), 2, 2)

                # Label
                font = QFont("Avenir Next", 9)
                painter.setFont(font)
                lc = QColor(FG_WHISPER)
                lc.setAlphaF(0.6)
                painter.setPen(lc)
                painter.drawText(QRectF(x0 - 100, y0 - 3, 95, 12), Qt.AlignRight, name)

                # Focus marker
                if name == self._focus_text:
                    gc = QColor("#1a1a1a")
                    gc.setAlphaF(0.6)
                    painter.setPen(gc)
                    painter.drawText(QRectF(x0 + bar_w + 4, y0 - 3, 20, 12), Qt.AlignLeft, "*")

        # Duration scale indicator
        if self._dur_scale != 1.0:
            font = QFont("Avenir Next", 10)
            painter.setFont(font)
            c = QColor(FG_WHISPER)
            c.setAlphaF(0.4)
            painter.setPen(c)
            painter.drawText(QRectF(w - 80, 20, 70, 20), Qt.AlignRight, f"{self._dur_scale:.1f}x")

        # -- Poem overlay (right side) --
        if self._poem_lines:
            poem_x = w * 0.35
            poem_w = w * 0.60
            poem_font = QFont("Georgia", 13)
            poem_font.setItalic(True)
            painter.setFont(poem_font)
            fm = QFontMetrics(poem_font)

            # Calculate wrapped height per line (bottom-up layout)
            entries = []
            for ts, text in self._poem_lines:
                br = fm.boundingRect(QRectF(0, 0, poem_w, 1000).toRect(),
                                     Qt.AlignLeft | Qt.TextWordWrap, text)
                entries.append((ts, text, br.height() + 8))

            # Walk backwards from bottom, fitting as many as possible
            total_h = 0
            visible = []
            for entry in reversed(entries):
                if total_h + entry[2] > h - 60:
                    break
                visible.insert(0, entry)
                total_h += entry[2]

            y_pos = h - 30 - total_h
            for idx, (ts, text, eh) in enumerate(visible):
                age = len(visible) - 1 - idx  # 0 = newest
                if age == 0:
                    alpha = 0.85
                elif age < 3:
                    alpha = 0.55
                elif age < 6:
                    alpha = 0.30
                elif age < 12:
                    alpha = 0.15
                else:
                    alpha = 0.07
                c = QColor(POEM_FG)
                c.setAlphaF(alpha)
                painter.setPen(c)
                painter.setFont(poem_font)
                painter.drawText(QRectF(poem_x, y_pos, poem_w, eh), Qt.AlignLeft | Qt.TextWordWrap, text)
                # Tiny timestamp
                ts_font = QFont("Avenir Next", 8)
                painter.setFont(ts_font)
                tc = QColor(FG_WHISPER)
                tc.setAlphaF(alpha * 0.4)
                painter.setPen(tc)
                painter.drawText(QRectF(poem_x - 40, y_pos + 2, 36, 16), Qt.AlignRight, ts)
                y_pos += eh

        painter.end()


# ================================================================
# Poem Field (right panel)
# ================================================================

class PoemWidget(QWidget):
    """Living text emergence with fading lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._lines: list[tuple[str, str, float]] = []  # (timestamp, text, birth_time)
        self._max_lines = 200
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(0)

        hdr = QLabel("poem")
        hdr.setStyleSheet(f"color: {FG_WHISPER}; font-size: 10px; letter-spacing: 2px;")
        lay.addWidget(hdr)
        lay.addSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_lay = QVBoxLayout(self._container)
        self._container_lay.setContentsMargins(0, 0, 0, 0)
        self._container_lay.setSpacing(6)
        self._container_lay.addStretch()

        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll)

    def add_line(self, timestamp: str, text: str):
        """Add a new poem line with fade-in."""
        birth = time.time()
        self._lines.append((timestamp, text, birth))
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines:]

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"""
            color: {POEM_FG};
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 14px;
            font-style: italic;
            background: transparent;
            padding: 2px 0;
        """)

        ts_lbl = QLabel(timestamp)
        ts_lbl.setStyleSheet(f"color: {POEM_FG_DIM}; font-size: 9px; background: transparent;")

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_lay = QVBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(1)
        row_lay.addWidget(ts_lbl)
        row_lay.addWidget(lbl)

        # Insert before the stretch
        count = self._container_lay.count()
        self._container_lay.insertWidget(count - 1, row)

        # Fade older lines
        self._fade_old_lines()

        # Auto-scroll
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def _fade_old_lines(self):
        """Reduce opacity of older lines."""
        count = self._container_lay.count() - 1  # minus stretch
        for i in range(count):
            widget = self._container_lay.itemAt(i).widget()
            if widget is None:
                continue
            age = count - 1 - i  # 0 = newest
            if age == 0:
                opacity = 1.0
            elif age < 4:
                opacity = 0.7
            elif age < 8:
                opacity = 0.45
            elif age < 15:
                opacity = 0.25
            else:
                opacity = 0.12
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(opacity)
            widget.setGraphicsEffect(effect)


# ================================================================
# Whisper Bar + Debug Log (bottom)
# ================================================================

class WhisperBar(QWidget):
    """Bottom status bar with collapsible debug log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._expanded = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 8)
        lay.setSpacing(4)

        # Whisper row
        row = QHBoxLayout()
        self._status_lbl = QLabel("idle")
        self._status_lbl.setStyleSheet(f"color: {FG_WHISPER}; font-size: 11px;")
        row.addWidget(self._status_lbl)

        row.addStretch()

        self._toggle_btn = QPushButton("trace")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                color: {FG_WHISPER};
                background: transparent;
                border: none;
                font-size: 10px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ color: {FG_DIM}; }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_debug)
        row.addWidget(self._toggle_btn)
        lay.addLayout(row)

        # Debug log (hidden by default)
        self._debug_log = QTextEdit()
        self._debug_log.setReadOnly(True)
        self._debug_log.setMaximumHeight(200)
        self._debug_log.setVisible(False)
        self._debug_log.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_DEEP};
                color: {FG_WHISPER};
                font-family: 'Menlo', 'Courier New', monospace;
                font-size: 10px;
                border: 1px solid {BG_SURFACE};
                border-radius: 4px;
            }}
        """)
        lay.addWidget(self._debug_log)

    def set_status(self, text: str):
        self._status_lbl.setText(text)

    def append_log(self, source: str, line: str):
        self._debug_log.append(f"[{source}] {line}")
        # Trim to ~500 lines
        doc = self._debug_log.document()
        if doc.blockCount() > 500:
            cursor = self._debug_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, doc.blockCount() - 500)
            cursor.removeSelectedText()

    def _toggle_debug(self):
        self._expanded = not self._expanded
        self._debug_log.setVisible(self._expanded)
        self._toggle_btn.setText("hide trace" if self._expanded else "trace")

    def toggle_from_shortcut(self):
        self._toggle_debug()


# ================================================================
# Tools Dialog (secondary panel for ingest/tag/library)
# ================================================================

class ToolsDialog(QDialog):
    """Modal dialog grouping Harvest, Auto-tag, Library, Balance tools."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("tools")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(f"background-color: {BG_DEEP}; color: {FG_PRIMARY}; border: 1px solid {BG_SURFACE};")
        self._parent = parent
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        # -- Harvest --
        hg = QGroupBox("harvest")
        hg.setStyleSheet(f"QGroupBox {{ color: {FG_DIM}; border: 1px solid {BG_SURFACE}; border-radius: 8px; padding-top: 16px; }}")
        hlay = QFormLayout(hg)
        self.ingest_limit = QSpinBox(); self.ingest_limit.setRange(1, 200); self.ingest_limit.setValue(3)
        self.ingest_query = QLineEdit()
        self.ingest_source = QComboBox(); self.ingest_source.addItems(["all", "freesound", "internet_archive", "wikimedia"])
        self.ingest_category = QLineEdit()
        self.ingest_dry_run = QCheckBox("dry run")
        self.ingest_auto_tag = QCheckBox("auto-tag"); self.ingest_auto_tag.setChecked(True)
        hlay.addRow("limit", self.ingest_limit)
        hlay.addRow("query", self.ingest_query)
        hlay.addRow("source", self.ingest_source)
        hlay.addRow("category", self.ingest_category)
        opts = QHBoxLayout()
        opts.addWidget(self.ingest_dry_run); opts.addWidget(self.ingest_auto_tag)
        hlay.addRow("", opts)
        harvest_btn = PillButton("run harvest", ACCENT_CYAN)
        harvest_btn.clicked.connect(self._run_harvest)
        hlay.addRow("", harvest_btn)
        lay.addWidget(hg)

        # -- Auto Tag --
        tg = QGroupBox("auto tag")
        tg.setStyleSheet(f"QGroupBox {{ color: {FG_DIM}; border: 1px solid {BG_SURFACE}; border-radius: 8px; padding-top: 16px; }}")
        tlay = QFormLayout(tg)
        self.tag_model = QLineEdit("qwen3-coder:30b")
        self.tag_limit = QSpinBox(); self.tag_limit.setRange(0, 10000); self.tag_limit.setValue(20)
        self.tag_asset_id = QLineEdit()
        self.tag_retag = QCheckBox("retag existing")
        self.tag_dry_run = QCheckBox("dry run")
        tlay.addRow("model", self.tag_model)
        tlay.addRow("limit", self.tag_limit)
        tlay.addRow("asset id", self.tag_asset_id)
        topts = QHBoxLayout()
        topts.addWidget(self.tag_retag); topts.addWidget(self.tag_dry_run)
        tlay.addRow("", topts)
        tag_btn = PillButton("run auto tag", ACCENT_VIOLET)
        tag_btn.clicked.connect(self._run_auto_tag)
        tlay.addRow("", tag_btn)
        lay.addWidget(tg)

        # -- Library --
        lg = QGroupBox("library")
        lg.setStyleSheet(f"QGroupBox {{ color: {FG_DIM}; border: 1px solid {BG_SURFACE}; border-radius: 8px; padding-top: 16px; }}")
        llib = QVBoxLayout(lg)
        self.lib_summary_lbl = QLabel("not loaded")
        self.lib_summary_lbl.setStyleSheet(f"color: {FG_PRIMARY}; font-size: 13px;")
        llib.addWidget(self.lib_summary_lbl)
        lib_row = QHBoxLayout()
        refresh_btn = PillButton("refresh stats", ACCENT_CYAN)
        refresh_btn.clicked.connect(self._refresh_library)
        lib_row.addWidget(refresh_btn)
        review_btn = PillButton("open review tool", FG_DIM)
        review_btn.clicked.connect(self._open_review_tool)
        lib_row.addWidget(review_btn)
        lib_row.addStretch()
        llib.addLayout(lib_row)

        # Balance
        bal_row = QHBoxLayout()
        analyze_btn = PillButton("analyze balance", ACCENT_CYAN)
        analyze_btn.clicked.connect(self._analyze_balance)
        bal_row.addWidget(analyze_btn)
        break_btn = PillButton("break balance", ACCENT_AMBER)
        break_btn.clicked.connect(self._break_balance)
        bal_row.addWidget(break_btn)
        self.rebalance_auto_tag = QCheckBox("auto-tag"); self.rebalance_auto_tag.setChecked(True)
        bal_row.addWidget(self.rebalance_auto_tag)
        rebal_btn = PillButton("rebalance", ACCENT_VIOLET)
        rebal_btn.clicked.connect(self._run_rebalance)
        bal_row.addWidget(rebal_btn)
        stop_btn = PillButton("stop", ACCENT_RED)
        stop_btn.clicked.connect(self._stop_rebalance)
        bal_row.addWidget(stop_btn)
        bal_row.addStretch()
        llib.addLayout(bal_row)

        self.balance_text = QTextEdit()
        self.balance_text.setReadOnly(True)
        self.balance_text.setMaximumHeight(160)
        llib.addWidget(self.balance_text)
        lay.addWidget(lg)

        self._refresh_library()

    # -- Delegate actions to parent (BecomingWindow) --
    def _run_harvest(self):
        if not self._parent:
            return
        cmd = [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "harvest_sounds.py"),
               "--limit", str(self.ingest_limit.value())]
        q = self.ingest_query.text().strip()
        s = self.ingest_source.currentText()
        c = self.ingest_category.text().strip()
        if q: cmd.extend(["--queries", q])
        if s and s != "all": cmd.extend(["--source", s])
        if c: cmd.extend(["--category", c])
        if self.ingest_dry_run.isChecked(): cmd.append("--dry-run")
        if self.ingest_auto_tag.isChecked(): cmd.append("--auto-tag")
        self._parent._run_cmd_async("harvest", cmd)

    def _run_auto_tag(self):
        if not self._parent:
            return
        cmd = [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "auto_tag.py"),
               "--model", self.tag_model.text().strip() or "qwen3-coder:30b",
               "--limit", str(self.tag_limit.value())]
        aid = self.tag_asset_id.text().strip()
        if aid: cmd.extend(["--asset-id", aid])
        if self.tag_retag.isChecked(): cmd.append("--retag")
        if self.tag_dry_run.isChecked(): cmd.append("--dry-run")
        self._parent._run_cmd_async("auto_tag", cmd)

    def _refresh_library(self):
        try:
            lib = SoundLibrary()
            lib.load()
            summary = lib.summary()
            total = sum(summary.values())
            parts = " | ".join(f"{k}={v}" for k, v in sorted(summary.items()))
            self.lib_summary_lbl.setText(f"{total} sounds  :  {parts}")
        except Exception as e:
            self.lib_summary_lbl.setText(f"error: {e}")

    def _open_review_tool(self):
        if self._parent:
            cmd = [str(ROOT / ".venv" / "bin" / "python"), "-m", "review_tool.gui"]
            self._parent._run_cmd_async("review_tool", cmd)

    def _analyze_balance(self):
        def worker():
            try:
                from balance import analyze_balance, get_db
                db = get_db()
                report = analyze_balance(db)
                text = self._format_balance(report)
                QTimer.singleShot(0, lambda: self.balance_text.setPlainText(text))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.balance_text.setPlainText(f"ERROR: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _break_balance(self):
        def worker():
            try:
                from balance import analyze_balance, get_db
                from balance_shapes import (
                    _convergent, _bipolar, _cascade, _hollow, _surge, _drought, _normalize,
                )
                from src.engine.vectors import CLUSTER_DEFS
                clusters = sorted(CLUSTER_DEFS.keys())
                shape_makers = [
                    lambda c=clusters: _convergent(c, random.choice(c)),
                    lambda c=clusters: _bipolar(c, *random.sample(c, 2)),
                    lambda c=clusters: _cascade(c, random.sample(c, len(c))),
                    lambda c=clusters: _hollow(c, random.sample(c, max(2, len(c) // 3))),
                    lambda c=clusters: _surge(c),
                    lambda c=clusters: _drought(c),
                ]
                shape = random.choice(shape_makers)()
                db = get_db()
                report = analyze_balance(db, target_shape=shape)
                text = self._format_balance(report)
                QTimer.singleShot(0, lambda: self.balance_text.setPlainText(text))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.balance_text.setPlainText(f"ERROR: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _format_balance(self, report: dict) -> str:
        lines = []
        lines.append(f"Total: {report['total']}  Entropy: {report['entropy']:.3f}/{report['max_entropy']:.3f} ({report.get('entropy_score',0):.1%})")
        lines.append(f"Shape: {report.get('shape_name','uniform')}  Score: {report['balance_score']:.1%}")
        lines.append("")
        for name in sorted(report["clusters"], key=lambda n: -report["clusters"][n]["count"]):
            s = report["clusters"][name]
            bar = "=" * int(s["pct"] / 2)
            deficit = f" (+{s['deficit']})" if s["deficit"] > 0 else ""
            lines.append(f"  {name:<20s} {s['count']:>4d}  {s['pct']:5.1f}%  {bar}{deficit}")
        return "\n".join(lines)

    def _run_rebalance(self):
        if not self._parent:
            return
        cmd = [str(ROOT / ".venv" / "bin" / "python"), "-u", str(ROOT / "balance.py"), "--rebalance"]
        if self.rebalance_auto_tag.isChecked():
            cmd.append("--auto-tag")
        self._parent._run_cmd_async("rebalance", cmd)

    def _stop_rebalance(self):
        if self._parent:
            proc = self._parent._async_procs.get("rebalance")
            if proc and proc.poll() is None:
                proc.terminate()
                self._parent._log("rebalance", "stopped by user")


# ================================================================
# Main Window
# ================================================================

class BecomingWindow(QMainWindow):
    """The main atmospheric interface."""

    _log_signal = Signal(str, str)  # (source, line) — thread-safe log
    _midi_signal = Signal(str, str, float)  # (slider_attr, cmd, value)
    _poem_line_signal = Signal(str, str)  # (timestamp, text)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("becoming")
        self.setMinimumSize(1200, 920)
        self.resize(1600, 1120)

        self.engine_proc: subprocess.Popen | None = None
        self.engine_reader_thread: threading.Thread | None = None
        self._async_procs: dict[str, subprocess.Popen] = {}
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._midi_port = None
        self._midi_thread: threading.Thread | None = None

        self._poem_running = False
        self._poem_thread: threading.Thread | None = None
        self._poem_lines: list[str] = []
        self._poem_beat_index = 0

        self._tools_dialog: ToolsDialog | None = None

        self._build_layout()
        self._connect_signals()

        # Log drain timer
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(120)

        self._start_midi_listener()
        self._midi_signal.connect(self._apply_midi)
        self._poem_line_signal.connect(self._add_poem_to_drift)

    def _build_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Main horizontal: influence | drift field | poem
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._influence = InfluencePanel()
        # Wrap influence panel in scroll area so it never clips
        influence_scroll = QScrollArea()
        influence_scroll.setWidget(self._influence)
        influence_scroll.setWidgetResizable(True)
        influence_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        influence_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        influence_scroll.setFixedWidth(self._influence.width() + 6)
        influence_scroll.setStyleSheet(f"QScrollArea {{ background: {BG_PANEL}; border: none; }}")
        body.addWidget(influence_scroll)

        self._drift = DriftFieldWidget()
        body.addWidget(self._drift, stretch=1)

        main_lay.addLayout(body, stretch=1)

        # Whisper bar
        self._whisper = WhisperBar()
        main_lay.addWidget(self._whisper)

    def _connect_signals(self):
        self._influence.sliderChanged.connect(self._on_slider)
        self._influence.interventionClicked.connect(self._send_engine_cmd)
        self._influence.engineStartRequested.connect(self._start_engine)
        self._influence.engineStopRequested.connect(self._stop_engine)
        self._influence.poem_toggle_btn.clicked.connect(self._toggle_poem)
        self._influence.harvest_btn.clicked.connect(self._open_harvest)
        self._influence.autotag_btn.clicked.connect(self._open_autotag)
        self._influence.library_btn.clicked.connect(self._open_library)
        self._influence.rebalance_btn.clicked.connect(self._run_rebalance_quick)
        self._influence.break_bal_btn.clicked.connect(self._break_balance_quick)

    def keyPressEvent(self, event):
        # Ctrl+D or backtick toggles debug log
        if event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self._whisper.toggle_from_shortcut()
        elif event.key() == Qt.Key_QuoteLeft:
            self._whisper.toggle_from_shortcut()
        else:
            super().keyPressEvent(event)

    def _open_tools(self):
        if self._tools_dialog is None:
            self._tools_dialog = ToolsDialog(self)
        self._tools_dialog.show()
        self._tools_dialog.raise_()

    def _open_harvest(self):
        self._open_tools()
        # Scroll/focus to harvest section if needed

    def _open_autotag(self):
        self._open_tools()

    def _open_library(self):
        self._open_tools()

    def _run_rebalance_quick(self):
        """Run rebalance with auto-tag directly."""
        cmd = [str(ROOT / ".venv" / "bin" / "python"), "-u",
               str(ROOT / "balance.py"), "--rebalance", "--auto-tag"]
        self._run_cmd_async("rebalance", cmd)

    def _break_balance_quick(self):
        """Run break balance analysis in background."""
        def worker():
            try:
                from balance import analyze_balance, get_db
                from balance_shapes import (
                    _convergent, _bipolar, _cascade, _hollow, _surge, _drought,
                )
                from src.engine.vectors import CLUSTER_DEFS
                clusters = sorted(CLUSTER_DEFS.keys())
                shape_makers = [
                    lambda c=clusters: _convergent(c, random.choice(c)),
                    lambda c=clusters: _bipolar(c, *random.sample(c, 2)),
                    lambda c=clusters: _cascade(c, random.sample(c, len(c))),
                    lambda c=clusters: _hollow(c, random.sample(c, max(2, len(c) // 3))),
                    lambda c=clusters: _surge(c),
                    lambda c=clusters: _drought(c),
                ]
                shape = random.choice(shape_makers)()
                db = get_db()
                report = analyze_balance(db, target_shape=shape)
                name = report.get("shape_name", "uniform")
                score = report["balance_score"]
                self.log_queue.put(("balance", f"BREAK -> shape={name} score={score:.1%}"))
            except Exception as e:
                self.log_queue.put(("balance", f"ERROR: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Slider / Engine interaction
    # ------------------------------------------------------------------

    def _on_slider(self, cmd: str, value: float):
        """Send slider change to running engine."""
        if self.engine_proc and self.engine_proc.poll() is None and self.engine_proc.stdin:
            try:
                self.engine_proc.stdin.write(f"{cmd} {value:.3f}\n")
                self.engine_proc.stdin.flush()
            except Exception:
                pass
        # Update drift field params
        if cmd == "t":
            self._drift.set_params(value, self._drift._density, self._drift._temperature)
        elif cmd == "d":
            self._drift.set_params(self._drift._tension, value, self._drift._temperature)
        elif cmd == "T":
            self._drift.set_params(self._drift._tension, self._drift._density, value)

    def _start_engine(self):
        if self.engine_proc and self.engine_proc.poll() is None:
            QMessageBox.information(self, "Engine", "Engine is already running.")
            return

        state = self._influence.init_state_combo.currentText()
        tension = self._influence.strain_slider.value()
        density = self._influence.saturation_slider.value()
        temp = self._influence.heat_slider.value()

        cmd = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "engine.py"),
            "--state", state,
            "--tension", f"{tension:.3f}",
            "--density", f"{density:.3f}",
            "--temperature", f"{temp:.3f}",
        ]

        try:
            self.engine_proc = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except Exception as e:
            QMessageBox.critical(self, "Engine", f"Failed to start engine:\n{e}")
            return

        self._whisper.set_status("engine running")
        self._log("engine", f"started: {' '.join(cmd)}")
        self._start_engine_reader()

    def _start_engine_reader(self):
        if not self.engine_proc or not self.engine_proc.stdout:
            return
        def read_loop():
            proc = self.engine_proc
            if not proc or not proc.stdout:
                return
            for line in proc.stdout:
                self.log_queue.put(("engine", line.rstrip("\n")))
            code = proc.poll()
            self.log_queue.put(("engine", f"[process exited code={code}]"))
            self.log_queue.put(("status", "engine stopped"))
        self.engine_reader_thread = threading.Thread(target=read_loop, daemon=True)
        self.engine_reader_thread.start()

    def _send_engine_cmd(self, cmd: str):
        if not self.engine_proc or self.engine_proc.poll() is not None or not self.engine_proc.stdin:
            return
        if not cmd.endswith("\n"):
            cmd = cmd + "\n"
        try:
            self.engine_proc.stdin.write(cmd)
            self.engine_proc.stdin.flush()
            self._log("engine", f"> {cmd.strip()}")
        except Exception:
            pass

    def _stop_engine(self):
        if not self.engine_proc or self.engine_proc.poll() is not None:
            self._whisper.set_status("engine stopped")
            return
        try:
            if self.engine_proc.stdin:
                self.engine_proc.stdin.write("q\n")
                self.engine_proc.stdin.flush()
        except Exception:
            pass
        try:
            self.engine_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.engine_proc.terminate()
        self._whisper.set_status("engine stopped")
        self._log("engine", "stop requested")

    # ------------------------------------------------------------------
    # Async command runner
    # ------------------------------------------------------------------

    def _run_cmd_async(self, label: str, cmd: list[str]):
        self._log(label, f"running: {' '.join(cmd)}")
        def worker():
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                self._async_procs[label] = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.log_queue.put((label, line.rstrip("\n")))
                code = proc.wait()
                self._async_procs.pop(label, None)
                self.log_queue.put((label, f"[done exit={code}]"))
            except Exception as e:
                self._async_procs.pop(label, None)
                self.log_queue.put((label, f"ERROR: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, source: str, line: str):
        self.log_queue.put((source, line))

    def _drain_log_queue(self):
        try:
            for _ in range(50):  # process up to 50 per tick
                source, line = self.log_queue.get_nowait()
                if source == "status":
                    self._whisper.set_status(line)
                    continue
                if "[drift-snapshot]" in line:
                    self._handle_drift_snapshot(line)
                if "[poem-words]" in line:
                    self._handle_poem_words(line)
                self._whisper.append_log(source, line)
        except queue.Empty:
            pass

    def _handle_drift_snapshot(self, line: str):
        try:
            idx = line.index("[drift-snapshot]")
            raw = line[idx + len("[drift-snapshot]"):].strip()
            snap = json.loads(raw)
            self._drift.update_snapshot(snap)
        except (ValueError, json.JSONDecodeError):
            pass

    def _refresh_drift_status(self):
        self._send_engine_cmd("D")

    # ------------------------------------------------------------------
    # MIDI
    # ------------------------------------------------------------------

    MIDI_CC_MAP: dict[int, tuple[str, str, float, float]] = {
        40: ("strain_slider", "t", 0.0, 1.0),
        41: ("saturation_slider", "d", 0.0, 1.0),
        42: ("heat_slider", "T", 0.0, 1.0),
        43: ("timescale_slider", "dur", 0.1, 3.0),
    }
    MIDI_PREFERRED_PORT = "Private"

    def _start_midi_listener(self):
        if not HAS_MIDI:
            self.log_queue.put(("midi", "mido not installed — MIDI disabled"))
            return
        self.log_queue.put(("midi", "starting listener (CC 40-43)..."))
        self._midi_thread = threading.Thread(target=self._midi_loop, daemon=True)
        self._midi_thread.start()

    def _midi_loop(self):
        while True:
            try:
                names = mido.get_input_names()
            except Exception as e:
                self.log_queue.put(("midi", f"get_input_names failed: {e}"))
                return
            if not names:
                self.log_queue.put(("midi", "no MIDI devices found, retrying..."))
                time.sleep(5)
                continue
            chosen = names[0]
            for n in names:
                if self.MIDI_PREFERRED_PORT in n:
                    chosen = n
                    break
            try:
                self._midi_port = mido.open_input(chosen)
                self.log_queue.put(("midi", f"connected: {chosen}"))
            except Exception as e:
                self.log_queue.put(("midi", f"open failed: {e}"))
                time.sleep(5)
                continue
            try:
                for msg in self._midi_port:
                    if msg.type == "control_change":
                        if msg.control in self.MIDI_CC_MAP:
                            slider_attr, cmd, lo, hi = self.MIDI_CC_MAP[msg.control]
                            value = lo + (msg.value / 127.0) * (hi - lo)
                            self.log_queue.put(("midi", f"CC{msg.control}→{cmd}={value:.3f}"))
                            self._midi_signal.emit(slider_attr, cmd, value)
                        else:
                            self.log_queue.put(("midi", f"unmapped CC{msg.control} val={msg.value} ch={msg.channel}"))
            except Exception as e:
                self.log_queue.put(("midi", f"read error: {e}"))
            finally:
                try:
                    if self._midi_port:
                        self._midi_port.close()
                except Exception:
                    pass
                self._midi_port = None
            time.sleep(2)

    def _apply_midi(self, slider_attr: str, cmd: str, value: float):
        slider = getattr(self._influence, slider_attr, None)
        if slider:
            slider.setValue(round(value, 3))
        self._on_slider(cmd, value)

    def _add_poem_to_drift(self, ts: str, line: str):
        self._drift.add_poem_line(ts, line)

    # ------------------------------------------------------------------
    # Poem Making
    # ------------------------------------------------------------------

    def _toggle_poem(self):
        if self._poem_running:
            self._poem_running = False
            self._influence.poem_toggle_btn.setText("begin poem")
            self._log("poem", "stopped")
        else:
            if not self.engine_proc or self.engine_proc.poll() is not None:
                QMessageBox.warning(self, "Poem", "Engine must be running.")
                return
            self._poem_running = True
            self._influence.poem_toggle_btn.setText("end poem")
            self._log("poem", "started")
            self._poem_thread = threading.Thread(target=self._poem_loop, daemon=True)
            self._poem_thread.start()

    def _poem_loop(self):
        while self._poem_running:
            if self.engine_proc and self.engine_proc.poll() is None and self.engine_proc.stdin:
                try:
                    self.engine_proc.stdin.write("poem\n")
                    self.engine_proc.stdin.flush()
                    self.log_queue.put(("poem", "sent poem request to engine"))
                except Exception as e:
                    self.log_queue.put(("poem", f"send failed: {e}"))
            else:
                self.log_queue.put(("poem", "engine not running, skipping"))
            interval = max(5, self._influence.poem_interval_spin.value())
            for _ in range(interval * 10):
                if not self._poem_running:
                    return
                time.sleep(0.1)

    def _handle_poem_words(self, line: str):
        try:
            idx = line.index("[poem-words]")
            raw = line[idx + len("[poem-words]"):].strip()
            blob = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return

        def worker():
            try:
                from poem_maker import harvest_words, build_poem_prompt, generate_line
                words_str = harvest_words(blob)
                beat = "ascending" if self._poem_beat_index % 2 == 0 else "descending"
                rhyme_word = None
                if self._poem_beat_index % 2 == 1 and self._poem_lines:
                    words_in_prev = re.findall(r"[a-zA-Z]+", self._poem_lines[-1])
                    if words_in_prev:
                        rhyme_word = words_in_prev[-1].lower()
                self.log_queue.put(("poem", f"generating (beat={beat}, words={words_str[:40]}...)"))
                prompt = build_poem_prompt(
                    words_str,
                    blob.get("state", "drifting"),
                    blob.get("phase", "drift"),
                    blob.get("tension", 0.3),
                    blob.get("density", 0.5),
                    previous_lines=self._poem_lines[-3:] if self._poem_lines else None,
                    beat=beat,
                    rhyme_word=rhyme_word,
                )
                model = "qwen3-coder:30b"
                if self._tools_dialog:
                    model = self._tools_dialog.tag_model.text().strip() or model
                poem_line = generate_line(prompt, model=model)
                if poem_line:
                    self._poem_lines.append(poem_line)
                    self._poem_beat_index += 1
                    if len(self._poem_lines) > 200:
                        self._poem_lines = self._poem_lines[-200:]
                    ts = datetime.now().strftime("%H:%M")
                    self.log_queue.put(("poem", f"line: {poem_line[:60]}"))
                    self._poem_line_signal.emit(ts, poem_line)
                else:
                    self.log_queue.put(("poem", "generate_line returned empty"))
            except Exception as e:
                self.log_queue.put(("poem", f"error: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._poem_running = False
        try:
            if self._midi_port:
                self._midi_port.close()
        except Exception:
            pass
        # Kill engine process forcefully
        if self.engine_proc and self.engine_proc.poll() is None:
            try:
                self.engine_proc.stdin.write("q\n")
                self.engine_proc.stdin.flush()
            except Exception:
                pass
            try:
                self.engine_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.engine_proc.kill()
                try:
                    self.engine_proc.wait(timeout=2)
                except Exception:
                    pass
        # Kill any async child processes
        for proc in self._async_procs.values():
            try:
                proc.kill()
            except Exception:
                pass
        event.accept()


# ================================================================
# Entry Point
# ================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_SS)
    win = BecomingWindow()
    win.show()
    sys.exit(app.exec())
