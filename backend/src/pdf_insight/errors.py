"""API errors with safe Polish user-facing messages (no document text, no provider internals)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    message: str
    retryable: bool


ERRORS: dict[str, ErrorSpec] = {
    "INVALID_REQUEST": ErrorSpec(
        400, "Nieprawidłowe żądanie. Odśwież stronę i spróbuj ponownie.", False
    ),
    "ORIGIN_NOT_ALLOWED": ErrorSpec(403, "Ta strona nie ma dostępu do usługi analizy.", False),
    "BODY_TOO_LARGE": ErrorSpec(
        413, "Tekst dokumentu jest zbyt duży, aby wysłać go do analizy.", False
    ),
    "DOCUMENT_TOO_LONG": ErrorSpec(
        413,
        "Dokument przekracza długość tekstu obsługiwaną przez tę usługę. Tekst nie jest "
        "obcinany — użyj krótszego dokumentu.",
        False,
    ),
    "UNSUPPORTED_MEDIA_TYPE": ErrorSpec(415, "Nieobsługiwany format żądania.", False),
    "NO_TEXT_LAYER": ErrorSpec(
        422,
        "Dokument nie zawiera warstwy tekstowej (prawdopodobnie jest skanem). "
        "Rozpoznawanie tekstu (OCR) nie jest jeszcze dostępne — użyj PDF z tekstem.",
        False,
    ),
    "INSUFFICIENT_CONTENT": ErrorSpec(
        422,
        "Dokument zawiera za mało treści, aby rzetelnie przygotować podsumowanie "
        "i co najmniej 3 kluczowe punkty.",
        False,
    ),
    "RATE_LIMITED": ErrorSpec(
        429, "Zbyt wiele analiz w krótkim czasie. Odczekaj minutę i spróbuj ponownie.", True
    ),
    "AI_INVALID_OUTPUT": ErrorSpec(
        502,
        "Model AI zwrócił niepoprawną odpowiedź (także po ponownej próbie). Spróbuj ponownie.",
        True,
    ),
    "AI_UNAVAILABLE": ErrorSpec(
        502, "Usługa AI jest chwilowo niedostępna. Spróbuj ponownie za chwilę.", True
    ),
    "AI_QUOTA_EXCEEDED": ErrorSpec(
        503, "Wyczerpano dzienny limit analiz AI. Spróbuj ponownie później.", True
    ),
    "SERVICE_MISCONFIGURED": ErrorSpec(
        503, "Usługa analizy jest niepoprawnie skonfigurowana. Spróbuj później.", False
    ),
    "AI_TIMEOUT": ErrorSpec(
        504, "Analiza trwała zbyt długo i została przerwana. Spróbuj ponownie.", True
    ),
    "INTERNAL_ERROR": ErrorSpec(500, "Wystąpił nieoczekiwany błąd serwera.", True),
}


class ApiError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.spec = ERRORS[code]

    def body(self) -> dict[str, dict[str, object]]:
        return error_body(self.code)


def error_body(code: str) -> dict[str, dict[str, object]]:
    spec = ERRORS[code]
    return {"error": {"code": code, "message": spec.message, "retryable": spec.retryable}}
