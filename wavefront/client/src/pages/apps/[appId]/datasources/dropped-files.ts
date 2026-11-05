// Files picked or dropped for upload, each with its path inside whatever folder it came from, so a dropped
// "photos" folder uploads as photos/2024/a.jpg rather than a flat a.jpg.

export interface PickedFile {
  file: File;
  /** e.g. "photos/2024/a.jpg" for a file inside a picked folder, or just "a.jpg". */
  relativePath: string;
}

/** Files from a file input; with `webkitdirectory` the browser fills in each file's path within the folder. */
export const pickedFromInput = (files: FileList | File[]): PickedFile[] =>
  Array.from(files).map((file) => ({ file, relativePath: file.webkitRelativePath || file.name }));

const readAllEntries = async (directory: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> => {
  const reader = directory.createReader();
  const entries: FileSystemEntry[] = [];
  // readEntries hands back at most ~100 entries per call, so keep asking until it returns none.
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (batch.length === 0) return entries;
    entries.push(...batch);
  }
};

const entryFile = (entry: FileSystemFileEntry) => new Promise<File>((resolve, reject) => entry.file(resolve, reject));

const walk = async (entry: FileSystemEntry, parent: string, out: PickedFile[]) => {
  const path = parent ? `${parent}/${entry.name}` : entry.name;
  if (entry.isFile) {
    out.push({ file: await entryFile(entry as FileSystemFileEntry), relativePath: path });
  } else if (entry.isDirectory) {
    for (const child of await readAllEntries(entry as FileSystemDirectoryEntry)) {
      await walk(child, path, out);
    }
  }
};

/**
 * Everything dropped: plain files as they are, and folders opened up recursively. Falls back to the flat file
 * list where the browser doesn't expose entries.
 */
export const pickedFromDrop = async (dataTransfer: DataTransfer): Promise<PickedFile[]> => {
  // Entries have to be taken synchronously, before the drop event's data goes away.
  const entries = Array.from(dataTransfer.items ?? [])
    .map((item) => (item.kind === 'file' ? item.webkitGetAsEntry?.() : null))
    .filter((entry): entry is FileSystemEntry => Boolean(entry));
  if (entries.length === 0) return pickedFromInput(dataTransfer.files);

  const out: PickedFile[] = [];
  for (const entry of entries) await walk(entry, '', out);
  return out;
};

const MAX_FILES_PER_BATCH = 50;
const MAX_BYTES_PER_BATCH = 25 * 1024 * 1024;

/** Splits uploads into requests of at most 50 files or 25 MB (a single bigger file goes on its own). */
export const toBatches = <T extends { file: File }>(items: T[]): T[][] => {
  const batches: T[][] = [];
  let batch: T[] = [];
  let bytes = 0;
  for (const item of items) {
    if (batch.length > 0 && (batch.length >= MAX_FILES_PER_BATCH || bytes + item.file.size > MAX_BYTES_PER_BATCH)) {
      batches.push(batch);
      batch = [];
      bytes = 0;
    }
    batch.push(item);
    bytes += item.file.size;
  }
  if (batch.length > 0) batches.push(batch);
  return batches;
};
