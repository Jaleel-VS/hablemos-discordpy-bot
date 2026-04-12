"""Internationalization strings for the Introduce cog."""
from typing import Final

STRINGS: Final[dict[str, dict[str, str]]] = {
    # ── IntroStartView ──
    "intro_title": {
        "en": "Introduction",
        "es": "Introducción",
    },
    "intro_description": {
        "en": "Welcome! Let's introduce you to the community.\n\nAre you looking for a language exchange partner?",
        "es": "¡Bienvenido/a! Vamos a presentarte a la comunidad.\n\n¿Estás buscando un compañero de intercambio?",
    },
    "intro_footer": {
        "en": "This form will expire in 5 minutes",
        "es": "Este formulario expirará en 5 minutos",
    },
    "select_exchange_placeholder": {
        "en": "Looking for an exchange partner?",
        "es": "¿Buscas un compañero de intercambio?",
    },
    "select_exchange_yes": {
        "en": "Yes",
        "es": "Sí",
    },
    "select_exchange_yes_desc": {
        "en": "I want to find a language exchange partner",
        "es": "Quiero encontrar un compañero de intercambio",
    },
    "select_exchange_no": {
        "en": "No",
        "es": "No",
    },
    "select_exchange_no_desc": {
        "en": "I just want to introduce myself",
        "es": "Solo quiero presentarme",
    },
    "btn_continue": {
        "en": "Continue →",
        "es": "Continuar →",
    },
    "please_select_exchange": {
        "en": "Please select whether you're looking for an exchange partner.",
        "es": "Por favor selecciona si buscas un compañero de intercambio.",
    },
    # ── ExchangePrefsView ──
    "exchange_title": {
        "en": "Find an Exchange Partner",
        "es": "Buscar un compañero de intercambio",
    },
    "exchange_description": {
        "en": "Fill in your details below, then click **Next** to finish.",
        "es": "Rellena tus datos abajo y haz clic en **Siguiente** para terminar.",
    },
    "select_offer_placeholder": {
        "en": "Language you speak natively...",
        "es": "Tu idioma nativo...",
    },
    "select_seek_placeholder": {
        "en": "Language you want to learn...",
        "es": "Idioma que quieres aprender...",
    },
    "select_level_placeholder": {
        "en": "Your level in that language...",
        "es": "Tu nivel en ese idioma...",
    },
    "select_region_placeholder": {
        "en": "Your region...",
        "es": "Tu región...",
    },
    "btn_next_about": {
        "en": "Next: About You →",
        "es": "Siguiente: Sobre ti →",
    },
    "missing_fields": {
        "en": "Please select: {fields}.",
        "es": "Por favor selecciona: {fields}.",
    },
    # ── ExchangeDetailsModal ──
    "modal_title_exchange": {
        "en": "About You",
        "es": "Sobre ti",
    },
    "label_about": {
        "en": "About me & what I'm looking for",
        "es": "Sobre mí y lo que busco",
    },
    "placeholder_about": {
        "en": "About yourself, hobbies, goals, and what you want in a partner...",
        "es": "Sobre ti, hobbies, metas, y lo que buscas en un compañero...",
    },
    "label_other_lang": {
        "en": "Other native language (if any)",
        "es": "Otro idioma nativo (si aplica)",
    },
    "placeholder_other_lang": {
        "en": "e.g., Portuguese, Catalan, Arabic... (leave blank if N/A)",
        "es": "ej., Portugués, Catalán, Árabe... (dejar en blanco si no aplica)",
    },
    # ── IntroOnlyModal ──
    "modal_title_intro": {
        "en": "Introduce Yourself",
        "es": "Preséntate",
    },
    "label_about_me": {
        "en": "About Me",
        "es": "Sobre mí",
    },
    "placeholder_about_me": {
        "en": "Tell others a bit about yourself...",
        "es": "Cuéntanos un poco sobre ti...",
    },
    "label_interests": {
        "en": "Your Interests (Optional)",
        "es": "Tus intereses (Opcional)",
    },
    "placeholder_interests": {
        "en": "e.g., YouTube, sports, music, cooking, gaming...",
        "es": "ej., YouTube, deportes, música, cocina, videojuegos...",
    },
    # ── Embed text ──
    "embed_seeking": {
        "en": "{mention}'s seeking an exchange partner!",
        "es": "¡{mention} busca un compañero de intercambio!",
    },
    "embed_i_speak": {
        "en": "I speak",
        "es": "Hablo",
    },
    "embed_region": {
        "en": "Region",
        "es": "Región",
    },
    "embed_looking_for": {
        "en": "⭐ Looking for",
        "es": "⭐ Busco",
    },
    "embed_partner_suffix": {
        "en": "partner",
        "es": "compañero/a",
    },
    "embed_my_level": {
        "en": "My level",
        "es": "Mi nivel",
    },
    "embed_footer_dm": {
        "en": "Send me a DM if you'd like to be my partner!",
        "es": "¡Envíame un DM si quieres ser mi compañero/a!",
    },
    "embed_footer_tag": {
        "en": "Tag me in the server if you'd like to be my partner!",
        "es": "¡Etiquétame en el servidor si quieres ser mi compañero/a!",
    },
    "embed_intro_title": {
        "en": "New Member Introduction",
        "es": "Nuevo miembro",
    },
    "embed_intro_joined": {
        "en": "**{mention}** has joined the community!",
        "es": "¡**{mention}** se ha unido a la comunidad!",
    },
    # ── Errors / confirmations ──
    "error_no_links": {
        "en": "Links are not allowed. Please remove any URLs and try again.",
        "es": "No se permiten enlaces. Por favor elimina cualquier URL e inténtalo de nuevo.",
    },
    "error_already_posted": {
        "en": "You already have an active exchange post. Use `/exchange delete` to remove it, or `/exchange repost` to bump it (within 10 minutes of posting, or after 14 days).",
        "es": "Ya tienes una publicación activa. Usa `/exchange delete` para eliminarla, o `/exchange repost` para republicarla (dentro de 10 minutos, o después de 14 días).",
    },
    "error_generic": {
        "en": "Something went wrong. Please try again later.",
        "es": "Algo salió mal. Por favor inténtalo más tarde.",
    },
    "error_same_language": {
        "en": "You can't offer and seek the same language. Please change one of your selections.",
        "es": "No puedes ofrecer y buscar el mismo idioma. Por favor cambia una de tus selecciones.",
    },
    "error_other_lang_required": {
        "en": "You selected 'Other' as your native language — please specify which language in the field provided.",
        "es": "Seleccionaste 'Other' como tu idioma nativo — por favor especifica cuál en el campo proporcionado.",
    },
    "dm_copy_failed": {
        "en": "I couldn't DM you a copy of your post — check your privacy settings if you'd like to receive it.",
        "es": "No pude enviarte una copia por DM — revisa tu configuración de privacidad si deseas recibirla.",
    },
    "success_intro": {
        "en": "Your introduction has been posted to {channel}.\n\nWelcome to the community!",
        "es": "Tu presentación ha sido publicada en {channel}.\n\n¡Bienvenido/a a la comunidad!",
    },
    "success_exchange": {
        "en": "Your exchange request has been posted to {channel}.\n\nGood luck finding a partner!",
        "es": "Tu solicitud ha sido publicada en {channel}.\n\n¡Buena suerte encontrando un compañero/a!",
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Get a translated string. Falls back to English if key/lang missing."""
    entry = STRINGS.get(key, {})
    text = entry.get(lang, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text
