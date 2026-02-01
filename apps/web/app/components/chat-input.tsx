import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'

import { Button } from '~/components/ui/button'
import { Textarea } from '~/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog'
import FileItemBadge from '~/components/file-item-badge'
import ExcelPreview from '~/components/excel-preview'
import ExcelIcon from '~/assets/iconify/vscode-icons/file-type-excel.svg?react'

import type { ClipboardEvent, KeyboardEvent } from 'react'
import type { FileItem } from '~/components/file-item-badge'


interface ChatInputProps {
  text: string
  onTextChange: (text: string) => void
  onSubmit: () => void
  onPasteFiles: (files: File[], e: React.ClipboardEvent) => Promise<void>
  placeholder: string
  className?: string
  fileItems?: FileItem[]
  onRemoveFile: (fileId: string) => void
  /** 是否处于加载/处理状态 */
  loading?: boolean
}

const ChatInput = ({ text, onTextChange, onSubmit, onPasteFiles, placeholder, className, fileItems, onRemoveFile, loading = false }: ChatInputProps) => {

  // 是否禁用提交（loading 或正在处理粘贴文件）
  const isSubmitDisabled = !text.trim() || loading;

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isSubmitDisabled) {
        onSubmit();
      }
    }
  };

  const [pasteFileProcessing, setPasteFileProcessing] = useState(false);
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null);

  const onPaste = async (e: ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const files = items
      .filter(item => item.kind === 'file')
      .map(item => item.getAsFile())
      .filter((file): file is File => file !== null);

    if (files.length === 0) {
      return;
    }

    try {
      setPasteFileProcessing(true);
      await onPasteFiles(files, e);
    } catch (error) {
      console.error(error);
    } finally {
      setPasteFileProcessing(false);
    }
  };

  return (
    <div className={className}>
      {/* 文件列表 */}
      {fileItems && fileItems.length > 0 && (
        <div className="px-1 pb-1 flex items-start gap-1 flex-wrap">
          {fileItems.map((fileItem) => (
            <FileItemBadge
              key={fileItem.fileId}
              fileItem={fileItem}
              onRemove={onRemoveFile}
              onClick={() => {
                // 只有成功上传且有路径的文件才能预览
                if (fileItem.status === "success" && fileItem.path) {
                  setPreviewFile(fileItem);
                }
              }}
            />
          ))}
        </div>
      )}

      {/* Excel 预览弹窗 */}
      <Dialog open={!!previewFile} onOpenChange={(open) => !open && setPreviewFile(null)}>
        <DialogContent className="max-w-[95vw]! max-h-[95vh]! w-[95vw]! h-[95vh]! flex flex-col p-0 gap-0">
          <DialogHeader className="px-6 pt-6 pb-4 border-b shrink-0">
            <DialogTitle>
              <div className='flex items-center gap-0.5'>
                <ExcelIcon className="w-6 h-6 shrink-0" />
                <div>{previewFile?.file.name}</div>
              </div>
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden min-h-0">
            {previewFile && previewFile.path && (
              <ExcelPreview
                className="w-full h-full"
                fileUrl={`${previewFile.path}`}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
      <div className="bg-white border-2 border-emerald-500 rounded-xl py-2 shadow-sm">
        <div className="flex items-start pr-2">
          <Textarea
            rows={3}
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            onPaste={onPaste}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            disabled={pasteFileProcessing || loading}
            className="flex-1 border-0 focus:ring-0 focus-visible:ring-0 resize-none min-h-[80px] text-gray-900 placeholder:text-gray-400 border-none shadow-none max-h-[100px] overflow-y-auto"
          />

          <div className="self-end">
            <Button
              onClick={() => onSubmit()}
              size={"icon"}
              disabled={isSubmitDisabled || pasteFileProcessing}
              className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-300 rounded-full p-3 shrink-0 cursor-pointer"
            >
              {loading || pasteFileProcessing ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </Button>
          </div>

        </div>
      </div>
    </div>

  )
}

export default ChatInput