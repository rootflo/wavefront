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

/** Sent to the model as a document block, as-is. */
export const NATIVE_DOCUMENT_MIME_TYPES = ['application/pdf'];

/** Converted to text server-side before reaching the model. */
export const EXTRACTABLE_DOCUMENT_MIME_TYPES = [
  'text/plain',
  'text/csv',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
];

export const SUPPORTED_DOCUMENT_MIME_TYPES = [...NATIVE_DOCUMENT_MIME_TYPES, ...EXTRACTABLE_DOCUMENT_MIME_TYPES];

/**
 * Extensions are checked alongside the MIME type because `file.type` cannot be
 * relied on for these formats: browsers report an empty string for `.doc` and
 * `.xls` often enough, and Windows reports `.csv` as `application/vnd.ms-excel`.
 * A MIME-only check rejects legitimate uploads. The server resolves the
 * csv/xls ambiguity from the file's magic bytes.
 */
export const SUPPORTED_DOCUMENT_EXTENSIONS = ['pdf', 'txt', 'csv', 'doc', 'docx', 'xls', 'xlsx'];

export const SUPPORTED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp'];

export const IMAGE_ACCEPT_ATTRIBUTE = 'image/*';

export const DOCUMENT_ACCEPT_ATTRIBUTE = [
  ...SUPPORTED_DOCUMENT_EXTENSIONS.map((extension) => `.${extension}`),
  ...SUPPORTED_DOCUMENT_MIME_TYPES,
].join(',');

export const MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_DOCUMENT_UPLOAD_BYTES = 50 * 1024 * 1024;

export const SUPPORTED_IMAGE_LABEL = 'JPEG, PNG, GIF, WebP';
export const SUPPORTED_DOCUMENT_LABEL = 'PDF, TXT, CSV, DOC, DOCX, XLS, XLSX';

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

/**
 * The MIME type to send for a file.
 *
 * `file.type` is only trusted when it is a type we actually support. Browsers
 * report nothing for `.doc`/`.xls`, and on Windows commonly report
 * `application/octet-stream` or `application/x-zip-compressed` for
 * `.docx`/`.xlsx`. Forwarding those meant the upload passed the extension check
 * here and was then rejected by the server with a 400.
 */
export function documentMimeTypeFor(file: File): string {
  if (file.type && SUPPORTED_DOCUMENT_MIME_TYPES.includes(file.type)) {
    return file.type;
  }
  const byExtension: Record<string, string> = {
    pdf: 'application/pdf',
    txt: 'text/plain',
    csv: 'text/csv',
    doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  };
  // `||` not `??` on the tail: an unrecognised extension leaves `file.type` as
  // '', which is falsy but not nullish, so `??` would forward the empty string.
  return byExtension[extensionOf(file.name)] ?? (file.type || 'application/octet-stream');
}
