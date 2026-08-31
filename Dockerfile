FROM python:3.11-slim

LABEL org.opencontainers.image.title="智慧农业生态 AgriEco" \
      org.opencontainers.image.description="AI + 农业多 Agent 协同框架（气候分区/作物推荐/种植计划/生态撮合）" \
      version="1.0"

WORKDIR /app

# 纯标准库实现，无需 pip 安装第三方依赖
COPY . /app

# 默认运行端到端验证（可作为 CI/部署健康检查）
CMD ["python", "scripts/verify_all.py"]
