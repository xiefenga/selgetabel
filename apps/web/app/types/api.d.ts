/* eslint-disable */

export interface paths {
    "/excel/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 上传 Excel 文件
         * @description 上传一个或多个 Excel 文件，系统会自动解析表结构。每个文件会获得独立的 file_id。
         */
        post: operations["upload_excel_files_excel_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/excel/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 处理 Excel 需求
         * @description 使用自然语言描述数据处理需求，LLM 会自动理解并执行相应操作。
         */
        post: operations["process_excel_chat_excel_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/threads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 获取线程列表
         * @description 获取当前用户的所有线程列表
         */
        get: operations["get_threads_threads_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/threads/{thread_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 获取线程详情
         * @description 获取指定线程的详细信息，包含所有消息
         */
        get: operations["get_thread_detail_threads__thread_id__get"];
        put?: never;
        post?: never;
        /**
         * 删除线程
         * @description 删除指定的线程
         */
        delete: operations["delete_thread_threads__thread_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 用户注册
         * @description 用户注册
         */
        post: operations["register_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 用户登录
         * @description 用户登录，token 通过 cookie 返回
         */
        post: operations["login_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 刷新访问令牌
         * @description 刷新访问令牌，从 cookie 读取 refresh_token，新的 access_token 通过 cookie 返回
         */
        post: operations["refresh_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 用户登出
         * @description 用户登出，从 cookie 读取 refresh_token，并清除所有认证 cookie
         */
        post: operations["logout_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 获取当前用户信息
         * @description 获取当前用户信息
         */
        get: operations["get_current_user_info_auth_me_get"];
        /**
         * 更新用户信息
         * @description 更新用户信息
         */
        put: operations["update_user_info_auth_me_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * 修改密码
         * @description 修改密码
         */
        put: operations["change_password_auth_password_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/bind-account": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 绑定新账户
         * @description 绑定新的登录账户
         */
        post: operations["bind_account_auth_bind_account_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AccountInfo
         * @description 账户信息
         */
        AccountInfo: {
            /**
             * Email
             * @description 登录邮箱
             */
            email: string;
        };
        /** ApiResponse[List[ThreadListItem]] */
        ApiResponse_List_ThreadListItem__: {
            /**
             * Code
             * @description 响应状态码，0 表示成功，非 0 表示失败
             * @example 0
             * @example 400
             * @example 500
             */
            code: number;
            /**
             * Data
             * @description 响应数据
             */
            data?: components["schemas"]["ThreadListItem"][] | null;
            /**
             * Msg
             * @description 响应消息
             * @example 成功
             * @example 请上传文件
             */
            msg: string;
        };
        /** ApiResponse[List[UploadItem]] */
        ApiResponse_List_UploadItem__: {
            /**
             * Code
             * @description 响应状态码，0 表示成功，非 0 表示失败
             * @example 0
             * @example 400
             * @example 500
             */
            code: number;
            /**
             * Data
             * @description 响应数据
             */
            data?: components["schemas"]["UploadItem"][] | null;
            /**
             * Msg
             * @description 响应消息
             * @example 成功
             * @example 请上传文件
             */
            msg: string;
        };
        /** ApiResponse[NoneType] */
        ApiResponse_NoneType_: {
            /**
             * Code
             * @description 响应状态码，0 表示成功，非 0 表示失败
             * @example 0
             * @example 400
             * @example 500
             */
            code: number;
            /**
             * Data
             * @description 响应数据
             */
            data?: null;
            /**
             * Msg
             * @description 响应消息
             * @example 成功
             * @example 请上传文件
             */
            msg: string;
        };
        /** ApiResponse[ThreadDetail] */
        ApiResponse_ThreadDetail_: {
            /**
             * Code
             * @description 响应状态码，0 表示成功，非 0 表示失败
             * @example 0
             * @example 400
             * @example 500
             */
            code: number;
            /** @description 响应数据 */
            data?: components["schemas"]["ThreadDetail"] | null;
            /**
             * Msg
             * @description 响应消息
             * @example 成功
             * @example 请上传文件
             */
            msg: string;
        };
        /** ApiResponse[UserInfo] */
        ApiResponse_UserInfo_: {
            /**
             * Code
             * @description 响应状态码，0 表示成功，非 0 表示失败
             * @example 0
             * @example 400
             * @example 500
             */
            code: number;
            /** @description 响应数据 */
            data?: components["schemas"]["UserInfo"] | null;
            /**
             * Msg
             * @description 响应消息
             * @example 成功
             * @example 请上传文件
             */
            msg: string;
        };
        /**
         * BindAccountRequest
         * @description 绑定新账户请求
         */
        BindAccountRequest: {
            /**
             * Account Id
             * @description 账户标识（邮箱、手机号等）
             */
            account_id: string;
            /**
             * Provider Id
             * @description 登录方式（credentials, github, google 等）
             */
            provider_id: string;
            /**
             * Password
             * @description 密码（credentials 时必填）
             */
            password?: string | null;
        };
        /** Body_upload_excel_files_excel_upload_post */
        Body_upload_excel_files_excel_upload_post: {
            /** Files */
            files: string[];
        };
        /**
         * ChangePasswordRequest
         * @description 修改密码请求
         */
        ChangePasswordRequest: {
            /**
             * Old Password
             * @description 旧密码
             */
            old_password: string;
            /**
             * New Password
             * @description 新密码
             */
            new_password: string;
        };
        /**
         * ChatRequest
         * @description Excel 处理请求
         */
        ChatRequest: {
            /**
             * Query
             * @description 数据处理需求的自然语言描述
             */
            query: string;
            /**
             * File Ids
             * @description 上传文件返回的 file_id 列表（UUID 字符串），支持多个文件
             */
            file_ids: string[];
            /**
             * Thread Id
             * @description 线程 ID（可选，用于继续会话）
             */
            thread_id?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * LoginParams
         * @description 用户登录请求
         */
        LoginParams: {
            /**
             * Account
             * @description 登录账户（邮箱或用户名）
             */
            account: string;
            /**
             * Password
             * @description 密码
             */
            password: string;
        };
        /**
         * RegisterParams
         * @description 用户注册请求
         */
        RegisterParams: {
            /**
             * Username
             * @description 用户名
             */
            username: string;
            /**
             * Email
             * Format: email
             * @description 邮箱地址
             */
            email: string;
            /**
             * Password
             * @description 密码
             */
            password: string;
        };
        /**
         * ThreadDetail
         * @description 线程详情
         */
        ThreadDetail: {
            /** Id */
            id: string;
            /** Title */
            title: string | null;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Turns
             * @description 消息列表
             */
            turns?: {
                [key: string]: unknown;
            }[];
        };
        /**
         * ThreadListItem
         * @description 线程列表项
         */
        ThreadListItem: {
            /** Id */
            id: string;
            /** Title */
            title: string | null;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Turn Count
             * @description 消息数量
             * @default 0
             */
            turn_count?: number;
        };
        /**
         * UpdateUserRequest
         * @description 更新用户信息请求
         */
        UpdateUserRequest: {
            /**
             * Username
             * @description 用户名
             */
            username?: string | null;
            /**
             * Avatar
             * @description 头像 URL
             */
            avatar?: string | null;
        };
        /**
         * UploadItem
         * @description 上传文件项
         */
        UploadItem: {
            /**
             * Id
             * @description 文件唯一标识
             * @example abc123def456
             */
            id: string;
            /**
             * Path
             * @description 文件路径
             * @example /uploads/abc123def456/filename.xlsx
             */
            path: string;
            /**
             * Table
             * @description 表名
             * @example orders
             */
            table: string;
            /**
             * Schema
             * @description 表结构，格式: {列字母: 列名}
             * @example {
             *       "A": "订单ID",
             *       "B": "客户名称",
             *       "C": "金额"
             *     }
             */
            schema: {
                [key: string]: string;
            };
        };
        /**
         * UserInfo
         * @description 用户信息响应
         */
        UserInfo: {
            /**
             * Id
             * Format: uuid
             * @description 用户 ID
             */
            id: string;
            /**
             * Username
             * @description 用户名
             */
            username: string;
            /**
             * Avatar
             * @description 头像 URL
             */
            avatar?: string | null;
            /**
             * Status
             * @description 状态：0 正常，1 禁用
             */
            status: number;
            /** @description 该用户所有登录账户 */
            accounts: components["schemas"]["AccountInfo"];
            /**
             * Roles
             * @description 角色代码列表
             */
            roles?: string[];
            /**
             * Permissions
             * @description 权限代码列表
             */
            permissions?: string[];
            /**
             * Created At
             * @description 创建时间
             */
            created_at: string;
            /**
             * Last Login At
             * @description 最后登录时间
             */
            last_login_at?: string | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    upload_excel_files_excel_upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_excel_files_excel_upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_List_UploadItem__"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    process_excel_chat_excel_chat_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_threads_threads_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_List_ThreadListItem__"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_thread_detail_threads__thread_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                thread_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ThreadDetail_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_thread_threads__thread_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                thread_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    register_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterParams"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginParams"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserInfo_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
        };
    };
    logout_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
        };
    };
    get_current_user_info_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserInfo_"];
                };
            };
        };
    };
    update_user_info_auth_me_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateUserRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserInfo_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    change_password_auth_password_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bind_account_auth_bind_account_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BindAccountRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
