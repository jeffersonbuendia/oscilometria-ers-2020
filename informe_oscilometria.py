# -*- coding: utf-8 -*-
"""
Generador de informe de oscilometría en PDF.

Referencia principal:
  King GG, Bates J, Berger KI, et al. Technical standards for respiratory
  oscillometry. Eur Respir J 2020;55:1900753.
  doi:10.1183/13993003.00753-2019

Referencia secundaria:
  PulmoScan Interpretation Guide (Biswas R, Cognita Labs, 2025).
  https://pulmoscan.cognitalabs.com/how-to-interpret-pulmoscan-oscillometry-data/
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from interpretation import InterpretationResult, BDResult
from models import OscillometrySession


# ---------------------------------------------------------------------------
# Colores institucionales
# ---------------------------------------------------------------------------

AZUL = colors.HexColor("#1F4E79")
AZUL_CLARO = colors.HexColor("#EBF3FB")
GRIS = colors.HexColor("#F5F5F5")
GRIS_TXT = colors.HexColor("#555555")
ROJO = colors.HexColor("#8B0000")
ROJO_FONDO = colors.HexColor("#FDEDED")
AMBAR = colors.HexColor("#7B4F00")
AMBAR_FONDO = colors.HexColor("#FFF6E0")
VERDE = colors.HexColor("#1A6B1A")
VERDE_FONDO = colors.HexColor("#EAF4EA")
BORDE = colors.HexColor("#B0B0B0")

# Tabla de parámetros normativos aplicados
PARAMETROS_APLICADOS: List[Tuple[str, str, str]] = [
    ("Normalidad",
     "z-score entre −1,645 y +1,645 (percentil 5-95)",
     "ERS 2020 [1]; PulmoScan Guide [2]"),
    ("Parámetros de resistencia (R5, R20, AX, Fres)",
     "Anormales si z > +1,645 (por encima del ULN)",
     "ERS 2020 [1]"),
    ("Reactancia (X5)",
     "Anormal si z < −1,645 (más negativo que el LLN)",
     "ERS 2020 [1]"),
    ("R5-R20 (dependencia de frecuencia)",
     "Anormal si z > +1,645; indica obstrucción de vía aérea pequeña",
     "ERS 2020 [1]"),
    ("Respuesta broncodilatadora — R5",
     "Disminución ≥ 40% respecto al basal",
     "ERS 2020 Tabla 1 [1]; ALA Toolkit [3]"),
    ("Respuesta broncodilatadora — X5",
     "Aumento ≥ 50% (menos negativo) respecto al basal",
     "ERS 2020 Tabla 1 [1]; ALA Toolkit [3]"),
    ("Respuesta broncodilatadora — AX",
     "Disminución ≥ 80% respecto al basal",
     "ERS 2020 Tabla 1 [1]; ALA Toolkit [3]"),
    ("Control de calidad — CoV R5",
     "≤ 10% en adultos; ≤ 15% en niños",
     "ERS 2020 [1]; ALA Toolkit [3]"),
    ("Control de calidad — coherencia",
     "Preferiblemente ≥ 0,95; no se usa como criterio de exclusión único",
     "ERS 2020 [1]"),
    ("Mínimo de mediciones",
     "≥ 3 mediciones aceptables (idealmente ≥ 5)",
     "ERS 2020 [1]; ALA Toolkit [3]"),
    ("EFL (Limitación flujo espiratorio)",
     "Rexp5 marcadamente > Rinsp5 (umbral pragmático: ≥ 30%)",
     "Dellacà 2004 [4]; PulmoScan Guide [2]"),
    ("IFL (Limitación flujo inspiratorio)",
     "Rinsp5 marcadamente > Rexp5",
     "PulmoScan Guide [2]"),
    ("Ecuación de referencia recomendada",
     "Seleccionar la más adecuada para la población del paciente",
     "ERS 2020 [1]; Gochicoa-Rangel 2025 [5]"),
]


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class InformeOscilometria:
    """
    Genera el informe de oscilometría en PDF.

    Uso:
        gen = InformeOscilometria(
            institucion="SALUD ES VIVIR IPS",
            firmante="Jefferson Antonio Buendía",
            credenciales="MD · Neumólogo Pediatra",
        )
        pdf_bytes = gen.generar(session, result, conclusion="...")
    """

    def __init__(self, institucion: str = "", laboratorio: str = "",
                 ciudad: str = "", registro_lab: str = "",
                 firmante: str = "", credenciales: str = ""):
        self.institucion = institucion
        self.laboratorio = laboratorio
        self.ciudad = ciudad
        self.registro_lab = registro_lab
        self.firmante = firmante
        self.credenciales = credenciales
        self._estilos = self._build_styles()

    # ---------------------------------------------------------------- estilos
    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        e: Dict[str, ParagraphStyle] = {}
        e["cuerpo"] = ParagraphStyle(
            "cuerpo", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.4, leading=12, alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#1A1A1A"))
        e["seccion"] = ParagraphStyle(
            "seccion", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=11, leading=14, spaceBefore=10, spaceAfter=4,
            textColor=AZUL)
        e["subseccion"] = ParagraphStyle(
            "subseccion", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.8, leading=12, spaceBefore=6, spaceAfter=2,
            textColor=AZUL)
        e["nota"] = ParagraphStyle(
            "nota", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=7.2, leading=9.4, alignment=TA_JUSTIFY, textColor=GRIS_TXT)
        e["celda"] = ParagraphStyle(
            "celda", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.4, leading=9.2)
        e["celda_c"] = ParagraphStyle(
            "celda_c", parent=e["celda"], alignment=TA_CENTER)
        e["alerta"] = ParagraphStyle(
            "alerta", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=11.4, alignment=TA_JUSTIFY)
        e["firma"] = ParagraphStyle(
            "firma", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=11, alignment=TA_CENTER)
        e["conclusion"] = ParagraphStyle(
            "conclusion", parent=e["cuerpo"], fontSize=8.6, leading=12.4,
            spaceAfter=3)
        return e

    # ---------------------------------------------------------------- helpers
    def _ancho(self) -> float:
        return LETTER[0] - 30 * mm

    def _tabla(self, filas, anchos, extra=None, cab=True, fill=None) -> Table:
        t = Table(filas, colWidths=anchos, repeatRows=1 if cab else 0)
        cmds = [
            ("GRID", (0, 0), (-1, -1), 0.35, BORDE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.4),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
        ]
        if cab:
            cmds += [
                ("BACKGROUND", (0, 0), (-1, 0), fill or AZUL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.0),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ]
        if extra:
            cmds += extra
        t.setStyle(TableStyle(cmds))
        return t

    def _panel(self, titulo, cuerpo, col_text, col_fill) -> Table:
        txt = (f'<font color="#{col_text.hexval()[2:]}">'
               f"<b>{titulo}</b></font>  {cuerpo}")
        t = Table([[Paragraph(txt, self._estilos["alerta"])]],
                  colWidths=[self._ancho()])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), col_fill),
            ("BOX", (0, 0), (-1, -1), 0.9, col_text),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def _titulo(self, texto) -> List[Any]:
        p = Paragraph(texto, self._estilos["seccion"])
        linea = Table([[""]], colWidths=[self._ancho()], rowHeights=[1.0])
        linea.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.9, AZUL),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return [p, linea, Spacer(1, 4)]

    def _blank(self, s=6) -> Spacer:
        return Spacer(1, s)

    def _cell(self, txt, bold=False, center=False, color=None) -> Paragraph:
        st = ParagraphStyle(
            "tmp", parent=self._estilos["celda"],
            fontName="Helvetica-Bold" if bold else "Helvetica",
            alignment=TA_CENTER if center else TA_LEFT,
            textColor=color or colors.black)
        return Paragraph(str(txt) if txt is not None else "—", st)

    # ---------------------------------------------------------------- render
    def generar(self, session: OscillometrySession,
                result: InterpretationResult,
                conclusion: str = "",
                n_reporte: str = "",
                pdf_original: Optional[bytes] = None) -> bytes:
        buf = io.BytesIO()
        ancho, alto = LETTER
        mx, mt, mb = 15 * mm, 26 * mm, 18 * mm

        doc = BaseDocTemplate(
            buf, pagesize=LETTER,
            leftMargin=mx, rightMargin=mx, topMargin=mt, bottomMargin=mb,
            title=f"Informe oscilometría — {session.patient.name}",
            author=self.firmante or self.institucion,
            subject="Oscilometría de impulso — ERS 2020",
        )
        marco = Frame(mx, mb, ancho - 2 * mx, alto - mt - mb,
                      id="principal", showBoundary=0)
        doc.addPageTemplates([PageTemplate(
            id="std", frames=[marco],
            onPage=lambda c, d: self._decorate(c, d, session, n_reporte))])

        story: List[Any] = []
        self._alertas(story, result)
        self._paciente(story, session)
        self._calidad(story, session, result)
        self._parametros(story, session, result)
        self._intraciclo(story, session, result)
        self._bd(story, session, result)
        self._interpretacion(story, result)
        self._conclusion(story, result, conclusion)
        self._firma(story, session, n_reporte)
        self._normativa(story)

        doc.build(story)
        pdf = buf.getvalue()

        if pdf_original:
            pdf = self._merge(pdf, pdf_original)
        return pdf

    # ---------------------------------------------------------------- decorate
    def _decorate(self, canv, doc, session, n_reporte):
        canv.saveState()
        ancho, alto = LETTER
        mx = 15 * mm
        canv.setFont("Helvetica-Bold", 13)
        canv.setFillColor(AZUL)
        canv.drawString(mx, alto - 14 * mm, self.institucion or "")
        canv.setFont("Helvetica", 7.8)
        canv.setFillColor(GRIS_TXT)
        sub = self.laboratorio
        if self.registro_lab:
            sub += f"  ·  {self.registro_lab}"
        canv.drawString(mx, alto - 18.4 * mm, sub)
        canv.setFont("Helvetica-Bold", 8.2)
        canv.setFillColor(colors.HexColor("#333333"))
        canv.drawRightString(ancho - mx, alto - 14 * mm,
                             "INFORME DE OSCILOMETRÍA")
        canv.setFont("Helvetica", 7.2)
        canv.setFillColor(GRIS_TXT)
        canv.drawRightString(ancho - mx, alto - 18 * mm,
                             f"Fecha: {session.patient.exam_date}")
        if n_reporte:
            canv.drawRightString(ancho - mx, alto - 21.4 * mm,
                                 f"Informe {n_reporte}")
        canv.setStrokeColor(AZUL)
        canv.setLineWidth(1.0)
        canv.line(mx, alto - 23 * mm, ancho - mx, alto - 23 * mm)
        canv.setStrokeColor(AZUL)
        canv.setLineWidth(0.5)
        canv.line(mx, 13 * mm, ancho - mx, 13 * mm)
        canv.setFont("Helvetica", 6.4)
        canv.setFillColor(colors.HexColor("#888888"))
        izq = " · ".join(x for x in (self.laboratorio, self.institucion,
                                     self.ciudad) if x)
        canv.drawString(mx, 10 * mm, izq)
        canv.drawRightString(ancho - mx, 10 * mm, f"Página {doc.page}")
        canv.drawString(mx, 7.2 * mm,
                        "Interpretación conforme a ERS 2020 (Eur Respir J 2020;55:1900753)")
        canv.restoreState()

    # ---------------------------------------------------------------- secciones
    def _alertas(self, story, result):
        if result.quality.grade == "LIMITADO":
            story.append(self._panel(
                "CALIDAD TÉCNICA LIMITADA.",
                " ".join(result.quality.notes),
                ROJO, ROJO_FONDO))
            story.append(self._blank(6))

        if "atípico" in result.pattern.label.lower():
            story.append(self._panel(
                "PATRÓN ATÍPICO — VERIFICAR CALIDAD.",
                result.pattern.detail[:200],
                AMBAR, AMBAR_FONDO))
            story.append(self._blank(6))

    def _paciente(self, story, session):
        p = session.patient
        w = self._ancho()
        filas = [
            [self._cell("Nombre:", bold=True), self._cell(p.name),
             self._cell("ID:", bold=True), self._cell(p.patient_id)],
            [self._cell("Sexo biológico:", bold=True), self._cell(p.gender),
             self._cell("Edad:", bold=True),
             self._cell(f"{p.age_years} años" if p.age_years else "—")],
            [self._cell("Talla / Peso:", bold=True),
             self._cell(f"{p.height_cm} cm / {p.weight_kg} kg" if p.height_cm else "—"),
             self._cell("Tabaquismo:", bold=True), self._cell(p.smoking_history)],
            [self._cell("Etnia:", bold=True), self._cell(p.ethnicity),
             self._cell("Fecha:", bold=True), self._cell(p.exam_date)],
            [self._cell("Ecuación de referencia:", bold=True),
             self._cell(p.reference_equation),
             self._cell("Operador:", bold=True), self._cell(p.operator)],
            [self._cell("Sesión:", bold=True),
             self._cell(p.session_id),
             self._cell("Notas:", bold=True), self._cell(p.notes or "—")],
        ]
        estilos = [("BACKGROUND", (0, 0), (0, -1), AZUL_CLARO),
                   ("BACKGROUND", (2, 0), (2, -1), AZUL_CLARO)]
        story.extend(self._titulo("1.  DATOS DEL PACIENTE"))
        story.append(self._tabla(
            filas, [w * .18, w * .32, w * .16, w * .34],
            extra=estilos, cab=False))
        story.append(self._blank(3))
        story.append(Paragraph(
            "El sexo biológico determina la ecuación de referencia. La ecuación "
            "seleccionada debe ser la más adecuada para la población del paciente "
            "(ERS 2020; Gochicoa-Rangel 2025).",
            self._estilos["nota"]))

    def _calidad(self, story, session, result):
        q = session.quality
        r = result.quality
        w = self._ancho()
        filas = [
            ["Indicador", "Valor", "Umbral", "Resultado"],
            ["N° mediciones aceptables",
             str(q.n_acceptable) if q.n_acceptable else "—",
             "≥ 3",
             "✓ OK" if r.n_ok else ("✗ Insuf." if r.n_ok is False else "—")],
            ["CoV R5 (%)",
             f"{q.cov_r5_pct:.1f}%" if q.cov_r5_pct else (q.cov_pre_r5 or "—"),
             "≤ 10% adultos / ≤ 15% niños",
             "✓ OK" if r.cov_ok else ("✗ Elevado" if r.cov_ok is False else "—")],
            ["Coherencia promedio",
             f"{q.avg_coherence:.2f}" if q.avg_coherence else "—",
             "≥ 0,95 (recomendado)",
             "✓ OK" if r.coherence_ok else ("⚠ Baja" if r.coherence_ok is False else "—")],
            ["Grado global", "", "", r.grade],
        ]
        col_grado = VERDE if r.grade == "OK" else (
            AMBAR if r.grade == "ACEPTABLE" else ROJO)
        estilos = [
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("TEXTCOLOR", (3, 4), (3, 4), col_grado),
            ("FONTNAME", (3, 4), (3, 4), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ]
        story.extend(self._titulo("2.  CONTROL DE CALIDAD"))
        story.append(self._tabla(filas, [w * .38, w * .18, w * .28, w * .16],
                                 extra=estilos))
        for nota in r.notes:
            story.append(Paragraph(f"— {nota}", self._estilos["nota"]))

    def _parametros(self, story, session, result):
        w = self._ancho()
        has_post = session.has_post
        if has_post:
            enc = ["Parámetro", "Referencia", "Pre-BD", "Z pre",
                   "% pred.", "Post-BD", "Z post", "% pred.", "Cambio %"]
            anchos = [w*.18, w*.10, w*.10, w*.09, w*.09,
                      w*.10, w*.09, w*.09, w*.16]
        else:
            enc = ["Parámetro", "Referencia", "Pre-BD", "Z-score", "% pred."]
            anchos = [w*.26, w*.18, w*.18, w*.18, w*.20]

        filas = [enc]
        estilos = [("ALIGN", (1, 1), (-1, -1), "CENTER"),
                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS])]

        ORDER = ["R5", "R20", "R5-R20", "X5", "AX", "Fres"]
        for i, name in enumerate(ORDER, start=1):
            pr = result.params.get(name)
            p = session.params.get(name)
            if not p:
                continue

            def _fv(v): return f"{v:.2f}".replace(".", ",") if v is not None else "—"
            def _fz(v): return f"{v:+.2f}".replace(".", ",") if v is not None else "—"
            def _fp(v): return f"{v:.0f} %" if v is not None else "—"

            anormal_pre = (
                (pr.above_uln_pre is True) or (pr.below_lln_pre is True)
            )
            anormal_post = (
                (pr.above_uln_post is True) or (pr.below_lln_post is True)
            )
            col_pre = ROJO if anormal_pre else colors.black
            col_post = ROJO if anormal_post else colors.black

            fila = [
                f"{name} ({p.unit})",
                _fv(p.reference),
                _fv(p.pre),
                _fz(p.pre_z),
                _fp(p.pre_pct_pred),
            ]
            if has_post:
                fila += [
                    _fv(p.post),
                    _fz(p.post_z),
                    _fp(p.post_pct_pred),
                    (f"{p.pre_post_pct:+.0f} %".replace(".", ",")
                     if p.pre_post_pct is not None else "—"),
                ]
            filas.append(fila)

            col_idx_pre = 2
            col_idx_post = 5 if has_post else None
            if anormal_pre:
                estilos += [("TEXTCOLOR", (col_idx_pre, i), (col_idx_pre + 2, i), col_pre),
                            ("FONTNAME", (col_idx_pre, i), (col_idx_pre + 2, i), "Helvetica-Bold")]
            if has_post and anormal_post:
                estilos += [("TEXTCOLOR", (col_idx_post, i), (col_idx_post + 2, i), col_post),
                            ("FONTNAME", (col_idx_post, i), (col_idx_post + 2, i), "Helvetica-Bold")]

        story.extend(self._titulo("3.  PARÁMETROS OSCILOMÉTRICOS"))
        story.append(self._tabla(filas, anchos, extra=estilos))
        story.append(self._blank(3))
        story.append(Paragraph(
            "Rojo: valor fuera del rango de normalidad (z < −1,645 o z > +1,645). "
            "El porcentaje del predicho se informa por compatibilidad; "
            "la normalidad se decide por z-score, no por cortes fijos (ERS 2020). "
            "R5: resistencia total (↑ = obstrucción). "
            "R5-R20: dependencia de frecuencia (↑ = vía aérea pequeña). "
            "X5: reactancia a 5 Hz (más negativo = mayor rigidez/heterogeneidad). "
            "AX: área bajo la curva de reactancia (↑ = mayor disfunción). "
            "Fres: frecuencia de resonancia (↑ = mayor elastancia).",
            self._estilos["nota"]))

    def _intraciclo(self, story, session, result):
        story.extend(self._titulo("4.  ANÁLISIS INTRACICLO (INSPIRATORIO / ESPIRATORIO)"))
        wb_pre = session.pre_within
        wb_post = session.post_within
        bp_pre = session.pre_breathing
        bp_post = session.post_breathing
        w = self._ancho()

        def _fv(v): return f"{v:.2f}".replace(".", ",") if v is not None else "—"
        def _fvv(v, u=""): return f"{v:.1f} {u}".strip() if v is not None else "—"

        # Parámetros respiratorios
        filas_bp = [
            ["Parámetro", "Pre-BD", "Post-BD"],
            ["Volumen corriente (mL)",
             _fvv(bp_pre.tidal_volume_ml), _fvv(bp_post.tidal_volume_ml)],
            ["Frecuencia respiratoria (rpm)",
             _fvv(bp_pre.respiratory_rate_cpm), _fvv(bp_post.respiratory_rate_cpm)],
            ["Tiempo inspiratorio (s)",
             _fvv(bp_pre.inhalation_time_s), _fvv(bp_post.inhalation_time_s)],
            ["Tiempo espiratorio (s)",
             _fvv(bp_pre.exhalation_time_s), _fvv(bp_post.exhalation_time_s)],
            ["Flujo inspiratorio medio (mL/s)",
             _fvv(bp_pre.mean_inspiratory_flow_ml_s),
             _fvv(bp_post.mean_inspiratory_flow_ml_s)],
            ["Coherencia",
             _fvv(bp_pre.coherence), _fvv(bp_post.coherence)],
        ]
        estilos_bp = [("ALIGN", (1, 1), (-1, -1), "CENTER"),
                      ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS])]
        story.append(Paragraph("Parámetros ventilatorios durante la prueba",
                               self._estilos["subseccion"]))
        story.append(self._tabla(filas_bp, [w * .5, w * .25, w * .25],
                                 extra=estilos_bp))
        story.append(self._blank(6))

        # Tabla de resistencias insp/esp
        has_wb = (wb_pre.r_insp_5 is not None or wb_pre.r_exp_5 is not None)
        if has_wb:
            story.append(Paragraph("Resistencia y reactancia inspiratoria / espiratoria (Pre-BD)",
                                   self._estilos["subseccion"]))
            filas_wb = [
                ["Hz", "Rinsp", "Rexp", "Xinsp", "Xexp"],
            ]
            freqs = [("5", "r_insp_5", "r_exp_5", "x_insp_5", "x_exp_5"),
                     ("10", "r_insp_10", "r_exp_10", "x_insp_10", "x_exp_10"),
                     ("15", "r_insp_15", "r_exp_15", "x_insp_15", "x_exp_15"),
                     ("20", "r_insp_20", "r_exp_20", "x_insp_20", "x_exp_20"),
                     ("25", "r_insp_25", "r_exp_25", "x_insp_25", "x_exp_25"),
                     ("30", "r_insp_30", "r_exp_30", "x_insp_30", "x_exp_30")]
            for f, ri, re, xi, xe in freqs:
                filas_wb.append([
                    f,
                    _fv(getattr(wb_pre, ri)),
                    _fv(getattr(wb_pre, re)),
                    _fv(getattr(wb_pre, xi)),
                    _fv(getattr(wb_pre, xe)),
                ])
            estilos_wb = [("ALIGN", (1, 1), (-1, -1), "CENTER"),
                          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS])]
            story.append(self._tabla(
                filas_wb,
                [w * .1, w * .225, w * .225, w * .225, w * .225],
                extra=estilos_wb))
            story.append(self._blank(4))

        # Resultado del análisis intraciclo
        wb_result = result.within_breath
        if wb_result.efl_suspected:
            story.append(self._panel(
                "LIMITACIÓN AL FLUJO ESPIRATORIO (EFL) — sugestiva.",
                wb_result.text, AMBAR, AMBAR_FONDO))
        elif wb_result.ifl_suspected:
            story.append(self._panel(
                "LIMITACIÓN AL FLUJO INSPIRATORIO (IFL) — sugestiva.",
                wb_result.text, AZUL, AZUL_CLARO))
        else:
            story.append(Paragraph(wb_result.text, self._estilos["cuerpo"]))
        story.append(self._blank(3))
        story.append(Paragraph(
            "ERS 2020 no establece un umbral numérico formal para la disociación "
            "inspiratoria/espiratoria. Se aplica un criterio pragmático de ≥ 30% "
            "de diferencia entre Rexp5 y Rinsp5 (Dellacà 2004). "
            "La frecuencia respiratoria durante la prueba y el volumen corriente "
            "influyen en los valores oscilométricos; tasas muy elevadas pueden "
            "artefactualizar la medición a 5 Hz.",
            self._estilos["nota"]))

    def _bd(self, story, session, result):
        if not session.has_post:
            return
        story.extend(self._titulo("5.  RESPUESTA BRONCODILATADORA"))
        w = self._ancho()
        bd = result.bd

        def _c(v): return f"{v:+.1f} %".replace(".", ",") if v is not None else "—"

        filas = [
            ["Parámetro", "Pre-BD", "Post-BD", "Cambio %",
             f"Umbral ERS 2020", "Resultado"],
        ]
        datos = [
            ("R5", session.params.get("R5"),
             bd.r5_change_pct, bd.r5_positive, "< −40 %"),
            ("X5", session.params.get("X5"),
             bd.x5_change_pct, bd.x5_positive, "> +50 %"),
            ("AX", session.params.get("AX"),
             bd.ax_change_pct, bd.ax_positive, "< −80 %"),
        ]
        estilos = [("ALIGN", (1, 1), (-1, -1), "CENTER"),
                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS])]
        for i, (name, p, chg, pos, thresh) in enumerate(datos, start=1):
            pre = f"{p.pre:.2f}".replace(".", ",") if p and p.pre is not None else "—"
            post = f"{p.post:.2f}".replace(".", ",") if p and p.post is not None else "—"
            veredicto = "✓ Positiva" if pos else ("✗ Negativa" if pos is False else "—")
            filas.append([name, pre, post, _c(chg), thresh, veredicto])
            col = VERDE if pos else (ROJO if pos is False else GRIS_TXT)
            estilos.append(("TEXTCOLOR", (5, i), (5, i), col))
            estilos.append(("FONTNAME", (5, i), (5, i), "Helvetica-Bold"))

        story.append(self._tabla(
            filas, [w * .10, w * .12, w * .12, w * .16, w * .18, w * .32],
            extra=estilos))
        story.append(self._blank(6))

        col = VERDE if bd.positive else AMBAR
        fondo = VERDE_FONDO if bd.positive else AMBAR_FONDO
        veredicto = "POSITIVA" if bd.positive else "NEGATIVA"
        story.append(self._panel(
            f"RESPUESTA BRONCODILATADORA {veredicto}.",
            bd.text, col, fondo))
        story.append(self._blank(3))
        story.append(Paragraph(
            "Criterios ERS 2020 (Tabla 1): R5 disminución ≥ 40%, "
            "X5 aumento ≥ 50% (menos negativo), AX disminución ≥ 80%. "
            "El cambio se expresa como porcentaje respecto al valor basal "
            "absoluto: (post − pre) / |pre| × 100. "
            "La respuesta broncodilatadora en oscilometría es más sensible "
            "que en espirometría para detectar cambios en la vía aérea pequeña.",
            self._estilos["nota"]))

    def _interpretacion(self, story, result):
        story.extend(self._titulo("6.  INTERPRETACIÓN"))
        pat = result.pattern

        story.append(Paragraph("6.1  Patrón oscilométrico",
                               self._estilos["subseccion"]))
        txt = (f"<b>{pat.label.upper()}</b>"
               + (f" — {pat.subtype}" if pat.subtype else "")
               + f". {pat.detail}")
        story.append(Paragraph(txt, self._estilos["cuerpo"]))
        for f in pat.flags:
            story.append(Paragraph(f"— {f}", self._estilos["cuerpo"]))

        story.append(self._blank(4))
        story.append(Paragraph("6.2  Análisis intraciclo",
                               self._estilos["subseccion"]))
        story.append(Paragraph(result.within_breath.text,
                               self._estilos["cuerpo"]))

    def _conclusion(self, story, result, conclusion_editada=""):
        story.extend(self._titulo("7.  CONCLUSIÓN"))
        conclusion_final = conclusion_editada.strip() or result.conclusion

        celdas = []
        for i, punto in enumerate(conclusion_final.split(". "), start=1):
            punto = punto.strip()
            if not punto:
                continue
            if not punto.endswith("."):
                punto += "."
            celdas.append([Paragraph(
                f"<b>{i}.</b>  {punto}", self._estilos["conclusion"])])

        t = Table(celdas, colWidths=[self._ancho()])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), VERDE_FONDO),
            ("BOX", (0, 0), (-1, -1), 0.8, VERDE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(self._blank(3))
        story.append(Paragraph(
            "La interpretación de la oscilometría debe complementarse con la "
            "valoración clínica, la espirometría y otros estudios cuando sea "
            "necesario. La oscilometría no debe usarse como prueba diagnóstica "
            "única (ALA Toolkit 2026).",
            self._estilos["nota"]))

    def _firma(self, story, session, n_reporte):
        w = self._ancho()
        story.append(Spacer(1, 18))
        firma_izq = [
            Paragraph(f"<b>{self.firmante}</b>", self._estilos["firma"]),
            Paragraph(self.credenciales, self._estilos["firma"]),
            Paragraph(self.laboratorio, self._estilos["firma"]),
            Paragraph(self.institucion, self._estilos["firma"]),
        ]
        firma_der = [
            Paragraph(self.ciudad, self._estilos["firma"]),
            Paragraph(f"Fecha: {session.patient.exam_date}", self._estilos["firma"]),
        ]
        if n_reporte:
            firma_der.append(Paragraph(f"N.° {n_reporte}", self._estilos["firma"]))
        t = Table([[firma_izq, firma_der]], colWidths=[w * .5, w * .5])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.7, colors.HexColor("#333333")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(KeepTogether(t))

    def _normativa(self, story):
        w = self._ancho()
        filas = [["Parámetro / criterio", "Valor aplicado", "Fuente"]]
        for nombre, valor, fuente in PARAMETROS_APLICADOS:
            filas.append([
                Paragraph(f"<b>{nombre}</b>", self._estilos["celda"]),
                Paragraph(valor, self._estilos["celda"]),
                Paragraph(fuente, self._estilos["celda"]),
            ])
        estilos = [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
                   ("VALIGN", (0, 0), (-1, -1), "TOP")]
        story.append(Spacer(1, 16))
        story.extend(self._titulo("8.  PARÁMETROS NORMATIVOS APLICADOS"))
        story.append(self._tabla(
            filas, [w * .26, w * .44, w * .30], extra=estilos))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>Referencias.</b>  "
            "[1] King GG, et al. Technical standards for respiratory oscillometry. "
            "Eur Respir J 2020;55:1900753. doi:10.1183/13993003.00753-2019.  "
            "[2] Biswas R. How to Interpret PulmoScan Oscillometry Data. "
            "Cognita Labs, 2025. pulmoscan.cognitalabs.com.  "
            "[3] American Lung Association. Oscillometry: A Toolkit for Healthcare "
            "Professionals. ALA, 2026. lung.org.  "
            "[4] Dellacà RL, et al. Detection of expiratory flow limitation in COPD "
            "using forced oscillation technique. Eur Respir J 2004;23:232-240.  "
            "[5] Gochicoa-Rangel L, Vargas MH. How best to choose an oscillometer "
            "and reference equations for your patients with asthma. "
            "Ann Allergy Asthma Immunol 2025;134:159-164.",
            self._estilos["nota"]))

    # ---------------------------------------------------------------- merge
    def _merge(self, informe: bytes, original: bytes) -> bytes:
        import pymupdf
        out = pymupdf.open()
        try:
            d1 = pymupdf.open(stream=informe, filetype="pdf")
            out.insert_pdf(d1)
            d1.close()
            try:
                d2 = pymupdf.open(stream=original, filetype="pdf")
                if d2.page_count:
                    out.insert_pdf(d2, from_page=0, to_page=0)
                d2.close()
            except Exception:
                pass
            return out.tobytes(garbage=4, deflate=True)
        finally:
            out.close()


# ---------------------------------------------------------------------------
# Parche: función auxiliar que necesita interpretation.py
# ---------------------------------------------------------------------------

def bd_thresholds_text() -> str:
    return "R5 < −40%, X5 > +50%, AX < −80%"
