import { useForm, type SubmitHandler } from "react-hook-form";
import type { FormEvent, ReactNode } from "react";

import { Field, FieldContent, FieldTitle } from "~/components/ui/field";
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

      <Field>
        <FieldTitle>用户名</FieldTitle>
        <FieldContent>
          <input
            {...register("username")}
            className="block w-full rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-900 shadow-xs outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200"
            placeholder={initialValue.username}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldTitle>邮箱</FieldTitle>
        <FieldContent>
          <input
            type="email"
            {...register("email")}
            className="block w-full rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-900 shadow-xs outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200"
            placeholder={initialValue.email}
          />
        </FieldContent>
      </Field>

      {footer && <div className="pt-1">{footer}</div>}
    </form>
  );
};

