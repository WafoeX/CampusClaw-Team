UV ?= uv
OPENSPEC ?= openspec
CHANGE ?=
RUN := $(UV) run --locked
TRIVY := ghcr.io/aquasecurity/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c
GITLEAKS := ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
TRIVY_CACHE := $(CURDIR)/reports/trivy-cache

.PHONY: check check-static check-specs check-test check-secrets check-dependencies check-integration
check:
	$(MAKE) check-static
	$(MAKE) check-test
	$(MAKE) check-secrets
	$(MAKE) check-dependencies
	$(MAKE) check-integration

check-specs:
	$(OPENSPEC) validate --all --strict
ifneq ($(strip $(CHANGE)),)
	$(OPENSPEC) validate "$(CHANGE)" --strict
endif

check-static: check-specs
	$(RUN) ruff format --check app scripts tests
	$(RUN) ruff check app scripts tests
	$(RUN) python scripts/check_layout.py

check-test:
	$(RUN) python scripts/check_pytest.py -q --disable-socket tests/unit tests/api
	$(RUN) python scripts/check_pytest.py -q tests/test_startup.py

check-secrets:
	$(RUN) python scripts/check_secrets.py "$(GITLEAKS)"

check-dependencies:
	mkdir -p "$(TRIVY_CACHE)"
	docker run --rm --mount "type=bind,src=$(TRIVY_CACHE),dst=/cache" --mount "type=bind,src=$(CURDIR)/uv.lock,dst=/scan/uv.lock,readonly" "$(TRIVY)" fs --cache-dir /cache --db-repository ghcr.io/aquasecurity/trivy-db:2 --no-progress --include-dev-deps --scanners vuln --severity HIGH,CRITICAL --exit-code 1 /scan

check-integration:
	mkdir -p "$(TRIVY_CACHE)"
	CAMPUSCLAW_IMAGE_SCANNER="$(TRIVY)" CAMPUSCLAW_SCANNER_CACHE="$(TRIVY_CACHE)" $(RUN) python scripts/check_pytest.py -q --tb=short tests/integration
