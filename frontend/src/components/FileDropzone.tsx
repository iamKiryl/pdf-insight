import { useId, useRef, useState, type DragEvent } from 'react';
import { LIMITS } from '../lib/contract';

interface Props {
  onFile: (file: File) => void;
}

const MB = Math.round(LIMITS.maxFileBytes / (1024 * 1024));

export function FileDropzone({ onFile }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  };

  return (
    <section
      className={`dropzone${dragging ? ' dropzone--active' : ''}`}
      aria-labelledby="dropzone-title"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <p className="label label--accent">01 · Wgraj PDF</p>
      <h2 id="dropzone-title" className="dropzone__title">
        {dragging ? 'Upuść plik, aby go wczytać' : 'Przeciągnij plik PDF tutaj'}
      </h2>
      <p className="dropzone__or">albo</p>
      <button
        type="button"
        className="button button--primary"
        aria-describedby={hintId}
        onClick={() => inputRef.current?.click()}
      >
        Wybierz plik PDF
      </button>
      <p id={hintId} className="dropzone__hint">
        <span className="tag">Maks. {MB} MB</span> Format PDF z warstwą tekstową. Plik nie opuszcza
        przeglądarki.
      </p>
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept="application/pdf,.pdf"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) onFile(file);
        }}
      />
    </section>
  );
}
