FLUTTER ?= flutter
T ?=
SDK_EXAMPLE_URL ?= http://localhost:8012

.PHONY: test analyze run-web build-web serve-web
test:
	$(FLUTTER) test $(T)

analyze:
	$(FLUTTER) analyze

run-web:
	$(FLUTTER) run -d chrome

build-web:
	$(FLUTTER) build web --release

serve-web:
	$(FLUTTER) run -d web-server --web-hostname 0.0.0.0 --web-port 8078 --no-web-experimental-hot-reload --dart-define=SDK_EXAMPLE_URL=$(SDK_EXAMPLE_URL)
