import { useCallback, useRef, useState } from "react";
import { apiClient } from "../lib/api-client";

interface FileUploadOptions {
  maxSizeMB?: number;
  allowedExtensions?: string[];
}

export function useFileUpload(options?: FileUploadOptions) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const upload = useCallback(
    async (file: File, extra: { domain: string; classificationLevel: string; projectId?: string; submitterId: string }) => {
      const maxSize = (options?.maxSizeMB ?? 200) * 1024 * 1024;
      if (file.size > maxSize) {
        throw new Error(`文件大小超过限制: ${options?.maxSizeMB ?? 200}MB`);
      }

      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (options?.allowedExtensions && ext && !options.allowedExtensions.includes(ext)) {
        throw new Error(`不支持的文件格式: ${ext}`);
      }

      setUploading(true);
      setProgress(0);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("domain", extra.domain);
        formData.append("classification_level", extra.classificationLevel);
        if (extra.projectId) formData.append("project_id", extra.projectId);
        formData.append("submitter_id", extra.submitterId);

        const result = await apiClient.upload<{ candidateId: string; status: string }>(
          "/ingestion/document",
          formData
        );
        setProgress(100);
        return result;
      } finally {
        setUploading(false);
      }
    },
    [options]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setUploading(false);
  }, []);

  return { upload, cancel, progress, uploading };
}