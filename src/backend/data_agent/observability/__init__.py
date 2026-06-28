"""可观测性 / Tracing 模块。

LangChain Runnable / tool / 业务函数所有调用都通过 @traced 装饰器或
LangChainTracer callback 自动写入本地 SQLite trace.db。
"""
