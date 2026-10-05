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

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  };

  return (
    <div
      className={`dropzone${dragging ? ' dropzone--active' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <p className="dropzone__title">Przeciągnij plik PDF tutaj</p>
      <p className="dropzone__or">lub</p>
      <button
        type="button"
        className="button button--primary"
        aria-describedby={hintId}
        onClick={() => inputRef.current?.click()}
      >
        Wybierz plik PDF
      </button>
      <p id={hintId} className="dropzone__hint">
        Format PDF z warstwą tekstową, maksymalnie {MB} MB.
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
    </div>
  );
}
