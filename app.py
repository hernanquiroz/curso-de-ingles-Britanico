key = (level, skill)
version = st.session_state.versions.get(key, 0)

if generate:
    if not api_key:
        st.error("Introduce tu clave API en la barra lateral "
                 "(Gemini y Groq la dan gratis).")
    else:
        with st.spinner("Generando ejercicios con IA…"):
            try:
                raw = call_llm(build_prompt(level, skill, topic),
                               provider, model, api_key)
                st.session_state.bank[key] = parse_json(raw)
                st.session_state.versions[key] = version + 1
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo generar: {e}")

data = st.session_state.bank.get(key)
if not data:
    st.info("Pulsa **✨ Generar ejercicios** para empezar. "
            "Cada pulsación crea un set nuevo, así que nunca repetirás.")
else:
    prefix = f"{level}_{skill}_{st.session_state.versions.get(key, 0)}"

    def render_quiz(questions):
        with st.form(f"form_{prefix}"):
            chosen = []
            for i, item in enumerate(questions):
                st.markdown(f"**{i + 1}. {item['q']}**")
                chosen.append(st.radio("Elige:", item["options"],
                                       key=f"{prefix}_q{i}",
                                       label_visibility="collapsed"))
            submitted = st.form_submit_button("Corregir ✅", type="primary")
        if submitted:
            score = 0
            for i, item in enumerate(questions):
                ok = item["options"].index(chosen[i]) == item["answer"]
                score += ok
                if ok:
                    st.success(f"{i + 1}. ✅ Correcto — {item['explain']}")
                else:
                    st.error(f"{i + 1}. ❌ Correcta: **{item['options'][item['answer']]}**"
                             f" — {item['explain']}")
            total = len(questions)
            pct = round(100 * score / total)
            save_result(level, skill, score, total)
            c1, c2 = st.columns(2)
            c1.metric("Resultado", f"{score}/{total} · {pct} %")
            c2.metric("Calificación", grade(pct))
            if pct == 100:
                st.balloons()
            st.caption("Guardado en tu historial · Genera un set nuevo para seguir practicando.")

    if skill in ("vocab", "grammar"):
        render_quiz(data["questions"])

    elif skill == "reading":
        st.markdown("### 📖 Lee el texto")
        st.write(data["text"])
        st.divider()
        render_quiz(data["questions"])

    elif skill == "listening":
        st.markdown("### 🎧 Escucha con atención")
        st.caption("Usa la voz británica (en-GB) de tu navegador. "
                   "Puedes repetirla las veces que quieras.")
        if st.button("🔊 Escuchar / repetir"):
            speak(data["transcript"])
        with st.expander("Ver transcripción (solo si te rindes 😄)"):
            st.write(data["transcript"])
        st.divider()
        render_quiz(data["questions"])

    elif skill == "writing":
        st.markdown("### 🖊️ Tarea de escritura")
        st.write(data["prompt"])
        text = st.text_area("Escribe aquí tu texto en inglés:", height=180,
                            key=f"{prefix}_essay")
        with st.expander("Ver ejemplo de respuesta y criterios"):
            st.write(data["model"])
            for c in data["checklist"]:
                st.write(f"- {c}")
        if st.button("🤖 Corregir con IA", type="primary"):
            if not api_key:
                st.error("Introduce tu clave API en la barra lateral.")
            elif len(text.strip()) < 10:
                st.warning("Escribe un poco más antes de corregir.")
            else:
                with st.spinner("Corrigiendo…"):
                    try:
                        raw = call_llm(build_correction_prompt(level, data["prompt"], text),
                                       provider, model, api_key)
                        fb = parse_json(raw)
                    except Exception as e:
                        st.error(f"No se pudo corregir: {e}")
                        st.stop()
                score = int(fb.get("score", 0))
                save_result(level, skill, score, 100)
                c1, c2, c3 = st.columns(3)
                c1.metric("Puntuación", f"{score}/100")
                c2.metric("Calificación", grade(score))
                c3.metric("Nivel estimado", fb.get("level_estimate", "—"))
                for corr in fb.get("corrections", []):
                    st.error(f"❌ {corr['original']} → ✅ **{corr['corrected']}**"
                             f" — {corr['why']}")
                st.success(f"✨ Versión mejorada: {fb.get('improved', '')}")
                st.info(f"💬 {fb.get('comments', '')}")
                st.caption("Guardado en tu historial.")
