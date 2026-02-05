import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { User } from "lucide-react";

import { Field, FieldContent, FieldTitle } from "~/components/ui/field";
import { uploadFiles } from "~/lib/api";

type UserAvatarFieldProps = {
  value?: string;
  onChange: (value: string) => void;
  label?: ReactNode;
};

export const UserAvatarField = ({ value, onChange, label = "头像" }: UserAvatarFieldProps) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Field orientation="horizontal" className="items-center!">
      <FieldTitle className="shrink-0 max-w-12 w-12">{label}</FieldTitle>
      <FieldContent>
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="group relative w-10 h-10 rounded-full ring-2 ring-brand/20 bg-brand-muted overflow-hidden shadow-sm hover:ring-brand/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/70"
            onClick={() => fileInputRef.current?.click()}
          >
            {value ? (
              <img
                src={value}
                alt="用户头像"
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <User className="h-6 w-6 text-brand-dark" />
              </div>
            )}
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;

              const previousValue = value ?? "";
              const previewUrl = URL.createObjectURL(file);
              // 先本地预览
              onChange(previewUrl);
              setUploading(true);
              setError(null);

              try {
                const [item] = await uploadFiles([file]);
                // 使用后端返回的公开地址覆盖本地预览
                if (item?.path) {
                  onChange(item.path);
                }
              } catch (e) {
                // 上传失败时恢复为之前的值，并提示错误
                onChange(previousValue);
                setError(
                  e instanceof Error ? e.message : "头像上传失败，请稍后重试",
                );
              } finally {
                setUploading(false);
              }

              // TODO: 在这里调用上传接口，成功后拿到真实 avatar URL 再调用 onChange(url)
            }}
          />
        </div>
        {uploading && (
          <p className="mt-1 text-xs text-gray-400">正在上传头像...</p>
        )}
        {error && (
          <p className="mt-1 text-xs text-error">{error}</p>
        )}
      </FieldContent>
    </Field>
  );
}

