"""Bilingual strings for the Language Exchange cog.

Keep this focused: only the strings the langex flow needs. English is the
fallback for any missing key/language.
"""
from typing import Final

STRINGS: Final[dict[str, dict[str, str]]] = {
    # Panel
    "panel_title": {
        "en": "🤝 Language Exchange",
        "es": "🤝 Intercambio de Idiomas",
    },
    "panel_body": {
        "en": (
            "Find a language-exchange partner — a Discord pen pal in your "
            "target language.\n\n"
            "• **Post / update** your profile so others can find you.\n"
            "• **Find a partner** to see people who are a mutual match."
        ),
        "es": (
            "Encuentra un compañero de intercambio — un amigo por Discord en "
            "el idioma que aprendes.\n\n"
            "• **Publica / actualiza** tu perfil para que te encuentren.\n"
            "• **Buscar compañero** para ver personas compatibles contigo."
        ),
    },
    "btn_post": {"en": "Post / update profile", "es": "Publicar / actualizar"},
    "btn_find": {"en": "Find a partner", "es": "Buscar compañero"},
    "btn_delete": {"en": "Delete my profile", "es": "Borrar mi perfil"},

    # Prefs step
    "prefs_title": {"en": "Your language exchange", "es": "Tu intercambio de idiomas"},
    "prefs_body": {
        "en": "Pick your languages and details, then add a short bio.",
        "es": "Elige tus idiomas y detalles, luego añade una breve descripción.",
    },
    "select_offer": {"en": "I speak (can teach)…", "es": "Yo hablo (puedo enseñar)…"},
    "select_seek": {"en": "I want to learn…", "es": "Quiero aprender…"},
    "select_level": {"en": "My level in the language I'm learning…", "es": "Mi nivel en el idioma que aprendo…"},
    "select_region": {"en": "My region…", "es": "Mi región…"},
    "select_dm": {"en": "How to contact me…", "es": "Cómo contactarme…"},
    "btn_next": {"en": "Next: about you →", "es": "Siguiente: sobre ti →"},

    # Validation
    "missing_fields": {
        "en": "Please choose: {fields}.",
        "es": "Por favor elige: {fields}.",
    },
    "field_offer": {"en": "the language you speak", "es": "el idioma que hablas"},
    "field_seek": {"en": "the language you want to learn", "es": "el idioma que quieres aprender"},
    "field_level": {"en": "your level", "es": "tu nivel"},
    "field_region": {"en": "your region", "es": "tu región"},
    "field_dm": {"en": "how to contact you", "es": "cómo contactarte"},
    "error_same_language": {
        "en": "The language you speak and the one you want to learn can't be the same.",
        "es": "El idioma que hablas y el que quieres aprender no pueden ser el mismo.",
    },
    "error_no_urls": {
        "en": "Please don't include links in your profile.",
        "es": "Por favor no incluyas enlaces en tu perfil.",
    },

    # Modal
    "modal_title": {"en": "About you", "es": "Sobre ti"},
    "modal_about_label": {"en": "About you", "es": "Sobre ti"},
    "modal_about_ph": {
        "en": "A short intro — age, where you're from, your vibe.",
        "es": "Una breve presentación — edad, de dónde eres, tu estilo.",
    },
    "modal_want_label": {"en": "What you're looking for", "es": "Qué buscas"},
    "modal_want_ph": {
        "en": "How you'd like to practise (chat, voice, activities…).",
        "es": "Cómo te gustaría practicar (chat, voz, actividades…).",
    },
    "modal_interests_label": {"en": "Interests (optional)", "es": "Intereses (opcional)"},
    "modal_interests_ph": {
        "en": "e.g. gaming, music, history, cooking — helps matching.",
        "es": "p.ej. videojuegos, música, historia, cocina — ayuda a emparejar.",
    },
    "modal_methods_label": {
        "en": "How do you want to practice? (optional)",
        "es": "¿Cómo quieres practicar? (opcional)",
    },
    "card_methods": {"en": "Open to", "es": "Disponible para"},
    "card_speaks": {"en": "Speaks", "es": "Habla"},
    "card_learning": {"en": "Learning", "es": "Aprende"},
    "card_region": {"en": "Region", "es": "Región"},

    # Posting result
    "posted_ok": {
        "en": "✅ Your profile is live. Manage it from the panel anytime.",
        "es": "✅ Tu perfil está publicado. Puedes gestionarlo desde el panel.",
    },
    "post_failed": {
        "en": "Something went wrong posting your profile. Try again later.",
        "es": "Algo salió mal al publicar tu perfil. Inténtalo más tarde.",
    },

    # Find results
    "find_no_profile": {
        "en": "Post your own profile first so partners can find you too — use **Post / update profile**.",
        "es": "Publica tu perfil primero para que también te encuentren — usa **Publicar / actualizar**.",
    },
    "find_no_matches": {
        "en": (
            "No mutual matches right now. A match is someone who wants to learn what you "
            "speak **and** speaks what you want to learn. Check back as more people post."
        ),
        "es": (
            "No hay coincidencias ahora. Una coincidencia es alguien que quiere aprender lo que "
            "hablas **y** habla lo que quieres aprender. Vuelve cuando haya más perfiles."
        ),
    },
    "find_header": {
        "en": "Top matches for you — people who are a mutual fit. Jump to their post to learn more.",
        "es": "Tus mejores coincidencias — personas compatibles. Salta a su publicación para saber más.",
    },
    "find_jump": {"en": "jump ➜", "es": "ir ➜"},

    # Posted profile card
    "post_contact_dm": {"en": "prefers DMs", "es": "prefiere MD"},
    "post_contact_tag": {"en": "prefers a server tag", "es": "prefiere mención en el servidor"},

    # Delete
    "delete_ok": {"en": "🗑️ Your profile was removed.", "es": "🗑️ Tu perfil fue eliminado."},
    "delete_none": {"en": "You don't have a profile to delete.", "es": "No tienes un perfil que borrar."},

    # Generic
    "generic_error": {
        "en": "Something went wrong. Please try again later.",
        "es": "Algo salió mal. Inténtalo de nuevo más tarde.",
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Translate a key. Falls back to English, then the raw key."""
    entry = STRINGS.get(key, {})
    text = entry.get(lang, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text
