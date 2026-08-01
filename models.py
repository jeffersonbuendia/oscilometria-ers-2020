# -*- coding: utf-8 -*-
"""
Modelos de dominio para la aplicación de oscilometría de impulso.

Referencia técnica:
  King GG, Bates J, Berger KI, et al. Technical standards for respiratory
  oscillometry. Eur Respir J 2020;55:1900753.
  doi:10.1183/13993003.00753-2019
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Parámetro individual
# ---------------------------------------------------------------------------

@dataclass
class OscParameter:
    """
    Un parámetro oscilométrico (R5, X5, AX, Fres, etc.) con sus valores
    de referencia, pre-BD y post-BD.

    Convención de signos para la respuesta broncodilatadora:
      - R5, R20, AX, Fres: mejora cuando DISMINUYEN (cambio negativo = bueno)
      - X5, R5-R20: mejoran cuando X5 aumenta (menos negativo, cambio positivo)
    """
    name: str                          # Nombre del parámetro, p. ej. "R5"
    unit: str = ""                     # Unidad de medida

    reference: Optional[float] = None  # Valor predicho (referencia)
    lln: Optional[float] = None        # Límite inferior de normalidad
    uln: Optional[float] = None        # Límite superior de normalidad

    pre: Optional[float] = None
    pre_z: Optional[float] = None
    pre_pct_pred: Optional[float] = None

    post: Optional[float] = None
    post_z: Optional[float] = None
    post_pct_pred: Optional[float] = None

    #: Cambio pre-post expresado como % (positivo = aumento, negativo = disminución)
    pre_post_pct: Optional[float] = None

    #: Umbral ERS 2020 de respuesta broncodilatadora positiva, p. ej. "<-40%"
    bd_threshold_label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parámetros dentro del ciclo respiratorio
# ---------------------------------------------------------------------------

@dataclass
class WithinBreathParams:
    """
    Parámetros inspiratorios y espiratorios separados.

    Útiles para detectar:
      - EFL (Expiratory Flow Limitation): Rexp >> Rinsp
      - IFL (Inspiratory Flow Limitation): Rinsp >> Rexp
    """
    r_insp_5: Optional[float] = None
    r_insp_10: Optional[float] = None
    r_insp_15: Optional[float] = None
    r_insp_20: Optional[float] = None
    r_insp_25: Optional[float] = None
    r_insp_30: Optional[float] = None
    r_insp_5_20: Optional[float] = None

    x_insp_5: Optional[float] = None
    x_insp_10: Optional[float] = None
    x_insp_15: Optional[float] = None
    x_insp_20: Optional[float] = None
    x_insp_25: Optional[float] = None
    x_insp_30: Optional[float] = None
    fres_insp: Optional[float] = None
    ax_insp: Optional[float] = None

    r_exp_5: Optional[float] = None
    r_exp_10: Optional[float] = None
    r_exp_15: Optional[float] = None
    r_exp_20: Optional[float] = None
    r_exp_25: Optional[float] = None
    r_exp_30: Optional[float] = None
    r_exp_5_20: Optional[float] = None

    x_exp_5: Optional[float] = None
    x_exp_10: Optional[float] = None
    x_exp_15: Optional[float] = None
    x_exp_20: Optional[float] = None
    x_exp_25: Optional[float] = None
    x_exp_30: Optional[float] = None
    fres_exp: Optional[float] = None
    ax_exp: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parámetros respiratorios por sesión
# ---------------------------------------------------------------------------

@dataclass
class BreathingParams:
    """Parámetros del patrón ventilatorio durante la sesión de oscilometría."""
    tidal_volume_ml: Optional[float] = None
    inhalation_time_s: Optional[float] = None
    exhalation_time_s: Optional[float] = None
    respiratory_duty_cycle: Optional[float] = None
    respiratory_rate_cpm: Optional[float] = None
    mean_inspiratory_flow_ml_s: Optional[float] = None
    mean_expiratory_flow_ml_s: Optional[float] = None
    coherence: Optional[float] = None
    session_time: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Control de calidad
# ---------------------------------------------------------------------------

@dataclass
class QualityData:
    """
    Control de calidad de la sesión según ERS 2020.

    Criterios de aceptabilidad:
      - CoV R5 ≤ 10% en adultos, ≤ 15% en niños
      - Mínimo 3 mediciones aceptables
      - Coherencia ≥ 0.95 (recomendada, no excluyente)
    """
    n_measurements: Optional[int] = None
    n_acceptable: Optional[int] = None
    cov_r5_pct: Optional[float] = None
    avg_coherence: Optional[float] = None
    cov_pre_r5: Optional[str] = None    # "n/a" u otro texto del equipo
    cov_post_r5: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Datos del paciente
# ---------------------------------------------------------------------------

@dataclass
class PatientData:
    name: str = ""
    patient_id: str = ""
    gender: str = ""
    age_years: Optional[float] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    ethnicity: str = ""
    smoking_history: str = ""
    reference_equation: str = ""
    operator: str = ""
    exam_date: str = ""
    session_id: str = ""
    notes: str = ""

    @property
    def is_paediatric(self) -> bool:
        return self.age_years is not None and self.age_years < 18.0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Sesión completa
# ---------------------------------------------------------------------------

@dataclass
class OscillometrySession:
    """
    Contenedor completo de una sesión de oscilometría con pre y post BD.
    """
    patient: PatientData = field(default_factory=PatientData)
    quality: QualityData = field(default_factory=QualityData)

    # Parámetros principales (promedio de todas las mediciones pre/post)
    params: dict = field(default_factory=dict)  # {name: OscParameter}

    # Parámetros inspiratorios/espiratorios separados
    pre_within: WithinBreathParams = field(default_factory=WithinBreathParams)
    post_within: WithinBreathParams = field(default_factory=WithinBreathParams)

    # Parámetros respiratorios por serie
    pre_breathing: BreathingParams = field(default_factory=BreathingParams)
    post_breathing: BreathingParams = field(default_factory=BreathingParams)

    has_post: bool = False
    bronchodilator: str = ""

    def to_dict(self) -> dict:
        return {
            "patient": self.patient.to_dict(),
            "quality": self.quality.to_dict(),
            "params": {k: v.to_dict() for k, v in self.params.items()},
            "pre_within": self.pre_within.to_dict(),
            "post_within": self.post_within.to_dict(),
            "pre_breathing": self.pre_breathing.to_dict(),
            "post_breathing": self.post_breathing.to_dict(),
            "has_post": self.has_post,
            "bronchodilator": self.bronchodilator,
        }
