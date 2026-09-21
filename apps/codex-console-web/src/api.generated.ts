export interface paths {
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session */
        get: operations["session_api_session_get"];
        put?: never;
        /** Login */
        post: operations["login_api_session_post"];
        /** Logout */
        delete: operations["logout_api_session_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/session/owh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login From Open Work Hub */
        post: operations["login_from_open_work_hub_api_session_owh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/codex/account": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Account */
        get: operations["account_api_codex_account_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/codex/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Models */
        get: operations["models_api_codex_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/codex/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Codex Login */
        post: operations["codex_login_api_codex_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/codex/threads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Threads */
        get: operations["threads_api_codex_threads_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Thread */
        post: operations["import_thread_api_tasks_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tasks */
        get: operations["tasks_api_tasks_get"];
        put?: never;
        /** New Task */
        post: operations["new_task_api_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Task Detail */
        get: operations["task_detail_api_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/attachments/{attachment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upload Attachment */
        put: operations["upload_attachment_api_tasks__task_id__attachments__attachment_id__put"];
        post?: never;
        /** Delete Attachment */
        delete: operations["delete_attachment_api_tasks__task_id__attachments__attachment_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Attachment List */
        get: operations["attachment_list_api_tasks__task_id__attachments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/attachments/{attachment_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Attachment */
        get: operations["download_attachment_api_tasks__task_id__attachments__attachment_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Document */
        put: operations["document_api_tasks__task_id__documents_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Message */
        post: operations["message_api_tasks__task_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/implement": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Implement */
        post: operations["implement_api_tasks__task_id__implement_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/steer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Steer */
        post: operations["steer_api_tasks__task_id__steer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/interrupt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Interrupt */
        post: operations["interrupt_api_tasks__task_id__interrupt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/recover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Recover */
        post: operations["recover_api_tasks__task_id__recover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/requests/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Answer */
        post: operations["answer_api_tasks__task_id__requests__request_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/changes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Changes */
        get: operations["changes_api_tasks__task_id__changes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/git": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Git Status */
        get: operations["git_status_api_tasks__task_id__git_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/diff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Diff */
        get: operations["diff_api_tasks__task_id__diff_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Events */
        get: operations["events_api_tasks__task_id__events_get"];
        put?: never;
        post?: never;
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
        /** AccountOut */
        AccountOut: {
            /** Connected */
            connected: boolean;
            /** Auth Type */
            auth_type?: string | null;
            /** Plan Type */
            plan_type?: string | null;
            /** Rate Limits */
            rate_limits?: {
                [key: string]: unknown;
            } | null;
            /** Error Code */
            error_code?: string | null;
        };
        /** Answer */
        Answer: {
            /** Decision */
            decision?: ("accept" | "decline" | "cancel") | null;
            /** Answers */
            answers?: {
                [key: string]: string[];
            } | null;
        };
        /** AttachmentLimits */
        AttachmentLimits: {
            /** File Bytes */
            file_bytes: number;
            /** Task Bytes */
            task_bytes: number;
            /** Files */
            files: number;
            /** Selection */
            selection: number;
        };
        /** AttachmentOut */
        AttachmentOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Size */
            size: number;
            /** Deleted */
            deleted: boolean;
        };
        /** ChangeOut */
        ChangeOut: {
            /** Path */
            path: string;
            /** Status */
            status: string;
            /** Old Path */
            old_path: string | null;
        };
        /** DeviceLoginOut */
        DeviceLoginOut: {
            /** Login Id */
            login_id: string;
            /** Verification Url */
            verification_url: string;
            /** User Code */
            user_code: string;
        };
        /** DiffOut */
        DiffOut: {
            /** Path */
            path: string;
            /** Binary */
            binary: boolean;
            /** Old */
            old: string;
            /** New */
            new: string;
        };
        /** DocumentInput */
        DocumentInput: {
            /** Kind */
            kind?: "plan" | null;
            /** Base Version */
            base_version: number;
            /** Body */
            body: string;
        };
        /** GitStatusOut */
        GitStatusOut: {
            /** Root */
            root: string;
            /** Branch */
            branch: string | null;
            /** Head */
            head: string | null;
            /** Detached */
            detached: boolean;
            /** Upstream */
            upstream: string | null;
            /** Ahead */
            ahead: number | null;
            /** Behind */
            behind: number | null;
            /** Staged */
            staged: number;
            /** Unstaged */
            unstaged: number;
            /** Untracked */
            untracked: number;
            /** Conflicts */
            conflicts: number;
            /** Changed */
            changed: number;
            /** Checked At */
            checked_at: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** Implement */
        Implement: {
            /** Model */
            model?: string | null;
            /** Effort */
            effort?: string | null;
            /**
             * Permissions
             * @default ask
             * @enum {string}
             */
            permissions: "ask" | "yolo";
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            /** Revision Id */
            revision_id?: number | null;
            /**
             * Text
             * @default
             */
            text: string;
            /** Attachment Ids */
            attachment_ids?: string[];
        };
        /** ImportThread */
        ImportThread: {
            /** Thread Id */
            thread_id: string;
            /**
             * Confirm Inactive
             * @constant
             */
            confirm_inactive: true;
        };
        /** LoginInput */
        LoginInput: {
            /** Password */
            password: string;
        };
        /** Message */
        Message: {
            /** Model */
            model?: string | null;
            /** Effort */
            effort?: string | null;
            /**
             * Permissions
             * @default ask
             * @enum {string}
             */
            permissions: "ask" | "yolo";
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            /**
             * Text
             * @default
             */
            text: string;
            /**
             * Stage
             * @default plan
             * @constant
             */
            stage: "plan";
            /** Attachment Ids */
            attachment_ids?: string[];
        };
        /** MessageBody */
        MessageBody: {
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            /**
             * Text
             * @default
             */
            text: string;
            /**
             * Stage
             * @default plan
             * @constant
             */
            stage: "plan";
            /** Attachment Ids */
            attachment_ids?: string[];
        };
        /** ModelOut */
        ModelOut: {
            /** Model */
            model: string;
            /** Name */
            name: string;
            /** Is Default */
            is_default: boolean;
            /** Default Effort */
            default_effort: string;
            /** Efforts */
            efforts: string[];
        };
        /** NewTask */
        NewTask: {
            /** Title */
            title: string;
        };
        /** Ok */
        Ok: {
            /**
             * Ok
             * @default true
             */
            ok: boolean;
        };
        /** OwhSessionInput */
        OwhSessionInput: {
            /** Issuer */
            issuer: string;
            /** Code */
            code: string;
        };
        /** Recover */
        Recover: {
            /**
             * Confirm Workspace
             * @default false
             */
            confirm_workspace: boolean;
        };
        /** RequestOut */
        RequestOut: {
            /** Id */
            id: string;
            /** Method */
            method: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
        };
        /** RevisionOut */
        RevisionOut: {
            /** Id */
            id: number;
            /** Kind */
            kind: string;
            /** Version */
            version: number;
            /** Body */
            body: string;
            /** Created At */
            created_at: string;
        };
        /** SessionOut */
        SessionOut: {
            /** Authenticated */
            authenticated: boolean;
        };
        /** TaskDetail */
        TaskDetail: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Stage */
            stage: string;
            /** Status */
            status: string;
            /** Thread Id */
            thread_id: string | null;
            /** Turn Id */
            turn_id: string | null;
            /** Root */
            root: string;
            /** Isolated */
            isolated: boolean;
            /** Approved Revision */
            approved_revision: number | null;
            /** Error Code */
            error_code: string | null;
            /** Updated At */
            updated_at: string;
            /** Model */
            model?: string | null;
            /** Effort */
            effort?: string | null;
            /**
             * Permissions
             * @default read-only
             * @enum {string}
             */
            permissions: "read-only" | "ask" | "yolo";
            /** Progress */
            progress?: {
                [key: string]: unknown;
            } | null;
            /** Failed Request Text */
            failed_request_text?: string | null;
            /** Revisions */
            revisions: components["schemas"]["RevisionOut"][];
            /** Items */
            items: {
                [key: string]: unknown;
            }[];
            /** History Truncated */
            history_truncated: boolean;
            /** Requests */
            requests: components["schemas"]["RequestOut"][];
            /** Event Id */
            event_id: number;
            /** Attachments */
            attachments: components["schemas"]["AttachmentOut"][];
            attachment_limits: components["schemas"]["AttachmentLimits"];
        };
        /** TaskOut */
        TaskOut: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Stage */
            stage: string;
            /** Status */
            status: string;
            /** Thread Id */
            thread_id: string | null;
            /** Turn Id */
            turn_id: string | null;
            /** Root */
            root: string;
            /** Isolated */
            isolated: boolean;
            /** Approved Revision */
            approved_revision: number | null;
            /** Error Code */
            error_code: string | null;
            /** Updated At */
            updated_at: string;
            /** Model */
            model?: string | null;
            /** Effort */
            effort?: string | null;
            /**
             * Permissions
             * @default read-only
             * @enum {string}
             */
            permissions: "read-only" | "ask" | "yolo";
            /** Progress */
            progress?: {
                [key: string]: unknown;
            } | null;
        };
        /** ThreadPage */
        ThreadPage: {
            /** Items */
            items: components["schemas"]["ThreadSummary"][];
            /** Cursor */
            cursor: string | null;
        };
        /** ThreadSummary */
        ThreadSummary: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Preview */
            preview: string;
            /** Updated At */
            updated_at: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
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
    health_healthz_get: {
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
                    "application/json": components["schemas"]["Ok"];
                };
            };
        };
    };
    session_api_session_get: {
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
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
        };
    };
    login_api_session_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
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
    logout_api_session_delete: {
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
                    "application/json": components["schemas"]["Ok"];
                };
            };
        };
    };
    login_from_open_work_hub_api_session_owh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwhSessionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
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
    account_api_codex_account_get: {
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
                    "application/json": components["schemas"]["AccountOut"];
                };
            };
        };
    };
    models_api_codex_models_get: {
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
                    "application/json": components["schemas"]["ModelOut"][];
                };
            };
        };
    };
    codex_login_api_codex_login_post: {
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
                    "application/json": components["schemas"]["DeviceLoginOut"];
                };
            };
        };
    };
    threads_api_codex_threads_get: {
        parameters: {
            query?: {
                search?: string;
                cursor?: string | null;
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
                    "application/json": components["schemas"]["ThreadPage"];
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
    import_thread_api_tasks_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportThread"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    tasks_api_tasks_get: {
        parameters: {
            query?: {
                search?: string;
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
                    "application/json": components["schemas"]["TaskOut"][];
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
    new_task_api_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NewTask"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    task_detail_api_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["TaskDetail"];
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
    upload_attachment_api_tasks__task_id__attachments__attachment_id__put: {
        parameters: {
            query?: never;
            header: {
                "x-file-name": string;
            };
            path: {
                task_id: string;
                attachment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/octet-stream": string;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttachmentOut"];
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
    delete_attachment_api_tasks__task_id__attachments__attachment_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
                attachment_id: string;
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
                    "application/json": components["schemas"]["Ok"];
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
    attachment_list_api_tasks__task_id__attachments_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["AttachmentOut"][];
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
    download_attachment_api_tasks__task_id__attachments__attachment_id__download_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
                attachment_id: string;
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
    document_api_tasks__task_id__documents_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DocumentInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    message_api_tasks__task_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Message"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    implement_api_tasks__task_id__implement_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Implement"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    steer_api_tasks__task_id__steer_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    interrupt_api_tasks__task_id__interrupt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["Ok"];
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
    recover_api_tasks__task_id__recover_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Recover"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    answer_api_tasks__task_id__requests__request_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Answer"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskDetail"];
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
    changes_api_tasks__task_id__changes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["ChangeOut"][];
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
    git_status_api_tasks__task_id__git_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["GitStatusOut"];
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
    diff_api_tasks__task_id__diff_get: {
        parameters: {
            query: {
                path: string;
            };
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["DiffOut"];
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
    events_api_tasks__task_id__events_get: {
        parameters: {
            query?: {
                after?: number;
            };
            header?: never;
            path: {
                task_id: string;
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
}
