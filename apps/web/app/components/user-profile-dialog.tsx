import NiceModal, { useModal } from '@ebay/nice-modal-react';
import type { FormEvent } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { updateUser } from "~/api/auth";
import { useAuthStore } from "~/stores/auth";
import { UserProfileForm } from "~/components/user-profile-form";
import { Button } from './ui/button';

export const UserProfileDialog = NiceModal.create(() => {
  const modal = useModal();
  const { user, setUser } = useAuthStore();

  if (!user) {
    return null;
  }

  const handleClose = () => {
    modal.hide().then(() => {
      modal.remove();
    });
  };

  const onSubmit = async (
    values: {
      avatar?: string;
      username?: string;
      email?: string;
    },
    _event: FormEvent<HTMLFormElement>,
  ) => {
    try {
      const updated = await updateUser({
        username: values.username || undefined,
        avatar: values.avatar || undefined,
      });
      setUser(updated);
      handleClose();
    } catch (error) {
      console.error("更新用户信息失败:", error);
      // TODO: 接入全局提示
    }
  };

  return (
    <Dialog
      open={modal.visible}
      onOpenChange={(open) => {
        if (!open) {
          handleClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>个人信息</DialogTitle>
        </DialogHeader>
        <UserProfileForm
          initialValue={{
            avatar: user.avatar ?? undefined,
            username: user.username ?? undefined,
            email: user.accounts.email ?? undefined,
          }}
          onSubmit={onSubmit}
          footer={
            <DialogFooter className="pt-2 justify-center!">
              <DialogClose asChild>
                <Button type="button" variant="outline" size="sm">
                  取消
                </Button>
              </DialogClose>
              <Button type="submit" size="sm">
                保存
              </Button>
            </DialogFooter>
          }
        />
      </DialogContent>
    </Dialog>
  );
});

export default UserProfileDialog;

