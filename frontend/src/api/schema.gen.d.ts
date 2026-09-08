export interface paths {
    "/api/v1/batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Batches
         * @description 按 imported_at 倒序、batch_id 稳定排序列出批次（M3-04）。
         */
        get: operations["list_batches_api_v1_batches_get"];
        put?: never;
        /**
         * Create Batch
         * @description 上传一个标准 ZIP 新建批次；重复包 200 幂等命中（M3-04）。
         */
        post: operations["create_batch_api_v1_batches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Batch
         * @description 读取单个批次工作台视图（M3-04）。
         */
        get: operations["get_batch_api_v1_batches__batch_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Batch Run
         * @description 开始首次批量分析；无请求体，缺密钥时 503（M3-05）。
         */
        post: operations["start_batch_run_api_v1_batches__batch_id__runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Cases
         * @description 案例队列；服务端固定排序，不提供 sort_by（M3-04）。
         */
        get: operations["list_cases_api_v1_batches__batch_id__cases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/cases/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Case
         * @description 案例详情（M3-04）。
         */
        get: operations["get_case_api_v1_batches__batch_id__cases__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/cases/{case_id}/reruns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Rerun Case
         * @description 人工从头重跑单个案例；无请求体（M3-06）。
         */
        post: operations["rerun_case_api_v1_batches__batch_id__cases__case_id__reruns_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/cases/{case_id}/reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Submit Review
         * @description 提交人工确认；相同 submission_id 返回第一次保存结果（M3-07）。
         */
        post: operations["submit_review_api_v1_batches__batch_id__cases__case_id__reviews_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Evidence Content
         * @description 按作用域标识读取证据图片；不返回本机路径（M3-04）。
         */
        get: operations["get_evidence_content_api_v1_batches__batch_id__cases__case_id__evidence__evidence_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Health */
        get: operations["read_health_api_v1_health_get"];
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
        /**
         * ActionType
         * @description 动作目录 v1 的六个动作代码（规格第 7.3 节），与 config/action_catalog.v1.json 一一对应。
         * @enum {string}
         */
        ActionType: "EVIDENCE_CHECK" | "CUSTOMER_CONTACT" | "FULFILLMENT_ESCALATION" | "REPLACEMENT_RETURN_REFUND_CHECK" | "APOLOGY_COMPENSATION_RETENTION_REQUEST" | "NO_ACTION_MONITOR";
        /**
         * ActionView
         * @description 建议动作投影（规格 12.2；action_type 必须来自动作目录）。
         */
        ActionView: {
            action_type: components["schemas"]["ActionType"];
            /** Description */
            description: string;
            /** Reason */
            reason: string;
            /** Evidence Ids */
            evidence_ids?: string[];
            /** Precondition */
            precondition?: string | null;
        };
        /**
         * ApprovedReviewRequest
         * @description 直接通过：只携带共同字段，禁止另一份人工结果和审核原因。
         */
        ApprovedReviewRequest: {
            /**
             * Submission Id
             * Format: uuid
             */
            submission_id: string;
            /** Review Token */
            review_token: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            outcome: "APPROVED";
        };
        /**
         * AttributionFallbackCause
         * @description 归因无法可靠判断时的非原因兜底值。
         * @enum {string}
         */
        AttributionFallbackCause: "INSUFFICIENT_EVIDENCE";
        /**
         * BatchListView
         * @description 批次列表（规格 12.2，只含 items 与 total）。
         */
        BatchListView: {
            /** Items */
            items: components["schemas"]["BatchWorkspaceView"][];
            /** Total */
            total: number;
        };
        /**
         * BatchStatus
         * @description 批次业务状态（规格 7.2）。
         * @enum {string}
         */
        BatchStatus: "PENDING_ANALYSIS" | "ANALYZING" | "COMPLETED" | "COMPLETED_WITH_ERRORS";
        /**
         * BatchWorkspaceView
         * @description 批次工作台视图（规格 12.2）。
         */
        BatchWorkspaceView: {
            /** Batch Id */
            batch_id: string;
            /** Source Filename */
            source_filename: string;
            /** Is Mock */
            is_mock: boolean;
            status: components["schemas"]["BatchStatus"];
            /** Case Count */
            case_count: number;
            /** Evidence Count */
            evidence_count: number;
            /** Analysis Succeeded Count */
            analysis_succeeded_count: number;
            /** Error Count */
            error_count: number;
            /**
             * Imported At
             * Format: date-time
             */
            imported_at: string;
            /** Can Start Analysis */
            can_start_analysis: boolean;
            /** Analysis Unavailable Message */
            analysis_unavailable_message?: string | null;
        };
        /** Body_create_batch_api_v1_batches_post */
        Body_create_batch_api_v1_batches_post: {
            /**
             * File
             * @description 标准 ZIP 运行包
             */
            file: string;
        };
        /**
         * BusinessCause
         * @description 六个业务原因类别。
         * @enum {string}
         */
        BusinessCause: "LOGISTICS_FULFILLMENT" | "PRODUCT_ISSUE" | "RETURN_REFUND" | "SERVICE_COMMUNICATION" | "PRICE_OR_BENEFIT" | "OTHER";
        /**
         * BusinessError
         * @description 统一 JSON 错误结构（规格 12.4）。
         */
        BusinessError: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Object Type */
            object_type: string;
            /** Object Id */
            object_id?: string | null;
            stage: components["schemas"]["ProcessingErrorStage"];
            /** Next Action */
            next_action: string;
            /** Trace Id */
            trace_id?: string;
        };
        /**
         * CaseDetailView
         * @description 案例详情（规格 12.2）。
         */
        CaseDetailView: {
            /** Batch Id */
            batch_id: string;
            /** Case Id */
            case_id: string;
            /** Customer Display Id */
            customer_display_id: string;
            /** Is High Value */
            is_high_value: boolean;
            /** Customer Value Summary */
            customer_value_summary: string;
            status: components["schemas"]["CaseStatus"];
            intervention_level?: components["schemas"]["InterventionLevel"] | null;
            /** Risk Summary */
            risk_summary?: string | null;
            primary_cause?: components["schemas"]["CauseView"] | null;
            /** Actions */
            actions?: components["schemas"]["ActionView"][] | null;
            /** Communication Points */
            communication_points?: string[] | null;
            /** Uncertainty */
            uncertainty?: string[] | null;
            /** Missing Evidence */
            missing_evidence?: string[] | null;
            /** Cited Evidence */
            cited_evidence?: components["schemas"]["CitedEvidenceView"][] | null;
            /** Is Mock */
            is_mock: boolean;
            review_result?: components["schemas"]["ReviewResultView"] | null;
            processing_error?: components["schemas"]["CaseProcessingErrorView"] | null;
            /** Can Rerun */
            can_rerun: boolean;
            /** Can Review */
            can_review: boolean;
            /** Review Token */
            review_token?: string | null;
            review_options?: components["schemas"]["ReviewOptionsView"] | null;
        };
        /**
         * CaseProcessingErrorCode
         * @description 案例异步处理错误编号（规格 12.4），通过 processing_error 业务化展示。
         * @enum {string}
         */
        CaseProcessingErrorCode: "EVIDENCE_READ_FAILED" | "EVIDENCE_MEDIA_INVALID" | "MODEL_AUTH_FAILED" | "MODEL_TIMEOUT" | "MODEL_RATE_LIMITED" | "MODEL_RESPONSE_INVALID" | "MODEL_ATTEMPTS_EXHAUSTED" | "RESULT_PERSISTENCE_FAILED" | "APP_INTERRUPTED" | "UNEXPECTED_PROCESSING_ERROR";
        /**
         * CaseProcessingErrorView
         * @description 仅 status=PROCESSING_ERROR 案例出现的业务化处理异常（规格 12.2/12.4）。
         */
        CaseProcessingErrorView: {
            code: components["schemas"]["CaseProcessingErrorCode"];
            /** Message */
            message: string;
            stage: components["schemas"]["ProcessingErrorStage"];
            /** Next Action */
            next_action: string;
            /** Trace Id */
            trace_id: string;
        };
        /**
         * CaseQueueItemView
         * @description 案例队列条目（规格 12.2）；三个标记由当前有效结果或运行错误确定。
         */
        CaseQueueItemView: {
            /** Case Id */
            case_id: string;
            /** Customer Display Id */
            customer_display_id: string;
            /** Is High Value */
            is_high_value: boolean;
            /** Risk Summary */
            risk_summary?: string | null;
            intervention_level?: components["schemas"]["InterventionLevel"] | null;
            /** Priority Reason */
            priority_reason?: string | null;
            status: components["schemas"]["CaseStatus"];
            /** Has Evidence Conflict */
            has_evidence_conflict: boolean;
            /** Has Insufficient Evidence */
            has_insufficient_evidence: boolean;
            /** Has Modality Failure */
            has_modality_failure: boolean;
        };
        /**
         * CaseQueueView
         * @description 案例队列（规格 12.2，只含 items 与 total）。
         */
        CaseQueueView: {
            /** Items */
            items: components["schemas"]["CaseQueueItemView"][];
            /** Total */
            total: number;
        };
        /**
         * CaseStatus
         * @description 案例业务状态（规格 7.2）。
         * @enum {string}
         */
        CaseStatus: "PENDING_ANALYSIS" | "ANALYZING" | "PENDING_REVIEW" | "COMPLETED" | "PROCESSING_ERROR";
        /**
         * CauseView
         * @description 风险原因投影（规格 12.2；结构与 M2 归因 Cause 合同对齐）。
         */
        CauseView: {
            /** Category */
            category: components["schemas"]["BusinessCause"] | components["schemas"]["AttributionFallbackCause"];
            /** Explanation */
            explanation: string;
            /** Evidence Ids */
            evidence_ids?: string[];
            /** Counter Evidence Ids */
            counter_evidence_ids?: string[] | null;
            /** Uncertainty */
            uncertainty?: string | null;
        };
        /**
         * CitedEvidenceView
         * @description 当前结果实际引用的业务证据（规格 12.2）。
         *
         *     图片正文由 M4 用 batch_id、case_id、evidence_id 调用受控证据接口取得，
         *     不增加 content_url 字段。
         */
        CitedEvidenceView: {
            /** Evidence Id */
            evidence_id: string;
            modality: components["schemas"]["EvidenceModality"];
            /** Label */
            label: string;
            /** Text */
            text?: string | null;
            /** Summary */
            summary?: string | null;
        };
        /**
         * EvidenceModality
         * @description cited_evidence 的证据模态（规格 12.2，对应三类证据合同）。
         * @enum {string}
         */
        EvidenceModality: "TEXT" | "IMAGE" | "BEHAVIOR";
        /**
         * HealthView
         * @description GET /api/v1/health 的唯一响应结构（规格 12.2 字段白名单）。
         *
         *     业务 DTO 不返回密钥内容、供应商原始响应或本机绝对路径。
         */
        HealthView: {
            /** App Status */
            app_status: string;
            /** Database Status */
            database_status: string;
            /** Analysis Status */
            analysis_status: string;
            /** Message */
            message: string;
        };
        /**
         * InsufficientEvidenceReviewRequest
         * @description 标记证据不足：只说明证据缺口，禁止确定原因和处理动作。
         */
        InsufficientEvidenceReviewRequest: {
            /**
             * Submission Id
             * Format: uuid
             */
            submission_id: string;
            /** Review Token */
            review_token: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            outcome: "INSUFFICIENT_EVIDENCE";
            /** Review Reason */
            review_reason: string;
        };
        /**
         * InterventionLevel
         * @description 系统建议介入等级；等级语义与程序底线见规格第 7.4 节。
         * @enum {string}
         */
        InterventionLevel: "MUST_INTERVENE" | "SHOULD_INTERVENE" | "NO_IMMEDIATE_INTERVENTION";
        /**
         * ModifiedApprovedReviewRequest
         * @description 修改后确认：必须给出完整人工判断与修改原因，执行说明按需。
         */
        ModifiedApprovedReviewRequest: {
            /**
             * Submission Id
             * Format: uuid
             */
            submission_id: string;
            /** Review Token */
            review_token: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            outcome: "MODIFIED_AND_APPROVED";
            final_intervention_level: components["schemas"]["InterventionLevel"];
            final_cause: components["schemas"]["BusinessCause"];
            /** Final Actions */
            final_actions: components["schemas"]["ActionType"][];
            /** Review Reason */
            review_reason: string;
            /** Execution Note */
            execution_note?: string | null;
        };
        /**
         * OptionItem
         * @description 枚举或动作目录的单档选项（合同 value + 中文 label）。
         */
        OptionItem: {
            /** Value */
            value: string;
            /** Label */
            label: string;
        };
        /**
         * ProcessingErrorStage
         * @description 业务化阶段白名单（规格 12.2）；不把感知、归因、策略等内部阶段透传给运营人员。
         * @enum {string}
         */
        ProcessingErrorStage: "INPUT_PREPARATION" | "EVIDENCE_PROCESSING" | "AI_ANALYSIS" | "RESULT_PERSISTENCE" | "APP_RECOVERY";
        /**
         * RejectedWithJudgmentReviewRequest
         * @description 驳回并给出判断：必须携带人工判断与驳回原因，不得只有驳回。
         */
        RejectedWithJudgmentReviewRequest: {
            /**
             * Submission Id
             * Format: uuid
             */
            submission_id: string;
            /** Review Token */
            review_token: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            outcome: "REJECTED_WITH_JUDGMENT";
            final_intervention_level: components["schemas"]["InterventionLevel"];
            final_cause: components["schemas"]["BusinessCause"];
            /** Final Actions */
            final_actions: components["schemas"]["ActionType"][];
            /** Review Reason */
            review_reason: string;
            /** Execution Note */
            execution_note?: string | null;
        };
        /**
         * ReviewOptionsView
         * @description 人工确认表单只读选项（规格 12.2；仅 can_review=true 时出现）。
         */
        ReviewOptionsView: {
            /** Intervention Levels */
            intervention_levels: components["schemas"]["OptionItem"][];
            /** Cause Categories */
            cause_categories: components["schemas"]["OptionItem"][];
            /** Action Catalog Version */
            action_catalog_version: string;
            /** Action Types */
            action_types: components["schemas"]["OptionItem"][];
        };
        /**
         * ReviewResultView
         * @description 人工确认结果（规格 12.2）。
         */
        ReviewResultView: {
            /** Outcome */
            outcome: string;
            final_intervention_level?: components["schemas"]["InterventionLevel"] | null;
            final_cause?: components["schemas"]["CauseView"] | null;
            /** Final Actions */
            final_actions?: components["schemas"]["ActionView"][] | null;
            /** Execution Note */
            execution_note?: string | null;
            /** Review Reason */
            review_reason?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
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
    list_batches_api_v1_batches_get: {
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
                    "application/json": components["schemas"]["BatchListView"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    create_batch_api_v1_batches_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_create_batch_api_v1_batches_post"];
            };
        };
        responses: {
            /** @description 重复包幂等命中 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchWorkspaceView"];
                };
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchWorkspaceView"];
                };
            };
            /** @description ANSWER_LEAKAGE_DETECTED：运行包发现答案或答案性质字段 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description ACTIVE_BATCH_EXISTS：已有首次批量分析正在运行 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description UPLOAD_TOO_LARGE：ZIP 超过冻结的上传上限 */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description UNSUPPORTED_MEDIA_TYPE：上传或证据媒体类型不受支持 */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    get_batch_api_v1_batches__batch_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
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
                    "application/json": components["schemas"]["BatchWorkspaceView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    start_batch_run_api_v1_batches__batch_id__runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchWorkspaceView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description ACTIVE_BATCH_EXISTS：已有首次批量分析正在运行 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description ANALYSIS_UNAVAILABLE：缺密钥、模型健康检查失败或应用正在正常关闭 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    list_cases_api_v1_batches__batch_id__cases_get: {
        parameters: {
            query?: {
                /** @description 只允许一个案例状态筛选 */
                status?: string | null;
                /** @description 只允许一个介入等级筛选 */
                intervention_level?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                batch_id: string;
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
                    "application/json": components["schemas"]["CaseQueueView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    get_case_api_v1_batches__batch_id__cases__case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
                case_id: string;
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
                    "application/json": components["schemas"]["CaseDetailView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    rerun_case_api_v1_batches__batch_id__cases__case_id__reruns_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseDetailView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description CASE_ALREADY_COMPLETED：已完成案例收到新的审核或重跑请求 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description ANALYSIS_UNAVAILABLE：缺密钥、模型健康检查失败或应用正在正常关闭 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    submit_review_api_v1_batches__batch_id__cases__case_id__reviews_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovedReviewRequest"] | components["schemas"]["ModifiedApprovedReviewRequest"] | components["schemas"]["RejectedWithJudgmentReviewRequest"] | components["schemas"]["InsufficientEvidenceReviewRequest"];
            };
        };
        responses: {
            /** @description 相同 submission_id 幂等命中 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewResultView"];
                };
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewResultView"];
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description CASE_ALREADY_COMPLETED：已完成案例收到新的审核或重跑请求 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    get_evidence_content_api_v1_batches__batch_id__cases__case_id__evidence__evidence_id__content_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
                case_id: string;
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 受控证据图片流 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "image/*": string;
                };
            };
            /** @description RESOURCE_NOT_FOUND：批次、案例或证据不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description UNSUPPORTED_MEDIA_TYPE：上传或证据媒体类型不受支持 */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description REQUEST_VALIDATION_FAILED：HTTP 字段、联合请求、类型或枚举不合格 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
            /** @description INTERNAL_ERROR：未预期内部异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessError"];
                };
            };
        };
    };
    read_health_api_v1_health_get: {
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
                    "application/json": components["schemas"]["HealthView"];
                };
            };
        };
    };
}
