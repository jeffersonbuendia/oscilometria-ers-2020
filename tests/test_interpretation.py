"""Tests del motor de interpretación oscilométrica — ERS 2020."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from models import OscParameter, OscillometrySession, PatientData, QualityData, WithinBreathParams
from interpretation import (
    OscillometryInterpreter, interpret,
    Z_LLN, Z_ULN, BD_R5_THRESHOLD_PCT, BD_X5_THRESHOLD_PCT, BD_AX_THRESHOLD_PCT,
    COV_ADULT_MAX_PCT, COV_PAED_MAX_PCT,
)


def param(name, unit, pre, pre_z, post=None, post_z=None, ref=None):
    p = OscParameter(name=name, unit=unit, pre=pre, pre_z=pre_z,
                     post=post, post_z=post_z, reference=ref)
    if pre is not None and post is not None:
        p.pre_post_pct = (post - pre) / abs(pre) * 100 if pre else None
    return p


def session_normal():
    s = OscillometrySession()
    s.patient = PatientData(name="Normal", age_years=35.0, gender="Male")
    s.quality = QualityData(n_acceptable=5, cov_r5_pct=6.0, avg_coherence=0.97)
    s.params = {
        "R5":     param("R5", "cmH₂O/L/s", pre=3.5, pre_z=0.5),
        "R20":    param("R20", "cmH₂O/L/s", pre=2.8, pre_z=0.2),
        "R5-R20": param("R5-R20", "cmH₂O/L/s", pre=0.7, pre_z=0.8),
        "X5":     param("X5", "cmH₂O/L/s", pre=-2.5, pre_z=-0.9),
        "AX":     param("AX", "cmH₂O/L", pre=5.0, pre_z=0.6),
        "Fres":   param("Fres", "Hz", pre=12.0, pre_z=0.3),
    }
    return s


def session_obstructive():
    s = OscillometrySession()
    s.patient = PatientData(name="Obstructive", age_years=55.0, gender="Male")
    s.quality = QualityData(n_acceptable=3, cov_r5_pct=8.5, avg_coherence=0.96)
    s.params = {
        "R5":     param("R5", "cmH₂O/L/s", pre=9.0, pre_z=2.5),
        "R20":    param("R20", "cmH₂O/L/s", pre=3.5, pre_z=0.8),
        "R5-R20": param("R5-R20", "cmH₂O/L/s", pre=5.5, pre_z=2.8),
        "X5":     param("X5", "cmH₂O/L/s", pre=-6.0, pre_z=-2.2),
        "AX":     param("AX", "cmH₂O/L", pre=25.0, pre_z=2.1),
        "Fres":   param("Fres", "Hz", pre=22.0, pre_z=0.9),
    }
    return s


def session_pulmoscan_real():
    """Caso real IAN GAEL FLORES QUERALES — 4.5 años."""
    s = OscillometrySession()
    s.patient = PatientData(name="Ian Gael", age_years=4.5, gender="Male")
    s.quality = QualityData(n_acceptable=None, cov_r5_pct=None, avg_coherence=0.96)
    s.params = {
        "R5":     param("R5",     "cmH₂O/L/s", 2.83, -4.51, 3.77,  -3.87, ref=9.41),
        "R20":    param("R20",    "cmH₂O/L/s", 3.09, -3.38, 4.02,  -2.55, ref=6.87),
        "R5-R20": param("R5-R20", "cmH₂O/L/s",-0.26, -3.74,-0.25, -3.74, ref=2.57),
        "AX":     param("AX",     "cmH₂O/L",   0.11,-14.13, 1.25,  -7.49, ref=19.37),
        "X5":     param("X5",     "cmH₂O/L/s",-0.11,  3.60,-0.56,  3.12, ref=-3.49),
        "Fres":   param("Fres",   "Hz",         5.53, -6.40, 8.63,  -5.26, ref=22.88),
    }
    s.has_post = True
    return s


# ---------------------------------------------------------------- calidad
def test_calidad_ok():
    r = OscillometryInterpreter.quality_check(session_normal(), paediatric=False)
    assert r.grade == "OK"
    assert r.cov_ok is True
    assert r.coherence_ok is True
    assert r.n_ok is True


def test_calidad_pediatrico_umbral_mayor():
    s = session_normal()
    s.quality.cov_r5_pct = 12.0  # > adulto (10%) pero < pediátrico (15%)
    r_adulto = OscillometryInterpreter.quality_check(s, paediatric=False)
    r_paed = OscillometryInterpreter.quality_check(s, paediatric=True)
    assert r_adulto.cov_ok is False
    assert r_paed.cov_ok is True


def test_calidad_sin_datos():
    s = OscillometrySession()
    s.quality = QualityData()
    r = OscillometryInterpreter.quality_check(s)
    assert "CoV" in " ".join(r.notes)


# ---------------------------------------------------------------- patrón
def test_patron_normal():
    r = interpret(session_normal())
    assert r.pattern.label == "Normal"


def test_patron_obstructivo_periferico():
    s = session_normal()
    s.params["R5-R20"].pre_z = 2.5
    s.params["X5"].pre_z = -2.0
    s.params["AX"].pre_z = 2.2
    # R20 dentro de la normalidad
    r = interpret(s)
    assert "Obstructivo" in r.pattern.label
    assert "periférico" in r.pattern.subtype.lower() or "pequeña" in r.pattern.subtype.lower()


def test_patron_obstructivo_general():
    r = interpret(session_obstructive())
    assert "Obstructivo" in r.pattern.label


def test_patron_atipico_baja_impedancia():
    """Caso real: R5, AX, Fres por debajo del LLN; X5 por encima del ULN."""
    r = interpret(session_pulmoscan_real())
    assert "atípico" in r.pattern.label.lower() or "baja" in r.pattern.label.lower()


def test_patron_restrictivo():
    s = session_normal()
    s.params["X5"].pre_z = -3.5     # muy negativo
    s.params["AX"].pre_z = 2.5      # AX elevado
    s.params["R5"].pre_z = 0.3      # R5 normal
    s.params["R5-R20"].pre_z = 0.2  # R5-R20 normal
    r = interpret(s)
    assert "Restrictivo" in r.pattern.label or "reactancia" in r.pattern.label.lower()


# ---------------------------------------------------------------- BDR
def test_bd_r5_positiva():
    s = session_normal()
    s.params["R5"].pre = 10.0
    s.params["R5"].post = 5.0  # disminución 50%
    s.has_post = True
    r = OscillometryInterpreter.evaluate_bd(s)
    assert r.r5_positive is True
    assert r.positive is True


def test_bd_x5_positiva():
    s = session_normal()
    s.params["X5"].pre = -4.0
    s.params["X5"].post = -1.5  # aumento (menos negativo): 62.5%
    s.has_post = True
    r = OscillometryInterpreter.evaluate_bd(s)
    assert r.x5_positive is True


def test_bd_ax_positiva():
    s = session_normal()
    s.params["AX"].pre = 10.0
    s.params["AX"].post = 1.5   # disminución 85%
    s.has_post = True
    r = OscillometryInterpreter.evaluate_bd(s)
    assert r.ax_positive is True


def test_bd_negativa_caso_real():
    """Ian Gael: todos los parámetros empeoran post-BD."""
    r = interpret(session_pulmoscan_real())
    assert r.bd.positive is False
    assert r.bd.r5_positive is False
    assert r.bd.x5_positive is False
    assert r.bd.ax_positive is False


def test_bd_umbrales_son_exactos():
    s = session_normal()
    s.params["R5"].pre = 10.0
    s.params["R5"].post = 6.1   # disminución 39% < 40% → negativa
    s.has_post = True
    r = OscillometryInterpreter.evaluate_bd(s)
    assert r.r5_positive is False

    s.params["R5"].post = 5.9   # disminución 41% → positiva
    r = OscillometryInterpreter.evaluate_bd(s)
    assert r.r5_positive is True


# ---------------------------------------------------------------- intraciclo
def test_efl_detectada():
    wb = WithinBreathParams(r_insp_5=3.0, r_exp_5=4.5)  # exp >> insp
    r = OscillometryInterpreter.analyze_within_breath(wb)
    assert r.efl_suspected is True
    assert r.ifl_suspected is False


def test_ifl_detectada():
    wb = WithinBreathParams(r_insp_5=5.0, r_exp_5=2.5)  # insp >> exp
    r = OscillometryInterpreter.analyze_within_breath(wb)
    assert r.ifl_suspected is True
    assert r.efl_suspected is False


def test_sin_disociacion():
    wb = WithinBreathParams(r_insp_5=3.0, r_exp_5=3.1)
    r = OscillometryInterpreter.analyze_within_breath(wb)
    assert r.efl_suspected is False
    assert r.ifl_suspected is False


def test_sin_datos_intraciclo():
    r = OscillometryInterpreter.analyze_within_breath(WithinBreathParams())
    assert r.efl_suspected is False
    assert "No se dispone" in r.text


# ---------------------------------------------------------------- constantes
@pytest.mark.parametrize("val,esperado", [
    (Z_LLN, -1.645), (Z_ULN, 1.645),
    (BD_R5_THRESHOLD_PCT, -40.0),
    (BD_X5_THRESHOLD_PCT, 50.0),
    (BD_AX_THRESHOLD_PCT, -80.0),
    (COV_ADULT_MAX_PCT, 10.0),
    (COV_PAED_MAX_PCT, 15.0),
])
def test_constantes_normativas(val, esperado):
    assert val == pytest.approx(esperado)


# ---------------------------------------------------------------- PDF
def test_genera_pdf():
    """Generación de PDF no lanza excepción."""
    from informe_oscilometria import InformeOscilometria
    gen = InformeOscilometria(
        institucion="SALUD ES VIVIR IPS",
        firmante="Jefferson Antonio Buendía",
        credenciales="MD · Neumólogo Pediatra",
    )
    s = session_pulmoscan_real()
    r = interpret(s)
    pdf = gen.generar(s, r, n_reporte="TEST-001")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 10000
