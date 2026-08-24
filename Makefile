.PHONY: setup run dev prod test clean docker-up docker-down help

## 安装：克隆 Hermes + 安装依赖 + 初始化配置
setup:
	bash setup_hermes.sh --venv

## 安装（不使用虚拟环境）
setup-novenv:
	bash setup_hermes.sh

## 开发模式启动（热重载）
dev:
	bash run.sh

## 生产模式启动（无热重载）
prod:
	bash run.sh --prod

## 兼容 run
run: dev

## 运行 SGLang 连通性测试
test-sglang:
	python tests/test_sglang_connection.py --base-url http://localhost:30000/v1

## 运行端到端集成测试
test-integration:
	python tests/test_integration.py --host http://localhost:8100

## 运行所有测试
test: test-sglang test-integration

## Docker 启动
docker-up:
	docker-compose up -d

## Docker 停止
docker-down:
	docker-compose down

## 清理临时文件
clean:
	rm -rf __pycache__ .pytest_cache *.pyc uploads/* logs/*.log
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

## 健康检查
health:
	curl -s http://localhost:8100/health | python -m json.tool

## API 文档
docs:
	@echo "API 文档地址: http://localhost:8100/docs"

help:
	@echo "Hermes VCU Gateway — 常用命令"
	@echo ""
	@echo "  make setup          一键安装（含虚拟环境）"
	@echo "  make dev            开发模式启动（热重载）"
	@echo "  make prod           生产模式启动"
	@echo "  make test           运行所有测试"
	@echo "  make docker-up      Docker 启动"
	@echo "  make health         健康检查"
	@echo "  make clean          清理临时文件"
