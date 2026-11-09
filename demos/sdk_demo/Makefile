FLUTTER ?= flutter
T ?=

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
	$(FLUTTER) run -d web-server --web-hostname 0.0.0.0 --web-port 8078 --no-web-experimental-hot-reload
