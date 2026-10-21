import re
import unicodedata
from typing import Annotated, Literal


ARTICLES = (
    {
        "id": "KB-001",
        "title": "Conexión a la VPN",
        "keywords": ("vpn", "red", "conexion"),
        "service": "vpn",
        "content": (
            "Comprueba tu conexión a Internet y el estado del servicio VPN. "
            "Si no hay incidencia, reinicia el cliente VPN y vuelve a autenticarte. "
            "Si persiste el problema, contacta a soporte; no desactives el firewall."
        ),
    },
    {
        "id": "KB-002",
        "title": "Acceso al correo",
        "keywords": ("correo", "email", "outlook"),
        "service": "correo",
        "content": (
            "Consulta el estado del correo y prueba el portal web corporativo. "
            "Si el portal funciona pero el cliente no, reinicia el cliente. "
            "Si persiste el problema, contacta a soporte."
        ),
    },
    {
        "id": "KB-003",
        "title": "Recuperación de acceso y MFA",
        "keywords": ("mfa", "contrasena", "autenticacion", "factor", "identidad"),
        "service": "identidad",
        "content": (
            "Usa el portal corporativo de recuperación de acceso. "
            "Si perdiste el segundo factor, solicita verificación de identidad a soporte. "
            "Nunca compartas contraseñas ni códigos MFA; no desactives MFA."
        ),
    },
)

SERVICE_STATUS = {
    "vpn": "Degradado: incidencia ficticia INC-DEMO-001; el equipo de redes investiga.",
    "correo": "Operativo en el escenario ficticio.",
    "identidad": "Operativo en el escenario ficticio.",
}


def search_knowledge(
    query: Annotated[str, "Consulta de soporte TI en español"],
) -> list[dict[str, str]]:
    """Busca hasta tres artículos ficticios; una lista vacía indica falta de evidencia."""
    normalized = unicodedata.normalize("NFKD", query.casefold())
    words = set(re.findall(r"[a-z0-9]+", "".join(
        character for character in normalized if not unicodedata.combining(character)
    )))
    ranked = sorted(
        ((len(words.intersection(article["keywords"])), article) for article in ARTICLES),
        key=lambda match: match[0],
        reverse=True,
    )
    return [
        {key: article[key] for key in ("id", "title", "service", "content")}
        for score, article in ranked[:3]
        if score
    ]


def get_service_status(
    service: Annotated[Literal["vpn", "correo", "identidad"], "Servicio a consultar"],
) -> str:
    """Consulta un estado simulado, no el estado real de la organización."""
    return SERVICE_STATUS.get(service, "Servicio desconocido; consulta a soporte.")
