import { Clock, Copy } from "lucide-react";
import FileItemBadge from "./file-item-badge";

import type { UserMessageFile } from "~/hooks/use-excel-chat";
import type { UserMessage as UserMessageType } from "../types";

interface Props {
  message: UserMessageType;
  onClickFile?: (messageId: string, file: UserMessageFile) => void
}

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp);
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 || 12;
  const displayMinutes = minutes.toString().padStart(2, '0');
  return `${displayHours}:${displayMinutes} ${ampm}`;
};

const UserMessage = ({ message, onClickFile }: Props) => {
  return (
    <div className="relative p-4 flex flex-col items-end gap-1 group">
      {/* 用户头像 */}
      <div className="w-8 h-8 rounded-full border-2 border-white overflow-hidden bg-gray-100">
        <img src={message.avatar} className="w-full h-full object-cover" />
      </div>

      {/* 消息气泡 */}
      <div className="relative rounded-[16px] px-4 py-3 bg-gray-200 text-gray-800 max-w-[80%] ml-auto">
        <svg
          width={16}
          height={16}
          fill="var(--v0-gray-200)"
          className="absolute -top-[6px] right-0"
          style={{
            transitionProperty: "scale,fill",
            transitionDuration: "300ms",
            transitionTimingFunction: "cubic-bezier(.31,.1,.08,.96)",
            transitionDelay: "0ms",
            willChange: "fill",
          }}
        >
          <path d="M0 6.194c8 0 12-2.065 16-6.194 0 6.71 0 13.5-6 16L0 6.194Z" />
        </svg>
        <p className="whitespace-pre-wrap text-base leading-relaxed">
          {message.content}
        </p>
      </div>


      {/* 文件列表 */}
      {Boolean(message.files?.length) && (
        <div className="flex gap-1 mt-1 pr-1 justify-end">
          {message.files?.map(file => (
            <FileItemBadge
              key={file.id}
              file={file}
              onClick={() => onClickFile?.(message.id, file)}
            />
          ))}
        </div>
      )}

      {/* 消息元数据 - 时间戳和操作图标 */}
      <div className="flex items-center gap-3 justify-end mt-2 pr-2">
        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100">
          <div className="flex items-center gap-1 text-xs text-gray-500 ">
            <Clock className="w-3.5 h-3.5" />
            <span>{formatTime(message.created)}</span>
          </div>
        </div>

        <button className="text-gray-500 hover:text-gray-700 transition-colors p-1 cursor-pointer">
          <Copy className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

export default UserMessage