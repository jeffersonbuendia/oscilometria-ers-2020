"""
App de oscilometría de impulso — ERS 2020.

Flujo: cargar el PDF del espirómetro → revisar datos extraídos →
ver interpretación automática → editar conclusión → descargar informe.
"""
from __future__ import annotations

import streamlit as st

from informe_oscilometria import InformeOscilometria
from interpretation import interpret
from models import OscParameter, OscillometrySession, QualityData, PatientData
from parser import parse_report

st.set_page_config(
    page_title="Oscilometría — ERS 2020",
    page_icon="🌬️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PHYSICIAN_DEFAULT = "Jefferson Antonio Buendía, MD Neumólogo Pediatra"
INSTITUTION_DEFAULT = "SALUD ES VIVIR IPS"
LABORATORIO_DEFAULT = "Laboratorio de Función Pulmonar"
CIUDAD_DEFAULT = "Medellín, Colombia"

PARAMETROS_LABEL = {
    "R5":     "R5 — Resistencia total a 5 Hz (cmH₂O/L/s)",
    "R20":    "R20 — Resistencia central a 20 Hz (cmH₂O/L/s)",
    "R5-R20": "R5-R20 — Dependencia de frecuencia (cmH₂O/L/s)",
    "X5":     "X5 — Reactancia a 5 Hz (cmH₂O/L/s)",
    "AX":     "AX — Área bajo la curva de reactancia (cmH₂O/L)",
    "Fres":   "Fres — Frecuencia de resonancia (Hz)",
}

PARAM_ORDER = ["R5", "R20", "R5-R20", "X5", "AX", "Fres"]


def _num(v):
    return None if v in (None, 0.0) else float(v)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Configuración")
    institution = st.text_input("Institución", INSTITUTION_DEFAULT)
    laboratory = st.text_input("Laboratorio", LABORATORIO_DEFAULT)
    city = st.text_input("Ciudad", CIUDAD_DEFAULT)
    physician = st.text_area("Médico firmante", PHYSICIAN_DEFAULT, height=80)
    report_number = st.text_input("N.° de informe", "")
    bronchodilator = st.text_input(
        "Broncodilatador", "Salbutamol 400 µg / IDM con cámara espaciadora")

    st.divider()
    st.caption(
        "**Criterios aplicados — ERS 2020**\n\n"
        "• Normalidad: z-score entre −1,645 y +1,645\n"
        "• BD positiva:\n"
        "  — R5 disminución ≥ 40%\n"
        "  — X5 aumento ≥ 50%\n"
        "  — AX disminución ≥ 80%\n"
        "• CoV R5: ≤ 10% adultos / ≤ 15% niños"
    )

# ---------------------------------------------------------------------------
# Pantalla principal
# ---------------------------------------------------------------------------

st.title("🌬️ Informe de Oscilometría de Impulso")
st.caption(
    "Interpretación conforme a ERS 2020 (Eur Respir J 2020;55:1900753) · "
    "PulmoScan Interpretation Guide (Cognita Labs 2025) · "
    "American Lung Association Oscillometry Toolkit 2026"
)

uploaded = st.file_uploader("Subir reporte de oscilometría en PDF", type=["pdf"])

if not uploaded:
    st.markdown("""
    ### ¿Cómo funciona?

    1. Sube el PDF del **PulmoScan** u otro oscilómetro compatible.
    2. Revisa y corrige los datos extraídos automáticamente.
    3. Consulta la interpretación automática (ERS 2020).
    4. Edita la conclusión si es necesario.
    5. Descarga el informe en PDF (incluye la primera página del original).

    ### Parámetros interpretados
    | Parámetro | Significado | Anormal si |
    |---|---|---|
    | R5 | Resistencia total | z > +1,645 |
    | R20 | Resistencia central | z > +1,645 |
    | R5-R20 | Vía aérea pequeña | z > +1,645 |
    | X5 | Reactancia (rigidez) | z < −1,645 |
    | AX | Área de reactancia | z > +1,645 |
    | Fres | Frecuencia de resonancia | z > +1,645 |
    """)
    st.stop()

original_pdf = uploaded.getvalue()

try:
    session, raw_text = parse_report(original_pdf)
except Exception as err:
    st.error(f"No fue posible procesar el PDF: {err}")
    st.stop()

# Validar parámetros mínimos
faltan = [k for k in ("R5", "X5") if k not in session.params or
          session.params[k].pre is None]
if faltan:
    st.error(
        "La extracción automática no encontró: " + ", ".join(faltan) +
        ". Verifique el formato del PDF o complételos manualmente.")
else:
    st.success("PDF procesado. Revise los datos antes de generar el informe.")

# ---------------------------------------------------------------------------
# 1. Datos del paciente
# ---------------------------------------------------------------------------

st.subheader("1. Datos del paciente")
p = session.patient
c1, c2, c3 = st.columns(3)

with c1:
    p.name = st.text_input("Nombre completo", p.name)
    p.gender = st.selectbox("Sexo biológico",
                            ["", "Male", "Female", "Masculino", "Femenino"],
                            index=0 if not p.gender else
                            (["", "Male", "Female", "Masculino", "Femenino"]
                             .index(p.gender) if p.gender in
                             ["", "Male", "Female", "Masculino", "Femenino"] else 0))

with c2:
    p.age_years = st.number_input("Edad (años)", min_value=0.0, max_value=120.0,
                                  value=float(p.age_years or 0.0), step=0.1)
    p.height_cm = st.number_input("Talla (cm)", min_value=0.0, max_value=250.0,
                                  value=float(p.height_cm or 0.0), step=0.1)

with c3:
    p.weight_kg = st.number_input("Peso (kg)", min_value=0.0, max_value=400.0,
                                  value=float(p.weight_kg or 0.0), step=0.1)
    p.exam_date = st.text_input("Fecha del estudio", p.exam_date)

c4, c5 = st.columns(2)
with c4:
    p.ethnicity = st.text_input("Etnia", p.ethnicity)
    p.reference_equation = st.text_input("Ecuación de referencia",
                                         p.reference_equation)
with c5:
    p.smoking_history = st.text_input("Tabaquismo", p.smoking_history)
    p.notes = st.text_input("Notas clínicas", p.notes or "")

st.caption(
    "ℹ️ La ecuación de referencia determina los valores predichos y el LLN/ULN. "
    "ERS 2020 recomienda usar la ecuación desarrollada con el dispositivo específico "
    "y apropiada para la población del paciente."
)

# ---------------------------------------------------------------------------
# 2. Control de calidad
# ---------------------------------------------------------------------------

st.subheader("2. Control de calidad")
q = session.quality
col_q1, col_q2, col_q3, col_q4 = st.columns(4)
with col_q1:
    n = st.number_input("N.° mediciones aceptables", min_value=0, max_value=30,
                        value=int(q.n_acceptable or 0))
    q.n_acceptable = n or None
with col_q2:
    cov = st.number_input("CoV R5 (%)", min_value=0.0, max_value=100.0,
                          value=float(q.cov_r5_pct or 0.0), step=0.1)
    q.cov_r5_pct = _num(cov)
with col_q3:
    coh = st.number_input("Coherencia promedio", min_value=0.0, max_value=1.0,
                          value=float(q.avg_coherence or 0.0), step=0.01)
    q.avg_coherence = _num(coh)
with col_q4:
    st.metric("Paciente pediátrico", "Sí" if p.is_paediatric else "No")
    if p.is_paediatric:
        st.caption("CoV límite: ≤ 15%")

# ---------------------------------------------------------------------------
# 3. Parámetros oscilométricos
# ---------------------------------------------------------------------------

st.subheader("3. Parámetros oscilométricos")
st.caption(
    "Valores extraídos automáticamente. Los campos vacíos se tratan como "
    "ausentes, no como cero. El z-score determina la normalidad."
)

for key in PARAM_ORDER:
    if key not in session.params:
        session.params[key] = OscParameter(
            name=key,
            unit="%" if "/" not in key else "cmH₂O/L/s")

    p_obj = session.params[key]
    label = PARAMETROS_LABEL.get(key, key)
    st.markdown(f"**{label}**")
    cols = st.columns(8)
    fields = [
        ("Referencia", "reference"),
        ("Pre-BD", "pre"),
        ("Z-score pre", "pre_z"),
        ("% pred. pre", "pre_pct_pred"),
        ("Post-BD", "post"),
        ("Z-score post", "post_z"),
        ("% pred. post", "post_pct_pred"),
        ("Cambio %", "pre_post_pct"),
    ]
    for col, (lbl, attr) in zip(cols, fields):
        with col:
            cur = getattr(p_obj, attr)
            val = st.number_input(lbl, value=float(cur or 0.0),
                                  step=0.01, format="%.3f",
                                  key=f"{key}_{attr}")
            setattr(p_obj, attr, _num(val))
    st.divider()

session.has_post = any(
    p.post is not None for p in session.params.values())
if bronchodilator:
    session.bronchodilator = bronchodilator

# ---------------------------------------------------------------------------
# 4. Interpretación automática
# ---------------------------------------------------------------------------

result = interpret(session)

st.subheader("4. Interpretación automática — ERS 2020")

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Patrón", result.pattern.label)
with m2:
    st.metric("Subtipo", result.pattern.subtype or "—")
with m3:
    if session.has_post:
        veredicto = "✅ Positiva" if result.bd.positive else "❌ Negativa"
        st.metric("Resp. broncodilatadora", veredicto)
    else:
        st.metric("Resp. broncodilatadora", "Sin datos post-BD")
with m4:
    grado = result.quality.grade
    emoji = {"OK": "✅", "ACEPTABLE": "⚠️", "LIMITADO": "❌"}.get(grado, "")
    st.metric("Calidad técnica", f"{emoji} {grado}")

if result.pattern.detail:
    st.info(f"**Patrón:** {result.pattern.detail}")

for f in result.pattern.flags:
    st.warning(f)

if result.quality.notes:
    for nota in result.quality.notes:
        st.warning(nota)

if session.has_post and result.bd.positive != session.has_post:
    bd = result.bd
    st.markdown(
        "**Detalle de la respuesta broncodilatadora:**\n\n"
        f"- R5: {bd.r5_change_pct:+.1f}% "
        f"(umbral < −40% → {'✓' if bd.r5_positive else '✗'})\n"
        f"- X5: {bd.x5_change_pct:+.1f}% "
        f"(umbral > +50% → {'✓' if bd.x5_positive else '✗'})\n"
        f"- AX: {bd.ax_change_pct:+.1f}% "
        f"(umbral < −80% → {'✓' if bd.ax_positive else '✗'})"
        if all(v is not None for v in
               [bd.r5_change_pct, bd.x5_change_pct, bd.ax_change_pct])
        else ""
    )

if result.within_breath.efl_suspected:
    st.warning(f"⚠️ EFL: {result.within_breath.text}")
elif result.within_breath.ifl_suspected:
    st.info(f"ℹ️ IFL: {result.within_breath.text}")

# ---------------------------------------------------------------------------
# 5. Conclusión
# ---------------------------------------------------------------------------

st.subheader("5. Conclusión")
conclusion = st.text_area(
    "Conclusión del informe (editable)",
    value=result.conclusion,
    height=120,
)
editada = conclusion.strip() != result.conclusion.strip()
if editada:
    st.caption("Conclusión modificada por el médico. Aparecerá tal como se escribe.")

st.subheader("6. Médico firmante")
st.markdown(f"**{physician}**")

# ---------------------------------------------------------------------------
# 6. Generar y descargar
# ---------------------------------------------------------------------------

try:
    nombre_firma, _, credenciales = (physician or "").partition(",")
    gen = InformeOscilometria(
        institucion=institution,
        laboratorio=laboratory,
        ciudad=city,
        firmante=nombre_firma.strip(),
        credenciales=credenciales.strip(),
    )
    pdf_final = gen.generar(
        session=session,
        result=result,
        conclusion=conclusion if editada else "",
        n_reporte=report_number,
        pdf_original=original_pdf,
    )
except Exception as err:
    st.error(f"Error al generar el informe: {err}")
    st.stop()

safe_name = "_".join(p.name.split()) if p.name else "paciente"
st.download_button(
    "📥 Descargar informe de oscilometría",
    data=pdf_final,
    file_name=f"Informe_oscilometria_{safe_name}.pdf",
    mime="application/pdf",
    type="primary",
)
st.caption(
    "El PDF incluye el informe completo (ERS 2020) y, "
    "como última página, la primera hoja del reporte original del equipo."
)

with st.expander("📄 Texto extraído del PDF (depuración)"):
    st.text(raw_text[:3000])
