import { useState, useRef, useEffect } from "react";
import { FileSpreadsheet, Loader2, Download, X, Cloud, Info, Check, RefreshCw } from "lucide-react";

import { Button } from "~/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "~/components/ui/resizable"

import AppHeader from "~/components/app-header";
import ChatInput from "~/components/chat-input";
import ExcelPreview from "~/components/excel-preview";

import { useExcelChat, type AssistantMessage } from "~/hooks/use-excel-chat";

import { cn } from "~/lib/utils";
import { uploadFiles } from "~/lib/api";
import type { Route } from "./+types/_index";
import MessageList from "~/components/llm-chat/message-list";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "LLM Excel" },
    { name: "description", content: "使用 LLM 处理 Excel 数据" },
  ];
}

// 文件上传状态
type FileUploadStatus = "uploading" | "success" | "error";

// 文件项接口
interface FileItem {
  file: File;
  status: FileUploadStatus;
  progress: number; // 0-100
  fileId?: string; // 上传成功后的 file_id
  path?: string; // 文件路径
  error?: string; // 错误信息
}

const LLMChatPage = () => {

  const [query, setQuery] = useState('')
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [selectedFileIndex, setSelectedFileIndex] = useState<number>(0); // 当前选中的文件索引
  const [leftPanelTab, setLeftPanelTab] = useState<"input" | "output">("input"); // 左侧面板的顶层 tab
  const [outputFile, setOutputFile] = useState<string | null>(null); // 当前选中的处理结果文件

  const fileInputRef = useRef<HTMLInputElement>(null);

  // 获取所有成功上传的文件 IDs
  const fileIds = fileItems.filter(item => item.status === "success" && item.fileId).map(item => item.fileId!);

  const { messages, resetChat, sendMessage } = useExcelChat({
    onStart: () => {
      setQuery("");
    },
    onExecuteSuccess: (newOutputFile) => {
      setLeftPanelTab("output");
      setOutputFile(newOutputFile);
    },
  });


  // 确保选中的文件索引始终有效
  useEffect(() => {
    if (fileItems.length > 0 && selectedFileIndex >= fileItems.length) {
      setSelectedFileIndex(0);
    }
  }, [fileItems.length, selectedFileIndex]);

  useEffect(() => {
    // 如果没有输出文件但当前在"处理结果" tab，切换回"输入文件"
    if (!outputFile && leftPanelTab === "output") {
      setLeftPanelTab("input");
    }
  }, [outputFile, leftPanelTab]);

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
      setLeftPanelTab("output");
    }
  }, [messages]);

  // 上传单个文件
  const uploadSingleFile = async (fileItem: FileItem, index: number) => {
    // 设置状态为上传中
    setFileItems(prev => {
      const updated = [...prev];
      updated[index] = { ...fileItem, status: "uploading", progress: 0 };
      return updated;
    });

    try {
      const result = await uploadFiles([fileItem.file], (progress) => {
        // 更新进度
        setFileItems(prev => {
          const updated = [...prev];
          updated[index] = { ...updated[index], progress };
          return updated;
        });
      });

      // 上传成功
      if (result && result.length > 0) {
        setFileItems(prev => {
          const updated = [...prev];
          updated[index] = {
            ...updated[index],
            status: "success",
            progress: 100,
            fileId: result[0].id,
            path: result[0].path,
          };
          return updated;
        });
      }
    } catch (err) {
      // 上传失败
      const errorMessage = err instanceof Error ? err.message : "上传失败";
      setFileItems(prev => {
        const updated = [...prev];
        updated[index] = {
          ...updated[index],
          status: "error",
          error: errorMessage,
        };
        return updated;
      });
    }
  };

  // 上传多个文件
  const uploadFilesBatch = async (files: File[]) => {
    // 创建文件项，初始状态为上传中
    const newFileItems: FileItem[] = files.map(file => ({
      file,
      status: "uploading" as FileUploadStatus,
      progress: 0,
    }));

    setFileItems(prev => [...prev, ...newFileItems]);

    // 逐个上传文件
    const startIndex = fileItems.length;
    for (let i = 0; i < files.length; i++) {
      await uploadSingleFile(newFileItems[i], startIndex + i);
    }
  };

  // 重试上传文件
  const retryUploadFile = async (index: number) => {
    const fileItem = fileItems[index];
    if (fileItem) {
      await uploadSingleFile(fileItem, index);
    }
  };

  // 删除文件
  const removeFile = (index: number) => {
    const fileItem = fileItems[index];
    // 上传中的文件不能删除
    if (fileItem?.status === "uploading") {
      return;
    }

    setFileItems(prev => {
      const updated = prev.filter((_, idx) => idx !== index);
      // 如果删除的是当前选中的文件，切换到前一个文件
      if (index === selectedFileIndex && updated.length > 0) {
        setSelectedFileIndex(Math.max(0, index - 1));
      }
      return updated;
    });
  };

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    const excelFiles = selectedFiles.filter(
      (f) => f.name.endsWith(".xlsx") || f.name.endsWith(".xls")
    );

    if (excelFiles.length > 0) {
      await uploadFilesBatch(excelFiles);
    }
    // 清空 input，允许重新选择相同文件
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const droppedFiles = Array.from(e.dataTransfer.files);
    const excelFiles = droppedFiles.filter(
      (f) => f.name.endsWith(".xlsx") || f.name.endsWith(".xls")
    );
    if (excelFiles.length > 0) {
      await uploadFilesBatch(excelFiles);
    }
  };

  const onPasteFiles = async (files: File[], e: React.ClipboardEvent) => {
    const excelFiles = files.filter(
      (f) => f.name.endsWith(".xlsx") || f.name.endsWith(".xls")
    );

    if (excelFiles.length > 0) {
      e.preventDefault();
      await uploadFilesBatch(excelFiles);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleUploadAreaClick = () => {
    fileInputRef.current?.click();
  };



  return (
    <div className="h-full flex flex-col bg-[#FAFAFA]">

      {/* Header */}
      <AppHeader
        onNewChat={() => {
          setFileItems([]);
          resetChat();
          setSelectedFileIndex(0);
          setLeftPanelTab("input");
          setOutputFile(null);
        }}
      />


      <main className="flex-1 h-0 flex w-full overflow-hidden">
        <ResizablePanelGroup direction="horizontal" className="h-full w-full">
          {/* left: Excel Preview */}
          <ResizablePanel defaultSize={60}>
            <div className="border-r border-gray-200 bg-white flex flex-col overflow-hidden flex-1 h-full">
              {/* 顶层 Tab 切换 */}
              <div className="border-b border-gray-200 flex">
                <button
                  onClick={() => setLeftPanelTab("input")}
                  className={cn(
                    "px-6 py-3 text-sm font-medium border-b-2 transition-colors",
                    leftPanelTab === "input"
                      ? "border-emerald-600 text-emerald-900 bg-emerald-50"
                      : "border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50"
                  )}
                >
                  输入文件
                </button>
                <button
                  onClick={() => setLeftPanelTab("output")}
                  className={cn(
                    "px-6 py-3 text-sm font-medium border-b-2 transition-colors",
                    leftPanelTab === "output"
                      ? "border-emerald-600 text-emerald-900 bg-emerald-50"
                      : "border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50",
                    !outputFile && "opacity-50 cursor-not-allowed"
                  )}
                  disabled={!outputFile}
                >
                  处理结果
                </button>
              </div>

              {/* 输入文件 Tab 内容 */}
              {leftPanelTab === "input" && (
                <>
                  {/* 文件 Tab 列表 */}
                  <div className="border-b border-gray-200 overflow-x-auto">
                    <div className="flex min-w-0">
                      {fileItems.map((fileItem, idx) => (
                        <div
                          key={idx}
                          className={cn(
                            "flex items-center border-b-2 transition-colors",
                            selectedFileIndex === idx
                              ? "border-emerald-600 bg-emerald-50"
                              : "border-transparent"
                          )}
                        >
                          <button
                            onClick={() => setSelectedFileIndex(idx)}
                            className={cn(
                              "px-4 py-3 flex items-center gap-2 whitespace-nowrap min-w-0 flex-1",
                              selectedFileIndex === idx
                                ? "text-emerald-900"
                                : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
                            )}
                          >
                            <FileSpreadsheet className="w-4 h-4 shrink-0" />
                            <span className="text-sm font-medium truncate">{fileItem.file.name}</span>
                            {fileItem.status === "uploading" && (
                              <Loader2 className="w-3 h-3 shrink-0 animate-spin ml-1" />
                            )}
                            {fileItem.status === "success" && (
                              <Check className="w-3 h-3 shrink-0 text-emerald-600 ml-1" />
                            )}
                            {fileItem.status === "error" && (
                              <X className="w-3 h-3 shrink-0 text-red-500 ml-1" />
                            )}
                          </button>
                          {/* 删除按钮 - 上传中的文件不显示 */}
                          {fileItem.status !== "uploading" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                removeFile(idx);
                              }}
                              className="px-2 py-3 text-gray-400 hover:text-red-500 transition-colors shrink-0"
                              title="删除文件"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* 预览内容区域 */}
                  <div className="flex-1 overflow-y-auto p-4 h-0">
                    {fileItems[selectedFileIndex] && (() => {
                      const currentFile = fileItems[selectedFileIndex];
                      return (
                        <div className="h-full">
                          {/* 上传中状态 */}
                          {currentFile.status === "uploading" && (
                            <div className="space-y-2">
                              <div className="flex items-center gap-2 text-sm text-gray-700">
                                <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
                                <span>正在上传...</span>
                              </div>
                              <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                  className="absolute top-0 left-0 h-full bg-emerald-500 transition-all duration-300 ease-out"
                                  style={{ width: `${currentFile.progress}%` }}
                                />
                              </div>
                              <p className="text-xs text-gray-500">{currentFile.progress}%</p>
                            </div>
                          )}

                          {/* 上传成功状态 */}
                          {currentFile.status === "success" && (
                            <ExcelPreview
                              className="w-full h-full"
                              fileUrl={`/api${currentFile.path!}`}
                            />
                          )}

                          {/* 上传失败状态 */}
                          {currentFile.status === "error" && (
                            <div className="space-y-3">
                              <div className="flex items-center gap-2 text-sm text-red-700">
                                <X className="w-4 h-4" />
                                <span>上传失败</span>
                              </div>
                              <div className="text-xs text-gray-600 bg-red-50 border border-red-200 rounded p-3">
                                {currentFile.error || "上传失败，请重试"}
                              </div>
                              <Button
                                onClick={() => retryUploadFile(selectedFileIndex)}
                                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white"
                                size="sm"
                              >
                                <RefreshCw className="w-4 h-4 mr-2" />
                                重试上传
                              </Button>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                </>
              )}

              {/* 处理结果 Tab 内容 */}
              {leftPanelTab === "output" && (
                <>
                  {/* 预览内容区域 */}
                  <div className="flex-1 overflow-y-auto p-4 h-0">
                    {outputFile && (
                      <ExcelPreview
                        className="w-full h-full"
                        fileUrl={`/api/${outputFile}`}
                      />
                    )}
                    {!outputFile && (
                      <div className="flex items-center justify-center h-full text-gray-500">
                        <div className="text-center">
                          <FileSpreadsheet className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                          <p className="text-sm">暂无处理结果</p>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle />
          {/* right: LLM Chat */}
          <ResizablePanel defaultSize={40}>
            <div className="h-full flex flex-col w-full">
              <div className="flex-1 overflow-y-auto px-6 py-4">
                <MessageList
                  messages={messages}
                  emptyPlaceholder={
                    <div className="flex-1 flex flex-col px-6 mt-2 gap-6 overflow-y-auto">
                      <div className="flex-1 flex flex-col gap-4">
                        {/* Upload Area */}
                        <div
                          onClick={handleUploadAreaClick}
                          onDragOver={handleDragOver}
                          onDrop={handleDrop}
                          className="bg-white border-2 border-dashed border-gray-300 rounded-xl p-12 flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-emerald-400 transition-colors min-h-[320px]"
                        >
                          <Cloud className="w-16 h-16 text-gray-400" />
                          <p className="text-gray-600 text-center">
                            点击此处或复制、拖拽文件到此处上传文件
                          </p>
                        </div>

                        {/* Upload Instructions */}
                        <div className="bg-white rounded-lg p-4 border border-gray-200">
                          <div className="flex items-start gap-2">
                            <Info className="w-5 h-5 text-gray-500 mt-0.5 shrink-0" />
                            <div>
                              <h3 className="font-medium text-gray-900 mb-2">上传文件要求说明</h3>
                              <ul className="text-sm text-gray-600 space-y-1">
                                <li className="flex items-center gap-2">
                                  <span className="text-emerald-600">✓</span>
                                  支持上传 csv、xls、xlsx 格式文件
                                </li>
                                <li className="flex items-center gap-2">
                                  <span className="text-emerald-600">✓</span>
                                  支持多文件上传
                                </li>
                              </ul>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  }
                />
              </div>

              {/* input */}
              <div className="w-full p-6">
                <ChatInput
                  text={query}
                  onTextChange={setQuery}
                  onSubmit={() => sendMessage({ text: query, files: fileIds })}
                  onPasteFiles={onPasteFiles}
                  placeholder={fileIds.length > 0 ? "请输入对于上传文件的任何分析处理需求" : "请先上传 Excel 文件..."}
                />
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </main>

      <input
        multiple
        type="file"
        className="hidden"
        ref={fileInputRef}
        onChange={onFileChange}
      />
    </div>
  );
};

export default LLMChatPage;
