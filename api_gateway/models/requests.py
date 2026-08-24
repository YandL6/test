"""
请求模型 — 各 API 端点的入参校验

Phase 1 覆盖的路由:
  POST /api/v1/sessions             — 创建会话
  POST /api/v1/sessions/{id}/upload — 上传需求文档
  POST /api/v1/sessions/{id}/generate/requirements — 生成需求点
  POST /api/v1/sessions/{id}/generate/testcases   — 生成测试用例
  POST /api/v1/sessions/{id}/generate/scripts      — 生成测试脚本
  GET  /api/v1/kb/search            — 知识库检索
"""
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """创建会话请求。"""

    title: str = Field(..., min_length=1, max_length=200, description="会话标题")
    user_id: str | None = Field(None, description="用户标识（可选，用于多用户隔离）")
    domain: str = Field(
        "vcu", description="功能域: vcu_gear / vcu_torque / vcu / general"
    )


class GenerateRequirementsRequest(BaseModel):
    """生成需求点请求。"""

    session_id: str = Field(..., description="会话 ID")
    document_id: str | None = Field(
        None, description="已上传文档 ID（可选，若未指定则用会话最新上传的文档）"
    )
    prompt_hint: str | None = Field(
        None, description="附加提示词（可选，用于微调生成方向）"
    )
    stream: bool = Field(True, description="是否 SSE 流式返回")


class GenerateTestcasesRequest(BaseModel):
    """生成测试用例请求。"""

    session_id: str = Field(..., description="会话 ID")
    requirement_ids: list[str] | None = Field(
        None, description="指定需求点 ID 列表；为空则用会话内全部需求点"
    )
    level: str = Field(
        "all", description="用例级别过滤: S0 / S1 / S2 / S3 / all"
    )
    stream: bool = Field(True, description="是否 SSE 流式返回")


class GenerateScriptsRequest(BaseModel):
    """生成测试脚本请求。"""

    session_id: str = Field(..., description="会话 ID")
    testcase_ids: list[str] | None = Field(
        None, description="指定用例 ID 列表；为空则用会话内全部用例"
    )
    script_format: str = Field(
        "python", description="脚本格式: python / capl / text"
    )
    stream: bool = Field(True, description="是否 SSE 流式返回")


class KBSearchRequest(BaseModel):
    """知识库检索请求。"""

    query: str = Field(..., min_length=1, description="检索关键词或自然语言问题")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数")
    domain: str | None = Field(
        None, description="限定功能域: vcu_gear / vcu_torque / null=全库"
    )
