/**
 * Shared rules for the file pickers on the chat / inference surfaces.
 *
 * These lists were previously copy-pasted into each page that renders an
 * uploader, which is how the document list drifted from the server's: the UI
 * has long offered `.txt` while the API rejected it.
 *
 * Mirrors SUPPORTED_IMAGE_MIME_TYPES and SUPPORTED_DOCUMENT_MIME_TYPES in
 * `agents_module/utils/mime_type_utils.py`. Keep the two in step — the server
 * is the real gate, and anything accepted here that it rejects becomes a 400
 * after the user has already waited for the upload.
 */

export const SUPPORTED_IMAGE_MIME_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];

interface DocumentFormat {
  extension: string;
  mimeType: string;
  label: string;
  /** Sent to the model as a document block, as-is. Otherwise flo_ai extracts it to text. */
  native?: boolean;
}

/**
 * Every supported document format, defined once. The mime, extension and label
 * lists below are all derived from this, so enabling a format is one entry.
 */
const DOCUMENT_FORMATS: DocumentFormat[] = [
  { extension: 'pdf', mimeType: 'application/pdf', label: 'PDF', native: true },
  { extension: 'txt', mimeType: 'text/plain', label: 'TXT' },
  { extension: 'csv', mimeType: 'text/csv', label: 'CSV' },
  // Legacy .doc is deferred until flo_ai has a reader for it. The server rejects
  // it too, so listing it now would only move that rejection to after the
  // upload. To enable it once flo_ai supports it, uncomment:
  // { extension: 'doc', mimeType: 'application/msword', label: 'DOC' },
  {
    extension: 'docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    label: 'DOCX',
  },
  { extension: 'xls', mimeType: 'application/vnd.ms-excel', label: 'XLS' },
  {
    extension: 'xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    label: 'XLSX',
  },
];

export const NATIVE_DOCUMENT_MIME_TYPES = DOCUMENT_FORMATS.filter((f) => f.native).map((f) => f.mimeType);

/** Converted to text by flo_ai before reaching the model. */
export const EXTRACTABLE_DOCUMENT_MIME_TYPES = DOCUMENT_FORMATS.filter((f) => !f.native).map((f) => f.mimeType);

export const SUPPORTED_DOCUMENT_MIME_TYPES = DOCUMENT_FORMATS.map((f) => f.mimeType);

/**
 * Extensions are checked alongside the MIME type because `file.type` cannot be
 * relied on for these formats: browsers report an empty string for `.doc` and
 * `.xls` often enough, and Windows reports `.csv` as `application/vnd.ms-excel`.
 * A MIME-only check rejects legitimate uploads. The server resolves the
 * csv/xls ambiguity from the file's magic bytes.
 */
export const SUPPORTED_DOCUMENT_EXTENSIONS = DOCUMENT_FORMATS.map((f) => f.extension);

const MIME_TYPE_BY_EXTENSION: Record<string, string> = Object.fromEntries(
  DOCUMENT_FORMATS.map((f) => [f.extension, f.mimeType])
);

export const SUPPORTED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp'];

export const IMAGE_ACCEPT_ATTRIBUTE = 'image/*';

export const DOCUMENT_ACCEPT_ATTRIBUTE = [
  ...SUPPORTED_DOCUMENT_EXTENSIONS.map((extension) => `.${extension}`),
  ...SUPPORTED_DOCUMENT_MIME_TYPES,
].join(',');

export const MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_DOCUMENT_UPLOAD_BYTES = 50 * 1024 * 1024;

export const SUPPORTED_IMAGE_LABEL = 'JPEG, PNG, GIF, WebP';
export const SUPPORTED_DOCUMENT_LABEL = DOCUMENT_FORMATS.map((f) => f.label).join(', ');

function extensionOf(fileName: string): string {
  const parts = fileName.split('.');
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
}

function formatMegabytes(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))}MB`;
}

/**
 * Validate one file against a MIME list and its extension fallback.
 *
 * @returns An error message to show the user, or null when the file is fine.
 */
export function validateUpload(
  file: File,
  options: {
    mimeTypes: string[];
    extensions: string[];
    maxBytes: number;
    label: string;
  }
): string | null {
  const { mimeTypes, extensions, maxBytes, label } = options;
  const typeAllowed = Boolean(file.type) && mimeTypes.includes(file.type);
  const extensionAllowed = extensions.includes(extensionOf(file.name));

  if (!typeAllowed && !extensionAllowed) {
    return `${file.name} is not a supported file type. Supported: ${label}.`;
  }
  if (file.size > maxBytes) {
    return `${file.name} is too large (max ${formatMegabytes(maxBytes)}).`;
  }
  return null;
}

export function validateImageUpload(file: File): string | null {
  return validateUpload(file, {
    mimeTypes: SUPPORTED_IMAGE_MIME_TYPES,
    extensions: SUPPORTED_IMAGE_EXTENSIONS,
    maxBytes: MAX_IMAGE_UPLOAD_BYTES,
    label: SUPPORTED_IMAGE_LABEL,
  });
}

export function validateDocumentUpload(file: File): string | null {
  return validateUpload(file, {
    mimeTypes: SUPPORTED_DOCUMENT_MIME_TYPES,
    extensions: SUPPORTED_DOCUMENT_EXTENSIONS,
    maxBytes: MAX_DOCUMENT_UPLOAD_BYTES,
    label: SUPPORTED_DOCUMENT_LABEL,
  });
}

/**
 * The `document_type` tag sent alongside the payload.
 *
 * The server ignores this field — it resolves the type from `mime_type` and
 * the file name — so it is descriptive only, and left as a free-form string
 * rather than the old 'pdf' | 'txt' union that could not name the new formats.
 */
export function documentTypeFor(file: File): string {
  return extensionOf(file.name) || 'bin';
}

export function documentMimeTypeFor(file: File): string {
  // `||` not `??` on the tail: an unrecognised extension leaves `file.type` as
  // '', which is falsy but not nullish, so `??` would forward the empty string.
  return MIME_TYPE_BY_EXTENSION[extensionOf(file.name)] ?? (file.type || 'application/octet-stream');
}
