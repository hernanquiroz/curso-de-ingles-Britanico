import json
import re
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from gsheets_sync import clear_progress, load_progress, save_result as sync_save

st.set_page_config(page_title="British English · MCER A1–C2", page_icon="🇬🇧", layout="centered")

# ------------------------------------------------------------------ #
# Configuración                                                       #
# ------------------------------------------------------------------ #
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
LEVEL_NAMES = {
    "A1": "Principiante", "A2": "Elemental", "B1": "Intermedio",
    "B2": "Intermedio alto", "C1": "Avanzado", "C2": "Maestría",
}
CEFR_DESC = {
    "A1": "Entiende y usa expresiones cotidianas básicas; se presenta y responde preguntas simples.",
    "A2": "Se comunica en tareas simples y rutinarias; describe su entorno y necesidades inmediatas.",
    "B1": "Se desenvuelve en viajes, describe experiencias y da opiniones sencillas.",
    "B2": "Interactúa con fluidez y espontaneidad; argumenta ventajas e inconvenientes.",
    "C1": "Uso flexible y eficaz del idioma con fines sociales, académicos y profesionales.",
    "C2": "Comprende prácticamente todo con facilidad y se expresa con precisión y matices.",
}
BRIT_TIPS = {
    "A1": "flat = piso · autumn = otoño · biscuit = galleta",
    "A2": "lift = ascensor · holiday = vacaciones · chemist's = farmacia · queue = fila",
    "B1": "lorry = camión · postcode = código postal · rubbish = basura · petrol = gasolina",
    "B2": "'have got' es muy británico: *I've got a car* · at the weekend (no 'on')",
    "C1": "Registro: *shall we?*, *fancy a cuppa?*, *brilliant*, *cheers* = gracias (informal)",
    "C2": "Matices: *quite good* en británico puede significar 'regular', no 'muy bueno'.",
}
SKILLS = [
    ("vocab", "📝 Vocabulario"),
    ("grammar", "✏️ Gramática"),
    ("reading", "📖 Lectura"),
    ("listening", "🎧 Escucha"),
    ("writing", "🖊️ Escritura"),
]
SKILL_LABEL = dict(SKILLS)
PROVIDERS = {
    "Gemini (gratis)": {
        "kind": "gemini",
        "model": "gemini-2.5-flash",  # ← modelo actualizado
        "help": "Clave gratuita en https://aistudio.google.com/app/apikey",
    },
    "Groq (gratis)": {
        "kind": "openai",
        "base": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "help": "Clave gratuita en https://console.groq.com/keys",
    },
    "OpenAI": {
        "kind": "openai",
        "base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "help": "Clave de pago en https://platform.openai.com/api-keys",
    },
}

# ------------------------------------------------------------------ #
# Progreso persistente (Google Sheets si hay credenciales; si no,    #
# fichero local progress.json)                                        #
# ------------------------------------------------------------------ #
def save_result(level, skill, score, total):
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "skill": skill,
        "score": score,
        "total": total,
        "percent": round(100 * score / total, 1),
    }
    st.session_state.history.append(entry)
    if sync_save(entry):
        st.toast("☁️ Sincronizado con Google Sheets")


def grade(pct):
    if pct >= 90:
        return "A — Sobresaliente 🏆"
    if pct >= 75:
        return "B — Notable 💪"
    if pct >= 60:
        return "C — Aprobado ✅"
    return "D — A repasar 📚"


def next_level_advice(df):
    for i, lv in enumerate(LEVELS[:-1]):
        sub = df[df["level"] == lv].tail(3)
        if len(sub) >= 3 and sub["percent"].mean() >= 85:
            nxt = LEVELS[i + 1]
            return (f"Media de {sub['percent'].mean():.0f} % en tus últimos 3 intentos "
                    f"de **{lv}** → listo para subir a **{nxt}** 🎯")
    if (df["level"] == "C2").any() and df[df["level"] == "C2"]["percent"].mean() >= 85:
        return "Dominas C2: nivel de maestría. ¡Enhorabuena! 🏆"
    return "Sigue practicando: con una media del 85 % en tus últimos 3 intentos de un nivel, te recomendaré subir."

# ------------------------------------------------------------------ #
# Llamadas a la API                                                   #
# ------------------------------------------------------------------ #
def call_llm(prompt, provider, model, api_key):
    cfg = PROVIDERS[provider]
    if cfg["kind"] == "gemini":
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8,
                                 "responseMimeType": "application/json"},
        }
        r = requests.post(url, json=body, timeout=90)
    else:
        url = f"{cfg['base']}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un generador de ejercicios. "
                                              "Respondes únicamente con JSON válido."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }
        r = requests.post(url, headers={"Authorization": f"Bearer {api_key}"},
                          json=body, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"La API respondió {r.status_code}: {r.text[:400]}")
    data = r.json()
    if cfg["kind"] == "gemini":
        return data["candidates"][0]["content"]["parts"][0]["text"]
    return data["choices"][0]["message"]["content"]


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^
