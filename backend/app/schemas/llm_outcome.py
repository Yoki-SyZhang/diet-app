from enum import Enum


class LlmOutcome(str, Enum):
    """nl_parse/food_estimate 共用的四态结果类型(tasks/current.md)。

    RESOLVED 之外的三种语义不同,不能都当成"追问"处理:NEEDS_CLARIFICATION 是用户侧
    信息不足或输入与记录饮食无关;SERVICE_UNAVAILABLE 是网络/超时/限流/Key 缺失等外部
    服务故障;INVALID_MODEL_OUTPUT 是模型未遵守契约,重试一次后仍失败。
    """

    RESOLVED = "resolved"
    NEEDS_CLARIFICATION = "needs_clarification"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
