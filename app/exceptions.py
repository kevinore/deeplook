class DeepLookError(Exception):
    """Base exception for all DeepLook errors."""


class ParseError(DeepLookError):
    def __init__(self, filename: str, reason: str, line_number: int | None = None):
        self.filename = filename
        self.reason = reason
        self.line_number = line_number
        super().__init__(f"ParseError in {filename}: {reason}")


class ValidationError(DeepLookError):
    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"ValidationError on '{field}': {reason}")


class AIProviderError(DeepLookError):
    def __init__(self, provider: str, model: str, message: str, status_code: int | None = None):
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.message = message
        super().__init__(f"AIProviderError [{provider}/{model}]: {message}")


class AnalysisError(DeepLookError):
    def __init__(self, conversation_id: str, reason: str):
        self.conversation_id = conversation_id
        self.reason = reason
        super().__init__(f"AnalysisError for conversation {conversation_id}: {reason}")


class ReportGenerationError(DeepLookError):
    def __init__(self, job_id: str, reason: str):
        self.job_id = job_id
        self.reason = reason
        super().__init__(f"ReportGenerationError for job {job_id}: {reason}")
