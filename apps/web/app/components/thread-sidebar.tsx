import { toast } from 'sonner'
import { useState } from "react";
import { match, P } from "ts-pattern";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery } from '@tanstack/react-query'
import { MessageSquare, Plus, Trash2, Loader2, Clock } from "lucide-react";

import { Button } from "~/components/ui/button";

import { cn, formatRelativeTime } from "~/lib/utils";
import { deleteThread, getThreads } from '~/lib/api'

interface Props {
  isOpen: boolean;
  onClose?: () => void;
}

const ThreadSidebar = ({ isOpen, onClose }: Props) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const navigate = useNavigate();
  const params = useParams();

  const { data: threads, isLoading, refetch } = useQuery({
    queryKey: ['threads'],
    queryFn: () => getThreads()
  })

  const { mutateAsync: mutateThreadDelete } = useMutation({
    mutationFn: (threadId: string) => deleteThread(threadId),
    onMutate: async (threadId: string) => {
      setDeletingId(threadId)
    },
    onSuccess: (_, threadId) => {
      toast.success("删除成功")
      refetch()
      if (params.id === threadId) {
        navigate("/threads");
      }
    },
    onSettled: () => {
      setDeletingId(null)
    },
    onError: (error) => {
      toast.error("删除失败")
      console.error("删除失败:", error)
    }
  })

  const handleDelete = async (e: React.MouseEvent, threadId: string) => {
    e.preventDefault();
    e.stopPropagation();

    if (!confirm("确定要删除这个会话吗？")) {
      return;
    }

    await mutateThreadDelete(threadId);
  };

  const handleNewChat = () => {
    navigate("/threads");
    onClose?.();
  };

  return (
    <div
      className={cn(
        "fixed inset-y-0 left-0 z-50 w-80 bg-white border-r border-gray-200 transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0 h-full",
        isOpen ? "translate-x-0" : "-translate-x-full"
      )}
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="p-4 border-b border-gray-200">
          <Button
            onClick={handleNewChat}
            className="w-full gap-2 bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white"
            size="sm"
          >
            <Plus className="w-4 h-4" />
            新对话
          </Button>
        </div>

        {/* Thread List */}
        <div className="flex-1 overflow-y-auto">
          {match({ isLoading, threadCount: threads?.length })
            .with({ isLoading: true }, () => (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-600" />
              </div>
            ))
            .with({ isLoading: false, threadCount: 0 }, () => (
              <div className="p-6 text-center text-gray-500 h-full">
                <MessageSquare className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p className="text-sm">还没有会话</p>
                <p className="text-xs mt-1">开始一个新对话吧</p>
              </div>
            ))
            .with({ isLoading: false, }, () => (
              <div className="p-2">
                {threads?.map((thread) => {
                  const isActive = params.id === thread.id;

                  const displayTitle = match(thread)
                    .when(
                      (t) => t.title !== null && t.title !== "",
                      (t) => t.title!
                    )
                    .when(
                      (t) => t.turn_count > 0,
                      (t) => `会话 ${t.turn_count}`
                    )
                    .otherwise(() => "新会话");

                  const deleteButtonIcon = match(deletingId === thread.id)
                    .with(true, () => <Loader2 className="w-4 h-4 animate-spin" />)
                    .with(false, () => <Trash2 className="w-4 h-4" />)
                    .exhaustive();

                  return (
                    <Link
                      key={thread.id}
                      to={`/threads/${thread.id}`}
                      onClick={onClose}
                      className={cn(
                        "group relative flex items-start gap-3 p-3 rounded-lg mb-1 transition-colors border",
                        isActive
                          ? "bg-linear-to-r from-emerald-50 to-teal-50 border-emerald-200"
                          : "hover:bg-gray-50 border-transparent"
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <MessageSquare
                            className={cn(
                              "w-4 h-4 shrink-0",
                              isActive ? "text-emerald-600" : "text-gray-400"
                            )}
                          />
                          <h3
                            className={cn(
                              "text-sm font-medium truncate",
                              isActive ? "text-emerald-900" : "text-gray-900"
                            )}
                          >
                            {displayTitle}
                          </h3>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Clock className="w-3 h-3" />
                          <span>{formatRelativeTime(thread.updated_at)}</span>
                          {thread.turn_count > 0 && (
                            <>
                              <span>·</span>
                              <span>{thread.turn_count} 条消息</span>
                            </>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDelete(e, thread.id)}
                        className={cn(
                          "opacity-0 group-hover:opacity-100 p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-all shrink-0",
                          deletingId === thread.id && "opacity-100"
                        )}
                        title="删除会话"
                      >
                        {deleteButtonIcon}
                      </button>
                    </Link>
                  );
                })}
              </div>
            ))
            .exhaustive()}
        </div>
      </div>
    </div>
  );
}

export default ThreadSidebar;