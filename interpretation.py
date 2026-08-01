# -*- coding: utf-8 -*-
"""
Motor de interpretación oscilométrica.

Aplica los criterios del estándar técnico ERS 2020:
  King GG, Bates J, Berger KI, et al. Technical standards for respiratory
  oscillometry. Eur Respir J 2020;55:1900753.
  doi:10.1183/13993003.00753-2019

Flujo de interpretación (Tabla 1 del estándar + PulmoScan guide):
  1. Control de calidad (CoV, coherencia, nº mediciones)
  2. R5 — resistencia total
  3. R5-R20 — dependencia de frecuencia (vía aérea pequeña)
  4. X5 y AX — reactancia y área bajo la curva de reactancia
  5. Fres — frecuencia de resonancia
  6. Patrón ventilatorio (normal / obstructivo / periférico / restrictivo)
  7. Análisis intraciclo (EFL / IFL)
  8. Respuesta broncodilatadora
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models import BreathingParams, OscParameter, OscillometrySession, WithinBreathParams

# ---------------------------------------------------------------------------
# Constantes normativas (ERS 2020)
# ---------------------------------------------------------------------------

#: Límite inferior / superior de normalidad (percentil 5 y 95, z = ±1.645)
Z_LLN: float = -1.645
Z_ULN: float = 1.645

#: Umbrales de respuesta broncodilatadora (ERS 2020, Tabla 1 / Supplementary E2)
BD_R5_THRESHOLD_PCT: float = -40.0    # Disminución ≥ 40 %
BD_X5_THRESHOLD_PCT: float = 50.0     # Aumento ≥ 50 %  (menos negativo)
BD_AX_THRESHOLD_PCT: float = -80.0    # Disminución ≥ 80 %

#: Umbrales de CoV para control de calidad
COV_ADULT_MAX_PCT: float = 10.0
COV_PAED_MAX_PCT: float = 15.0

#: Coherencia mínima recomendada (ERS 2020 no la usa para excluir, pero sí la reporta)
COHERENCE_MIN: float = 0.95

#: Umbral para disociación inspiratoria/espiratoria (EFL / IFL)
#: No hay corte publicado en ERS 2020; se usa un criterio pragmático de ≥ 30%
WITHIN_BREATH_DISSOCIATION_PCT: float = 30.0


# ---------------------------------------------------------------------------
# Estructuras de resultado
# ---------------------------------------------------------------------------

@dataclass
class ParameterResult:
    name: str
    unit: str = ""
    pre: Optional[float] = None
    post: Optional[float] = None
    z_pre: Optional[float] = None
    z_post: Optional[float] = None
    pct_pred_pre: Optional[float] = None
    pct_pred_post: Optional[float] = None
    pre_post_pct: Optional[float] = None
    above_uln_pre: Optional[bool] = None    # resistencias: anormal si > ULN
    below_lln_pre: Optional[bool] = None    # reactancia: anormal si < LLN
    above_uln_post: Optional[bool] = None
    below_lln_post: Optional[bool] = None
    bd_positive: Optional[bool] = None
    bd_threshold: str = ""
    bd_note: str = ""


@dataclass
class QualityResult:
    grade: str = ""             # OK / ACEPTABLE / LIMITADO
    cov_ok: Optional[bool] = None
    coherence_ok: Optional[bool] = None
    n_ok: Optional[bool] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class BDResult:
    positive: bool = False
    r5_change_pct: Optional[float] = None
    x5_change_pct: Optional[float] = None
    ax_change_pct: Optional[float] = None
    r5_positive: Optional[bool] = None
    x5_positive: Optional[bool] = None
    ax_positive: Optional[bool] = None
    text: str = ""
    note_discordance: str = ""  # Si la máquina informó algo distinto


@dataclass
class WithinBreathResult:
    efl_suspected: bool = False   # Expiratory Flow Limitation
    ifl_suspected: bool = False   # Inspiratory Flow Limitation
    r5_insp: Optional[float] = None
    r5_exp: Optional[float] = None
    x5_insp: Optional[float] = None
    x5_exp: Optional[float] = None
    dissociation_pct: Optional[float] = None
    text: str = ""


@dataclass
class PatternResult:
    label: str = "No clasificable"
    subtype: str = ""
    detail: str = ""
    flags: List[str] = field(default_factory=list)


@dataclass
class InterpretationResult:
    quality: QualityResult = field(default_factory=QualityResult)
    params: Dict[str, ParameterResult] = field(default_factory=dict)
    pattern: PatternResult = field(default_factory=PatternResult)
    bd: BDResult = field(default_factory=BDResult)
    within_breath: WithinBreathResult = field(default_factory=WithinBreathResult)
    paediatric: bool = False
    conclusion: str = ""


# ---------------------------------------------------------------------------
# Motor principal
# ---------------------------------------------------------------------------

class OscillometryInterpreter:
    """
    Interpreta una sesión de oscilometría según ERS 2020.

    Métodos estáticos para que puedan usarse aisladamente:
      - quality_check()
      - evaluate_param()
      - evaluate_bd()
      - classify_pattern()
      - analyze_within_breath()
    """

    # ---------------------------------------------------------------- calidad
    @staticmethod
    def quality_check(session: OscillometrySession,
                      paediatric: bool = False) -> QualityResult:
        q = session.quality
        r = QualityResult()
        cov_max = COV_PAED_MAX_PCT if paediatric else COV_ADULT_MAX_PCT

        if q.n_acceptable is not None:
            r.n_ok = q.n_acceptable >= 3
            if not r.n_ok:
                r.notes.append(
                    f"Solo {q.n_acceptable} medición/es aceptable/s; "
                    "se requieren ≥ 3 para interpretación confiable.")

        if q.cov_r5_pct is not None:
            r.cov_ok = q.cov_r5_pct <= cov_max
            if not r.cov_ok:
                r.notes.append(
                    f"CoV de R5 = {q.cov_r5_pct:.1f}% "
                    f"(límite {'pediátrico' if paediatric else 'adulto'}: "
                    f"≤ {cov_max:.0f}%). Variabilidad elevada; interpretar con cautela.")
        else:
            r.notes.append(
                "No se dispone del CoV de R5. "
                "Por convención ERS 2020: ≤ 10% en adultos, ≤ 15% en niños.")

        if q.avg_coherence is not None:
            r.coherence_ok = q.avg_coherence >= COHERENCE_MIN
            if not r.coherence_ok:
                r.notes.append(
                    f"Coherencia promedio = {q.avg_coherence:.2f} "
                    f"(recomendada ≥ {COHERENCE_MIN}). La coherencia no excluye "
                    "mediciones automáticamente (ERS 2020), pero valores bajos "
                    "sugieren artefacto, ruido o mala colaboración.")

        problems = [x for x in (r.n_ok, r.cov_ok, r.coherence_ok)
                    if x is not None and not x]
        if not problems:
            r.grade = "OK"
        elif len(problems) == 1:
            r.grade = "ACEPTABLE"
        else:
            r.grade = "LIMITADO"
            r.notes.append(
                "La calidad técnica es limitada. Los resultados deben "
                "interpretarse con cautela y, si es posible, repetirse.")

        return r

    # ---------------------------------------------------------------- parámetro
    @staticmethod
    def evaluate_param(p: OscParameter) -> ParameterResult:
        """
        Evalúa la normalidad de un parámetro según su z-score o LLN/ULN.

        Para parámetros de resistencia (R5, R20, AX, Fres):
            Anormal si z > +1.645 (por encima del ULN).
        Para reactancia (X5):
            Anormal si z < -1.645 (por debajo del LLN, más negativo).
        Para R5-R20:
            Positivo es lo esperado en niños sanos; anormal si z > +1.645
            (dependencia de frecuencia marcadamente aumentada).
        """
        r = ParameterResult(name=p.name, unit=p.unit)
        r.pre = p.pre
        r.post = p.post
        r.z_pre = p.pre_z
        r.z_post = p.post_z
        r.pct_pred_pre = p.pre_pct_pred
        r.pct_pred_post = p.post_pct_pred
        r.pre_post_pct = p.pre_post_pct
        r.bd_threshold = p.bd_threshold_label

        def _above_uln(z): return z is not None and z > Z_ULN
        def _below_lln(z): return z is not None and z < Z_LLN

        name_up = p.name.upper()

        if "X5" in name_up and "R" not in name_up:
            # Reactancia: anormal si z < LLN (más negativo de lo esperado)
            r.below_lln_pre = _below_lln(p.pre_z)
            r.below_lln_post = _below_lln(p.post_z)
        else:
            # Resistencia, AX, Fres, R5-R20: anormal si z > ULN
            r.above_uln_pre = _above_uln(p.pre_z)
            r.above_uln_post = _above_uln(p.post_z)

        return r

    # -------------------------------------------------------- broncodilatación
    @staticmethod
    def evaluate_bd(session: OscillometrySession) -> BDResult:
        """
        Respuesta broncodilatadora según ERS 2020 (Tabla 1):
          R5:  disminución ≥ 40 %
          X5:  aumento ≥ 50 %   (menos negativo)
          AX:  disminución ≥ 80 %
        """
        r = BDResult()
        params = session.params

        def _pct(p: OscParameter) -> Optional[float]:
            """% de cambio (post-pre)/|pre|*100."""
            if p.pre is None or p.post is None:
                return None
            if p.pre == 0:
                return None
            return (p.post - p.pre) / abs(p.pre) * 100.0

        p_r5 = params.get("R5")
        p_x5 = params.get("X5")
        p_ax = params.get("AX")

        if p_r5 is not None and p_r5.pre is not None and p_r5.post is not None:
            r.r5_change_pct = _pct(p_r5)
            if r.r5_change_pct is not None:
                r.r5_positive = r.r5_change_pct <= BD_R5_THRESHOLD_PCT

        if p_x5 is not None and p_x5.pre is not None and p_x5.post is not None:
            # Para X5 (valor negativo): positivo = menos negativo = diferencia positiva
            # Se calcula como (post - pre) / |pre| * 100; si pre es más negativo,
            # el aumento hacia 0 da valor positivo.
            if p_x5.pre != 0:
                r.x5_change_pct = (p_x5.post - p_x5.pre) / abs(p_x5.pre) * 100.0
            if r.x5_change_pct is not None:
                # Positivo si el cambio es ≥ +50% (menos negativo)
                r.x5_positive = r.x5_change_pct >= BD_X5_THRESHOLD_PCT

        if p_ax is not None and p_ax.pre is not None and p_ax.post is not None:
            r.ax_change_pct = _pct(p_ax)
            if r.ax_change_pct is not None:
                r.ax_positive = r.ax_change_pct <= BD_AX_THRESHOLD_PCT

        positivos = [x for x in (r.r5_positive, r.x5_positive, r.ax_positive)
                     if x is not None]
        r.positive = any(positivos)

        partes = []
        if r.r5_change_pct is not None:
            partes.append(f"R5 {r.r5_change_pct:+.1f}% "
                          f"({'✓' if r.r5_positive else '✗'} umbral < {BD_R5_THRESHOLD_PCT:.0f}%)")
        if r.x5_change_pct is not None:
            partes.append(f"X5 {r.x5_change_pct:+.1f}% "
                          f"({'✓' if r.x5_positive else '✗'} umbral > +{BD_X5_THRESHOLD_PCT:.0f}%)")
        if r.ax_change_pct is not None:
            partes.append(f"AX {r.ax_change_pct:+.1f}% "
                          f"({'✓' if r.ax_positive else '✗'} umbral < {BD_AX_THRESHOLD_PCT:.0f}%)")

        veredicto = "POSITIVA" if r.positive else "NEGATIVA"
        r.text = (f"Respuesta broncodilatadora {veredicto} (criterios ERS 2020: "
                  f"R5 < −40%, X5 > +50%, AX < −80%). {'; '.join(partes)}.")

        return r

    # ------------------------------------------------------------ patrón
    @staticmethod
    def classify_pattern(params: Dict[str, OscParameter]) -> PatternResult:
        """
        Clasificación del patrón según el algoritmo PulmoScan / ERS 2020.

        Usa los valores PRE-BD (basales) y sus z-scores.
        """
        r = PatternResult()

        def z(name) -> Optional[float]:
            p = params.get(name)
            return p.pre_z if p else None

        def val(name) -> Optional[float]:
            p = params.get(name)
            return p.pre if p else None

        z_r5 = z("R5")
        z_r20 = z("R20")
        z_r5r20 = z("R5-R20")
        z_x5 = z("X5")
        z_ax = z("AX")
        z_fres = z("Fres")

        r5_high = z_r5 is not None and z_r5 > Z_ULN
        r20_high = z_r20 is not None and z_r20 > Z_ULN
        r5r20_high = z_r5r20 is not None and z_r5r20 > Z_ULN
        x5_low = z_x5 is not None and z_x5 < Z_LLN   # más negativo de lo normal
        ax_high = z_ax is not None and z_ax > Z_ULN
        fres_high = z_fres is not None and z_fres > Z_ULN

        # Caso especial: todos los parámetros de resistencia por DEBAJO del LLN
        r5_very_low = z_r5 is not None and z_r5 < Z_LLN
        ax_very_low = z_ax is not None and z_ax < Z_LLN
        fres_very_low = z_fres is not None and z_fres < Z_LLN
        x5_very_high = z_x5 is not None and z_x5 > Z_ULN  # menos negativo de lo esperado

        if r5_very_low and ax_very_low and fres_very_low and x5_very_high:
            r.label = "Patrón atípico"
            r.subtype = "Baja impedancia"
            r.detail = (
                "Los parámetros de resistencia (R5, R20) y el área de reactancia (AX) "
                "se encuentran significativamente POR DEBAJO del límite inferior de "
                "normalidad, y la frecuencia de resonancia (Fres) es muy inferior a la "
                "esperada para la edad. La reactancia X5 se aproxima a cero (z > +1,64). "
                "Este patrón puede observarse en estados de hiperinsuflación, en "
                "mediciones con artefacto de fuga, o en ciertos sujetos con compliance "
                "aumentada. Se recomienda revisar la calidad técnica (fuga, posición de "
                "la lengua, sellado de mejillas) y correlacionar con el cuadro clínico "
                "antes de emitir una interpretación definitiva."
            )
            r.flags.append("Verificar calidad técnica: patrón de baja impedancia inusual.")
            return r

        if not any([r5_high, r20_high, r5r20_high, x5_low, ax_high, fres_high]):
            r.label = "Normal"
            r.detail = (
                "Todos los parámetros oscilométricos principales se encuentran dentro "
                "de los límites de referencia (z-score entre −1,645 y +1,645)."
            )
            return r

        # Obstructivo puro con componente central (R20 alto, R5-R20 normal)
        if r5_high and r20_high and not r5r20_high and (x5_low or ax_high):
            r.label = "Obstructivo"
            r.subtype = "Con componente de vía aérea central"
            r.detail = (
                "↑ R5, ↑ R20, R5-R20 normal, ↑ AX / X5 más negativo. "
                "La elevación proporcional de R5 y R20 con R5-R20 conservado sugiere "
                "obstrucción en vía aérea central y periférica sin marcada "
                "heterogeneidad adicional de la vía pequeña."
            )

        # Obstrucción periférica aislada (vía aérea pequeña)
        elif not r20_high and r5r20_high and (x5_low or ax_high):
            r.label = "Obstructivo"
            r.subtype = "Periférico / vía aérea pequeña"
            r.detail = (
                "R20 normal, ↑ R5-R20, ↑ AX / X5 más negativo. "
                "Patrón de obstrucción periférica con resistencia central conservada. "
                "Frecuentemente la presentación más precoz de asma y EPOC; "
                "la espirometría puede ser normal en esta etapa."
            )

        # Obstructivo general (R5 alto, puede o no tener R5-R20)
        elif r5_high and (x5_low or ax_high or fres_high):
            r.label = "Obstructivo"
            r.subtype = "General"
            r.detail = (
                "↑ R5, ↑ AX y/o X5 más negativo. "
                "Patrón obstructivo con aumento de la resistencia total y/o "
                "heterogeneidad ventilatoria."
            )

        # Restrictivo / de vía aérea periférica con predominio de reactancia
        elif not r5_high and x5_low and ax_high:
            r.label = "Restrictivo / alteración de reactancia"
            r.subtype = "Reactancia predominante"
            r.detail = (
                "R5 normal o levemente elevado, R5-R20 normal, X5 marcadamente "
                "negativo y/o AX elevado. Puede verse en restricción pulmonar "
                "(fibrosis, ILD), hiperinsuflación dinámica severa, o en ciertos "
                "estadios de obstrucción severa con cierre de vía aérea pequeña."
            )

        # Patrón mixto / combinado
        elif r5_high and r5r20_high and x5_low and ax_high:
            r.label = "Obstructivo mixto"
            r.subtype = "Central y periférico"
            r.detail = (
                "↑ R5, ↑ R20, ↑ R5-R20, X5 más negativo, ↑ AX. "
                "Obstrucción combinada de vía aérea central y periférica con "
                "marcada heterogeneidad ventilatoria."
            )

        # Solo R5-R20 elevado sin otros hallazgos prominentes
        elif r5r20_high and not r5_high:
            r.label = "Alteración de vía aérea pequeña"
            r.subtype = "Dependencia de frecuencia aumentada"
            r.detail = (
                "↑ R5-R20 con R5 y R20 dentro de límites. "
                "Patrón de dependencia de frecuencia aumentada que indica "
                "heterogeneidad en la vía aérea pequeña."
            )

        else:
            r.label = "Patrón mixto"
            r.detail = (
                "Combinación de hallazgos que no encaja en un patrón único. "
                "Correlacionar con historial clínico y otros estudios funcionales."
            )

        # Banderas adicionales
        if fres_high:
            r.flags.append(
                f"Fres elevado (z > +1,645): la frecuencia de resonancia alta "
                "indica predominio del componente elástico (aumento de rigidez).")
        if ax_high and not r5_high:
            r.flags.append(
                "AX elevado con R5 normal: la heterogeneidad ventilatoria puede "
                "preceder a la elevación de la resistencia y es un signo sensible "
                "de enfermedad pequeñovía aérea incipiente.")

        return r

    # -------------------------------------------------- análisis intraciclo
    @staticmethod
    def analyze_within_breath(pre: WithinBreathParams,
                              post: WithinBreathParams = None,
                              paediatric: bool = False) -> WithinBreathResult:
        """
        Detección de EFL e IFL a partir de la disociación Rexp/Rinsp y Xexp/Xinsp.

        ERS 2020 no establece un umbral numérico formal para la disociación
        inspiratoria/espiratoria. PulmoScan y la literatura clínica (Dellacà 2004)
        usan "marcadamente mayor" para EFL. Se aplica un criterio pragmático
        de ≥ 30% de diferencia entre Rexp5 y Rinsp5.
        """
        r = WithinBreathResult()
        r.r5_insp = pre.r_insp_5
        r.r5_exp = pre.r_exp_5
        r.x5_insp = pre.x_insp_5
        r.x5_exp = pre.x_exp_5

        if pre.r_insp_5 is not None and pre.r_exp_5 is not None:
            dif = pre.r_exp_5 - pre.r_insp_5
            base = abs(pre.r_insp_5) if pre.r_insp_5 != 0 else 1
            r.dissociation_pct = dif / base * 100.0

            if r.dissociation_pct >= WITHIN_BREATH_DISSOCIATION_PCT:
                r.efl_suspected = True
                r.text = (
                    f"Rexp5 ({pre.r_exp_5:.2f}) > Rinsp5 ({pre.r_insp_5:.2f}): "
                    f"diferencia de {r.dissociation_pct:.0f}%, sugestivo de "
                    "limitación al flujo espiratorio (EFL). En el contexto "
                    "clínico adecuado puede indicar EPOC, asma severa o "
                    "hiperinsuflación dinámica.")
            elif r.dissociation_pct <= -WITHIN_BREATH_DISSOCIATION_PCT:
                r.ifl_suspected = True
                r.text = (
                    f"Rinsp5 ({pre.r_insp_5:.2f}) > Rexp5 ({pre.r_exp_5:.2f}): "
                    f"diferencia de {abs(r.dissociation_pct):.0f}%, sugestivo de "
                    "limitación al flujo inspiratorio (IFL). Puede verse en "
                    "restricción de vía aérea superior, ILD o enfermedad de la "
                    "pared torácica.")
            else:
                r.text = (
                    f"Sin disociación significativa entre parámetros "
                    f"inspiratorios y espiratorios (Rinsp5 {pre.r_insp_5:.2f}, "
                    f"Rexp5 {pre.r_exp_5:.2f}; diferencia {r.dissociation_pct:.0f}%)."
                )
        else:
            r.text = "No se dispone de parámetros intraciclo detallados."

        return r

    # --------------------------------------------------- función principal
    def interpret(self, session: OscillometrySession) -> InterpretationResult:
        result = InterpretationResult()
        result.paediatric = session.patient.is_paediatric

        # 1. Calidad
        result.quality = self.quality_check(session, result.paediatric)

        # 2. Parámetros individuales
        for name, p in session.params.items():
            result.params[name] = self.evaluate_param(p)

        # 3. Patrón ventilatorio (sobre valores pre-BD)
        result.pattern = self.classify_pattern(session.params)

        # 4. Respuesta broncodilatadora
        if session.has_post:
            result.bd = self.evaluate_bd(session)

        # 5. Análisis intraciclo
        result.within_breath = self.analyze_within_breath(
            session.pre_within,
            session.post_within if session.has_post else None,
            result.paediatric,
        )

        # 6. Conclusión integrada
        result.conclusion = self._build_conclusion(result, session)

        return result

    def _build_conclusion(self, r: InterpretationResult,
                          s: OscillometrySession) -> str:
        partes = []

        # Calidad
        if r.quality.grade == "LIMITADO":
            partes.append("Calidad técnica limitada: la interpretación debe "
                          "tomarse con cautela.")

        # Patrón
        pat = r.pattern.label
        if r.pattern.subtype:
            pat += f" ({r.pattern.subtype.lower()})"
        partes.append(f"Patrón oscilométrico basal: {pat}.")

        # BD
        if s.has_post:
            veredicto = "positiva" if r.bd.positive else "negativa"
            partes.append(f"Respuesta broncodilatadora {veredicto} "
                          "(criterios ERS 2020).")

        # Flujo intraciclo
        if r.within_breath.efl_suspected:
            partes.append("Datos intraciclo sugestivos de limitación al "
                          "flujo espiratorio (EFL).")
        elif r.within_breath.ifl_suspected:
            partes.append("Datos intraciclo sugestivos de limitación al "
                          "flujo inspiratorio (IFL).")

        return " ".join(partes)


# ---------------------------------------------------------------------------
# API de conveniencia
# ---------------------------------------------------------------------------

def interpret(session: OscillometrySession) -> InterpretationResult:
    return OscillometryInterpreter().interpret(session)
