.PHONY: build up down security-scan

build:
	docker compose -f infra/docker-compose.prod.yml build

up:
	docker compose -f infra/docker-compose.prod.yml up -d

down:
	docker compose -f infra/docker-compose.prod.yml down

security-scan:
	@echo "Running vulnerability scan on API image..."
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
		aquasec/trivy image --exit-code 1 --severity CRITICAL neuroflow-api:latest
	@echo "Running vulnerability scan on Frontend image..."
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
		aquasec/trivy image --exit-code 1 --severity CRITICAL neuroflow-frontend:latest
