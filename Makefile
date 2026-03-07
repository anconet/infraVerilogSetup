# Gather all Verilog/SystemVerilog source files (both .sv and .v)
SRCS := $(wildcard ./verilog/*.sv ./verilog/*.v)

# --------------------------- framework config ---------------------------
# items that comprise the reusable framework. install/uninstall rely on
# this list, so updating it here will affect both operations.  Use the
# actual names as they appear in the repo; directories are treated as such.
# (many projects use the dot‑prefixed versions for VS Code/devcontainer.)
FRAMEWORK_ITEMS := .devcontainer .vscode Makefile


# Detect all testbenches (either .sv or .v)
TBS := $(filter %_tb.sv %_tb.v,$(SRCS))

# Strip .sv extension
TB_NAMES := $(basename $(TBS))

# Outputs
SIMS := $(TB_NAMES:%=%.out)
VCDS := $(TB_NAMES:%=%.vcd)

.PHONY: all run waveform clean help watch install uninstall

# Display help information
help:
	@echo "Available targets:"
	@echo "  all      - Compile all testbenches (default)"
	@echo "  run      - Run all simulations and generate VCD files"
	@echo "  waveform - Open GTKWave for the first testbench"
	@echo "  wave-<TB_NAME> - Open GTKWave for a specific testbench (e.g., make wave-counter_tb)"
	@echo "  install  - Copy framework files into another project using rsync"
	@echo "             specify INSTALL_DIR=path (default ../)"
	@echo "  uninstall- Remove files previously installed by 'make install'"
	@echo "             (requires the .verilog_framework_installed record)"
	@echo "  clean    - Remove all compiled simulations and VCD files"
	@echo "  help     - Display this help message"

# Default: build all simulations
all: $(SIMS)

# Compile each testbench (supports .sv or .v extension)
%.out: $(SRCS)
	iverilog -g2012 -D"VCD_FILE=\"$(@:.out=.vcd)\"" -o $@ $^

# Run each simulation to produce VCD
%.vcd: %.out
	vvp $<

# Run all simulations
run: $(VCDS)

# Open GTKWave for the first testbench
waveform: $(VCDS)
	gtkwave $(firstword $(VCDS))

# Open GTKWave for a specific testbench
wave-%: %.vcd
	gtkwave $<

# Automatically re-run simulations when any source file changes
watch:
	@ls $(SRCS) | entr -c make run

# Directory where the files will be installed. This is
# the root of the new project (typically the parent dir
# when this repo is added as a submodule).
INSTALL_DIR ?= ..

.PHONY: install uninstall

# Copy the framework items, skipping git metadata and generated clutter
install:
	@if ! command -v rsync >/dev/null; then \
		echo "rsync is required for installation, please install it."; exit 1; \
	fi
	@echo "Installing framework files to $(INSTALL_DIR)"
	@for item in $(FRAMEWORK_ITEMS); do \
		rsync -av --exclude='.git' \
			--exclude='*.out' --exclude='*.vcd' \
			--exclude='*.gtkw' --exclude='*.sav' \
			"$$item" "$(INSTALL_DIR)/"; \
	done
	# keep record for compatibility / debugging
	@printf '%s\n' $(FRAMEWORK_ITEMS) > "$(INSTALL_DIR)/.verilog_framework_installed"

# Remove the files that were installed previously
uninstall:
	@echo "Uninstalling framework files from $(INSTALL_DIR)"
	@for item in $(FRAMEWORK_ITEMS); do \
		rm -rf -- "$(INSTALL_DIR)/$$item"; \
	done
	@rm -f "$(INSTALL_DIR)/.verilog_framework_installed"

clean:
	rm -f $(SIMS) $(VCDS)