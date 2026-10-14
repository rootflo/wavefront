import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { copyToClipboard, downloadBlobFile, extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { Copy } from 'lucide-react';
import React, { useRef, useState } from 'react';
import { FILE_STORAGE_PROTOCOLS } from './datasource-types';

interface FileStoragePanelProps {
  datasourceId: string;
  datasourceType: string;
}

/** Blob responses hide the JSON error body; read it back out for the message. */
const getDownloadErrorMessage = async (error: unknown): Promise<string | undefined> => {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text()) as { meta?: { error?: string } };
      return body.meta?.error;
    } catch {
      return undefined;
    }
  }
  return extractErrorMessage(error);
};

const fileNameFromPath = (path: string) => path.split('/').filter(Boolean).pop() || 'download';

const FileStoragePanel: React.FC<FileStoragePanelProps> = ({ datasourceId, datasourceType }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [uploadPath, setUploadPath] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadedPath, setUploadedPath] = useState<string | null>(null);

  const [downloadPath, setDownloadPath] = useState('');
  const [downloading, setDownloading] = useState(false);

  const protocol = FILE_STORAGE_PROTOCOLS[datasourceType] || 's3';

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await floConsoleService.datasourcesService.uploadFile(
        datasourceId,
        file,
        uploadPath.trim() || undefined
      );
      const path = response.data?.data?.path;
      if (!path) {
        notifyError('Upload succeeded but no path was returned');
        return;
      }
      setUploadedPath(path);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      notifySuccess('File uploaded successfully');
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to upload file');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async () => {
    const path = downloadPath.trim();
    if (!path) return;
    setDownloading(true);
    try {
      const response = await floConsoleService.datasourcesService.downloadFile(datasourceId, path);
      downloadBlobFile(fileNameFromPath(path), response.data);
    } catch (error) {
      notifyError((await getDownloadErrorMessage(error)) || 'Failed to download file');
    } finally {
      setDownloading(false);
    }
  };

  const handleCopy = async (value: string) => {
    if (await copyToClipboard(value)) {
      notifySuccess('Copied path to clipboard');
    } else {
      notifyError('Failed to copy path');
    }
  };

  return (
    <div className="grid w-full gap-6 lg:grid-cols-2">
      <div className="frost-panel ring-frost-border rounded-xl border ring-1">
        <div className="border-b border-[#EFF0F1] px-6 py-4">
          <h2 className="frost-text text-lg font-semibold">Upload File</h2>
        </div>
        <div className="flex flex-col gap-4 p-6">
          <div className="flex flex-col gap-2">
            <Label htmlFor="fileStorageUpload">File</Label>
            <Input
              ref={fileInputRef}
              type="file"
              id="fileStorageUpload"
              onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
              disabled={uploading}
              className="frost-control ring-frost-border frost-text file:text-brand w-full cursor-pointer border px-3 py-2 text-sm ring-1 outline-none file:cursor-pointer"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="fileStorageUploadPath">
              Destination path <span className="frost-text-subtle">(Optional)</span>
            </Label>
            <Input
              id="fileStorageUploadPath"
              placeholder="folder/ or folder/name.ext — defaults to the file name"
              value={uploadPath}
              onChange={(e) => setUploadPath(e.target.value)}
              disabled={uploading}
            />
          </div>
          <div>
            <Button onClick={handleUpload} loading={uploading} disabled={!file || uploading}>
              Upload
            </Button>
          </div>
          {uploadedPath && (
            <div className="flex flex-col gap-1">
              <span className="frost-text-muted text-xs font-medium">Uploaded to</span>
              <div className="flex items-center gap-1">
                <span className="frost-text truncate font-mono text-sm" title={uploadedPath}>
                  {uploadedPath}
                </span>
                <Button variant="ghost" size="sm" title="Copy path" onClick={() => void handleCopy(uploadedPath)}>
                  <Copy className="h-3.5 w-3.5" />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setDownloadPath(uploadedPath)}>
                  Use for download
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="frost-panel ring-frost-border rounded-xl border ring-1">
        <div className="border-b border-[#EFF0F1] px-6 py-4">
          <h2 className="frost-text text-lg font-semibold">Download File</h2>
        </div>
        <form
          className="flex flex-col gap-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            void handleDownload();
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="fileStorageDownloadPath">Path</Label>
            <Input
              id="fileStorageDownloadPath"
              placeholder={`${protocol}://bucket/folder/name.ext or folder/name.ext`}
              value={downloadPath}
              onChange={(e) => setDownloadPath(e.target.value)}
              disabled={downloading}
            />
          </div>
          <div>
            <Button type="submit" loading={downloading} disabled={!downloadPath.trim() || downloading}>
              Download
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default FileStoragePanel;
