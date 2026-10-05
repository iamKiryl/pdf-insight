import type { ApiClientError } from '../api/client';
import { LIMITS } from './contract';
import type { FileProblem, PdfExtractionError } from './pdf';
import type { ReadinessProblem } from './request';
import type { DocumentType } from './schema';

/** All user-facing system messages are Polish; analysis content stays in the document language. */

export interface UserMessage {
  title: string;
  detail: string;
  retryable: boolean;
}

const MB = Math.round(LIMITS.maxFileBytes / (1024 * 1024));

export function fileProblemMessage(problem: FileProblem): UserMessage {
  switch (problem) {
    case 'not-pdf':
      return {
        title: 'To nie jest plik PDF',
        detail: 'Wybierz dokument w formacie PDF.',
        retryable: false,
      };
    case 'too-large':
      return {
        title: 'Plik jest zbyt duży',
        detail: `Maksymalny rozmiar pliku to ${MB} MB. Wybierz mniejszy dokument.`,
        retryable: false,
      };
    case 'empty':
      return {
        title: 'Plik jest pusty',
        detail: 'Wybrany plik nie zawiera danych.',
        retryable: false,
      };
  }
}

export function extractionMessage(reason: PdfExtractionError['reason']): UserMessage {
  switch (reason) {
    case 'not-pdf':
      return {
        title: 'To nie jest poprawny PDF',
        detail: 'Zawartość pliku nie odpowiada formatowi PDF, mimo rozszerzenia .pdf.',
        retryable: false,
      };
    case 'password':
      return {
        title: 'PDF jest chroniony hasłem',
        detail: 'Usuń zabezpieczenie hasłem i wybierz plik ponownie.',
        retryable: false,
      };
    case 'too-many-pages':
      return {
        title: 'Dokument ma zbyt wiele stron',
        detail: `Obsługiwane są dokumenty do ${LIMITS.maxPages} stron.`,
        retryable: false,
      };
    case 'cancelled':
      return {
        title: 'Przerwano odczyt pliku',
        detail: 'Możesz wybrać plik ponownie.',
        retryable: false,
      };
    case 'corrupt':
      return {
        title: 'Nie udało się odczytać PDF',
        detail:
          'Plik może być uszkodzony. Spróbuj otworzyć go w innym programie i zapisać ponownie.',
        retryable: false,
      };
  }
}

export function readinessMessage(problem: ReadinessProblem): UserMessage {
  switch (problem) {
    case 'no-text-layer':
      return {
        title: 'Brak tekstu do analizy',
        detail:
          'Ten PDF nie zawiera warstwy tekstowej — prawdopodobnie jest skanem lub zdjęciem. ' +
          'Rozpoznawanie tekstu (OCR) nie jest jeszcze dostępne. Użyj PDF z zaznaczalnym tekstem ' +
          '(np. wyeksportowanego z edytora) albo najpierw wykonaj OCR w innym narzędziu.',
        retryable: false,
      };
    case 'insufficient-content':
      return {
        title: 'Za mało treści',
        detail:
          'Dokument zawiera zbyt mało tekstu, aby rzetelnie przygotować podsumowanie i kluczowe punkty.',
        retryable: false,
      };
    case 'page-too-long':
    case 'document-too-long':
      return {
        title: 'Dokument jest zbyt długi',
        detail:
          `Analiza obsługuje obecnie do ${LIMITS.maxTotalChars.toLocaleString('pl-PL')} znaków tekstu ` +
          `(maks. ${LIMITS.maxPageChars.toLocaleString('pl-PL')} na stronę). Dzielenie długich ` +
          'dokumentów nie jest jeszcze dostępne, a tekst nie jest obcinany.',
        retryable: false,
      };
  }
}

export function apiErrorMessage(error: ApiClientError): UserMessage {
  if (error.serverMessage) {
    return {
      title: 'Analiza nie powiodła się',
      detail: error.serverMessage,
      retryable: error.retryable,
    };
  }
  switch (error.code) {
    case 'CONFIG_MISSING':
      return {
        title: 'Brak konfiguracji usługi',
        detail: 'Adres usługi analizy nie został skonfigurowany w tej wersji aplikacji.',
        retryable: false,
      };
    case 'CLIENT_TIMEOUT':
      return {
        title: 'Przekroczono czas oczekiwania',
        detail: 'Serwer nie odpowiedział na czas. Spróbuj ponownie.',
        retryable: true,
      };
    case 'INVALID_RESPONSE':
      return {
        title: 'Niepoprawna odpowiedź serwera',
        detail: 'Wynik nie przeszedł walidacji i nie został wyświetlony. Spróbuj ponownie.',
        retryable: true,
      };
    default:
      return {
        title: 'Brak połączenia z usługą',
        detail: 'Sprawdź połączenie z internetem i spróbuj ponownie.',
        retryable: true,
      };
  }
}

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  faktura: 'Faktura',
  umowa: 'Umowa',
  oferta: 'Oferta',
  raport: 'Raport',
  inne: 'Inny dokument',
};

export const AI_NOTICE =
  'Plik PDF pozostaje w Twojej przeglądarce. Do analizy wysyłany jest wyłącznie wyodrębniony ' +
  'z niego tekst — trafia on do naszego serwera i modelu AI (Cloudflare Workers AI, ' +
  'Llama 3.3 70B). Nie zapisujemy dokumentu na serwerze. Nie przesyłaj dokumentów, których ' +
  'treści nie możesz udostępnić.';
