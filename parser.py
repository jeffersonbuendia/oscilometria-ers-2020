# -*- coding: utf-8 -*-
"""
Parser del formato PulmoScan (Cognita Labs).

Extrae de manera robusta todos los campos del informe oscilométrico:
  - Página 1 (resumen): parámetros principales con pre, z-score, %pred,
                        post, z-score post, %pred post, cambio %
  - Página 2 (pre detallado): parámetros inspiratorios/espiratorios,
                               parámetros respiratorios
  - Página 3 (post detallado): ídem para la serie post-BD
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

import pymupdf

from models import (
    BreathingParams,
    OscParameter,
    OscillometrySession,
    PatientData,
    QualityData,
    WithinBreathParams,
)

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _num(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.strip().replace(",", ".")
    if s in ("-", "", "n/a", "N/A", "—"):
        return None
    m = re.search(r"[-+]?\d+\.?\d*", s)
    return float(m.group()) if m else None


def _text(pdf_bytes: bytes) -> list[str]:
    """Devuelve el texto de cada página del PDF."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return pages


# ---------------------------------------------------------------------------
# Página 1: cabecera del paciente
# ---------------------------------------------------------------------------

def _parse_patient(text: str) -> PatientData:
    p = PatientData()

    m = re.search(r"Patient:\s*(.+?)(?:\n|$)", text)
    if m:
        p.name = m.group(1).strip()

    m = re.search(r"Gender\s+(\w+)", text)
    if m:
        p.gender = m.group(1)

    m = re.search(r"Height\s+([\d.]+)\s*cm", text)
    if m:
        p.height_cm = float(m.group(1))

    m = re.search(r"Weight\s+([\d.]+)\s*kg", text)
    if m:
        p.weight_kg = float(m.group(1))

    m = re.search(r"Age\s+([\d.]+)\s*years?", text)
    if m:
        p.age_years = float(m.group(1))

    m = re.search(r"Ethnicity\s+(.+?)(?:\n|$)", text)
    if m:
        p.ethnicity = m.group(1).strip()

    m = re.search(r"Smoking History\s+(.+?)(?:\n|$)", text)
    if m:
        p.smoking_history = m.group(1).strip()

    m = re.search(r"Reference Equation\s+(.+?)(?:\n|$)", text)
    if m:
        p.reference_equation = m.group(1).strip()

    m = re.search(r"Operator\s+(.+?)(?:\n|$)", text)
    if m:
        p.operator = m.group(1).strip()

    m = re.search(r"Patient ID\s+(.+?)(?:\n|$)", text)
    if m:
        p.patient_id = m.group(1).strip()

    m = re.search(r"Session ID:\s*(.+?)(?:\n|$)", text)
    if m:
        p.session_id = m.group(1).strip()

    # Fecha del informe (encabezado superior)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        p.exam_date = m.group(1)

    m = re.search(r"Notes\s*\n(.+?)(?:\n|$)", text)
    if m:
        p.notes = m.group(1).strip()

    return p


# ---------------------------------------------------------------------------
# Página 1: parámetros principales
# ---------------------------------------------------------------------------

# Mapeo de nombres del PDF a claves canónicas y unidades
_PARAM_MAP = {
    "R5":     ("R5",     "cmH₂O/L/s"),
    "R20":    ("R20",    "cmH₂O/L/s"),
    "R5-R20": ("R5-R20", "cmH₂O/L/s"),
    "AX":     ("AX",     "cmH₂O/L"),
    "X5":     ("X5",     "cmH₂O/L/s"),
    "Fres":   ("Fres",   "Hz"),
}

_BD_THRESHOLDS = {
    "R5":     "< −40 %",
    "X5":     "> +50 %",
    "AX":     "< −80 %",
    "Fres":   "—",
    "R20":    "—",
    "R5-R20": "—",
}


def _parse_main_params(text: str) -> dict:
    """
    Extrae la tabla principal de parámetros de la página 1 del PulmoScan.

    Formato esperado (cada parámetro en una línea o bloque):
    R5 (cmH2O/L/s)  9.41  2.83  -4.51  30%  3.77  -3.87  40%  33% [<-40%]
    """
    params = {}

    for raw_name, (key, unit) in _PARAM_MAP.items():
        # Regex flexible que captura todos los campos numéricos de la fila
        pattern = (
            r"(?:" + re.escape(raw_name) +
            r")\s*(?:\([^)]*\))?\s+"
            r"([-\d.]+)\s+"          # Reference
            r"([-\d.]+)\s+"          # Pre
            r"([-\d.]+)\s+"          # Pre Z
            r"(-|[\d.]+%?)\s+"       # Pre %pred
            r"([-\d.]+)\s+"          # Post
            r"([-\d.]+)\s+"          # Post Z
            r"(-|[\d.]+%?)\s*"       # Post %pred
            r"([-\d.]+%?)\s*"        # Pre-Post %
            r"(\[[^\]]*\])?"         # [threshold] opcional
        )
        m = re.search(pattern, text)
        if m:
            p = OscParameter(name=key, unit=unit)
            p.reference = _num(m.group(1))
            p.pre = _num(m.group(2))
            p.pre_z = _num(m.group(3))
            pct_str = m.group(4).replace("%", "").strip()
            p.pre_pct_pred = _num(pct_str)
            p.post = _num(m.group(5))
            p.post_z = _num(m.group(6))
            pct_post_str = m.group(7).replace("%", "").strip()
            p.post_pct_pred = _num(pct_post_str)
            chg_str = m.group(8).replace("%", "").strip()
            p.pre_post_pct = _num(chg_str)
            thresh = m.group(9)
            p.bd_threshold_label = thresh.strip("[]") if thresh else _BD_THRESHOLDS.get(key, "")
            params[key] = p
        else:
            # Intentar extracción parcial (solo pre sin post)
            pattern2 = (
                r"(?:" + re.escape(raw_name) +
                r")\s*(?:\([^)]*\))?\s+"
                r"([-\d.]+)\s+"
                r"([-\d.]+)\s+"
                r"([-\d.]+)\s*"
            )
            m2 = re.search(pattern2, text)
            if m2:
                p = OscParameter(name=key, unit=unit)
                p.reference = _num(m2.group(1))
                p.pre = _num(m2.group(2))
                p.pre_z = _num(m2.group(3))
                p.bd_threshold_label = _BD_THRESHOLDS.get(key, "")
                params[key] = p

    return params


# ---------------------------------------------------------------------------
# Páginas 2 y 3: parámetros intraciclo y respiratorios
# ---------------------------------------------------------------------------

def _parse_within_breath(text: str) -> Tuple[WithinBreathParams, BreathingParams]:
    wb = WithinBreathParams()
    bp = BreathingParams()

    # Parámetros respiratorios generales
    m = re.search(r"Tidal Volume\s+([\d.]+)\s*ml", text)
    if m:
        bp.tidal_volume_ml = float(m.group(1))

    m = re.search(r"Inhalation Time\s+([\d.]+)\s*s", text)
    if m:
        bp.inhalation_time_s = float(m.group(1))

    m = re.search(r"Exhalation Time\s+([\d.]+)\s*s", text)
    if m:
        bp.exhalation_time_s = float(m.group(1))

    m = re.search(r"Respiratory Duty Cycle\s+([\d.]+)", text)
    if m:
        bp.respiratory_duty_cycle = float(m.group(1))

    m = re.search(r"Respiratory Rate\s+([\d.]+)\s*cycles", text)
    if m:
        bp.respiratory_rate_cpm = float(m.group(1))

    m = re.search(r"Mean Inspiratory Flow\s+([\d.]+)", text)
    if m:
        bp.mean_inspiratory_flow_ml_s = float(m.group(1))

    m = re.search(r"Mean Expiratory Flow\s+([\d.]+)", text)
    if m:
        bp.mean_expiratory_flow_ml_s = float(m.group(1))

    m = re.search(r"Coherence\s+([\d.]+)", text)
    if m:
        bp.coherence = float(m.group(1))

    m = re.search(r"(?:Pre|Post)\s+-\s+\d+\)\s+Time:\s*(.+?)(?:\n|$)", text)
    if m:
        bp.session_time = m.group(1).strip()

    def _get_insp(param: str, freq: str) -> Optional[float]:
        pattern = r"R_?insp_?5\s*[\-–]\s*R_?insp_?20\s+([-\d.]+)" if "5_20" in param else \
                  (r"AX_?insp\s+([-\d.]+)" if "ax" in param.lower() else
                   r"Fres_?insp\s+([-\d.]+)" if "fres" in param.lower() else
                   rf"(?:X_?insp|Xinsp)\s*{freq}\s+([-\d.]+)" if param.startswith("X") else
                   rf"(?:R_?insp|Rinsp)\s*{freq}\s+([-\d.]+)")
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    def _get_exp(param: str, freq: str) -> Optional[float]:
        pattern = r"R_?exp_?5\s*[\-–]\s*R_?exp_?20\s+([-\d.]+)" if "5_20" in param else \
                  (r"AX_?exp\s+([-\d.]+)" if "ax" in param.lower() else
                   r"Fres_?exp\s+([-\d.]+)" if "fres" in param.lower() else
                   rf"(?:X_?exp|Xexp)\s*{freq}\s+([-\d.]+)" if param.startswith("X") else
                   rf"(?:R_?exp|Rexp)\s*{freq}\s+([-\d.]+)")
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    # Resistencias inspiratorias
    for freq, attr in [("5", "r_insp_5"), ("10", "r_insp_10"), ("15", "r_insp_15"),
                       ("20", "r_insp_20"), ("25", "r_insp_25"), ("30", "r_insp_30")]:
        m = re.search(rf"(?:R_?insp|Rinsp)\s*{freq}\b\s+([-\d.]+)", text)
        if m:
            setattr(wb, attr, float(m.group(1)))

    m = re.search(r"(?:R_?insp|Rinsp)\s*5\s*[-–]\s*(?:R_?insp|Rinsp)\s*20\s+([-\d.]+)", text)
    if m:
        wb.r_insp_5_20 = float(m.group(1))

    # Reactancias inspiratorias
    for freq, attr in [("5", "x_insp_5"), ("10", "x_insp_10"), ("15", "x_insp_15"),
                       ("20", "x_insp_20"), ("25", "x_insp_25"), ("30", "x_insp_30")]:
        m = re.search(rf"(?:X_?insp|Xinsp)\s*{freq}\b\s+([-\d.]+)", text)
        if m:
            setattr(wb, attr, float(m.group(1)))

    m = re.search(r"(?:Fres_?insp|Fresinsp)\s+([\d.]+)", text)
    if m:
        wb.fres_insp = float(m.group(1))

    m = re.search(r"(?:AX_?insp|AXinsp)\s+([-\d.]+)", text)
    if m:
        wb.ax_insp = float(m.group(1))

    # Resistencias espiratorias
    for freq, attr in [("5", "r_exp_5"), ("10", "r_exp_10"), ("15", "r_exp_15"),
                       ("20", "r_exp_20"), ("25", "r_exp_25"), ("30", "r_exp_30")]:
        m = re.search(rf"(?:R_?exp|Rexp)\s*{freq}\b\s+([-\d.]+)", text)
        if m:
            setattr(wb, attr, float(m.group(1)))

    m = re.search(r"(?:R_?exp|Rexp)\s*5\s*[-–]\s*(?:R_?exp|Rexp)\s*20\s+([-\d.]+)", text)
    if m:
        wb.r_exp_5_20 = float(m.group(1))

    # Reactancias espiratorias
    for freq, attr in [("5", "x_exp_5"), ("10", "x_exp_10"), ("15", "x_exp_15"),
                       ("20", "x_exp_20"), ("25", "x_exp_25"), ("30", "x_exp_30")]:
        m = re.search(rf"(?:X_?exp|Xexp)\s*{freq}\b\s+([-\d.]+)", text)
        if m:
            setattr(wb, attr, float(m.group(1)))

    m = re.search(r"(?:Fres_?exp|Fresexp)\s+([\d.]+)", text)
    if m:
        wb.fres_exp = float(m.group(1))

    m = re.search(r"(?:AX_?exp|AXexp)\s+([-\d.]+)", text)
    if m:
        wb.ax_exp = float(m.group(1))

    return wb, bp


# ---------------------------------------------------------------------------
# Calidad y coherencia (de la página 1)
# ---------------------------------------------------------------------------

def _parse_quality(text: str) -> QualityData:
    q = QualityData()

    m = re.search(r"Average Coherence:\s*([\d.]+)", text)
    if m:
        q.avg_coherence = float(m.group(1))

    m = re.search(r"COV_pre R5\s*=\s*(.+?)(?:\n|$)", text)
    if m:
        q.cov_pre_r5 = m.group(1).strip()
        v = _num(m.group(1))
        if v is not None:
            q.cov_r5_pct = v

    m = re.search(r"COV_post R5\s*=\s*(.+?)(?:\n|$)", text)
    if m:
        q.cov_post_r5 = m.group(1).strip()

    return q


# ---------------------------------------------------------------------------
# Función principal de parseo
# ---------------------------------------------------------------------------

def parse_report(pdf_bytes: bytes) -> Tuple[OscillometrySession, str]:
    """
    Parsea el PDF de PulmoScan y devuelve (OscillometrySession, texto_crudo).

    El segundo elemento es el texto de todas las páginas concatenado,
    útil para depuración desde la interfaz.
    """
    pages = _text(pdf_bytes)
    raw_text = "\n\n=== PÁGINA ".join(
        [f"{i+1} ===\n{p}" for i, p in enumerate(pages)])

    session = OscillometrySession()

    # Página 1: paciente + parámetros principales + calidad
    if pages:
        p1 = pages[0]
        session.patient = _parse_patient(p1)
        session.params = _parse_main_params(p1)
        session.quality = _parse_quality(p1)

        # Detectar si hay valores post
        session.has_post = any(
            p.post is not None for p in session.params.values()
        )

    # Páginas 2 y 3: detalles pre y post
    pre_page, post_page = None, None
    for pg in pages[1:]:
        if re.search(r"Pre\s*-\s*\d+\)", pg):
            pre_page = pg
        elif re.search(r"Post\s*-\s*\d+\)", pg):
            post_page = pg

    if pre_page:
        wb, bp = _parse_within_breath(pre_page)
        session.pre_within = wb
        session.pre_breathing = bp

    if post_page:
        wb, bp = _parse_within_breath(post_page)
        session.post_within = wb
        session.post_breathing = bp

    # Broncodilatador (texto genérico)
    if session.has_post:
        session.bronchodilator = "Salbutamol (según protocolo del laboratorio)"

    return session, raw_text
