import { useForm, type SubmitHandler } from "react-hook-form";
import type { FormEvent, ReactNode } from "react";

import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { UserAvatarField } from "~/components/user-avatar-field";

type UserProfileFormValues = {
  avatar?: string;
  username?: string;
  email?: string;
};

type UserProfileFormProps = {
  footer?: ReactNode;
  initialValue: UserProfileFormValues;
  onSubmit: (values: UserProfileFormValues, event: FormEvent<HTMLFormElement>) => void | Promise<void>;
};

export const UserProfileForm = ({ footer, initialValue, onSubmit }: UserProfileFormProps) => {
  const { register, handleSubmit, setValue, watch } = useForm<UserProfileFormValues>({
    defaultValues: {
      avatar: initialValue.avatar ?? "",
      username: initialValue.username ?? "",
      email: initialValue.email ?? "",
    },
  });

  const avatarUrl = watch("avatar") ?? "";

  const onValid: SubmitHandler<UserProfileFormValues> = async (values, event) => {
    await onSubmit(
      {
        username: values.username || undefined,
        avatar: values.avatar || undefined,
        email: values.email || undefined,
      },
      event as FormEvent<HTMLFormElement>,
    );
  };

  return (
    <form className="space-y-4 text-sm" onSubmit={handleSubmit(onValid)}>
      <UserAvatarField
        value={avatarUrl}
        onChange={(url) => setValue("avatar", url, { shouldDirty: true })}
      />

      <div className="flex items-center gap-2">
        <Label htmlFor="user-profile-username" className="shrink-0 w-12">用户名</Label>
        <Input
          id="user-profile-username"
          className="flex-1"
          {...register("username")}
          placeholder={initialValue.username}
        />
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="user-profile-email" className="shrink-0 w-12">邮箱</Label>
        <Input
          id="user-profile-email"
          type="email"
          readOnly
          aria-readonly="true"
          {...register("email")}
          className="bg-muted text-muted-foreground flex-1"
          placeholder={initialValue.email}
        />
      </div>

      {footer && <div className="pt-1">{footer}</div>}
    </form>
  );
};

