# GD32F10x Makefile (Kconfig + compile-time devicetree)
#
# Targets:
#   make lunch [BOARD=<name>]   select board (interactive or direct)
#   make                        build firmware -> build/bin/$(BOARD).bin
#   make defconfig              restore default config from configs/$(BOARD)_defconfig
#   make clean                  remove build/
#   make distclean              remove build/ + .config + .board
#   make download               flash firmware via OpenOCD + J-Link

ROOT_DIR    = .
TARGET      = $(BOARD)

BOARD_FILE   = .board
CONFIG_FILE  = .config
DEFCONFIG    = configs/$(BOARD)_defconfig

AVAILABLE_BOARDS = $(foreach b,$(sort $(notdir $(patsubst %/,%,$(dir $(wildcard $(ROOT_DIR)/boards/*/))))),$(if $(wildcard $(ROOT_DIR)/configs/$(b)_defconfig),$(b)))
CURRENT_BOARD := $(shell cat $(BOARD_FILE) 2>/dev/null)

BOARD_ON_CMD := $(if $(filter command%,$(origin BOARD)),$(BOARD),)

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)

ifneq ($(BOARD_ON_CMD),)
ifneq ($(CURRENT_BOARD),)
ifneq ($(CURRENT_BOARD),$(BOARD_ON_CMD))
$(error BOARD=$(BOARD_ON_CMD) conflicts with current board '$(CURRENT_BOARD)', switch via: make lunch BOARD=$(BOARD_ON_CMD))
endif
else
CURRENT_BOARD := $(BOARD_ON_CMD)
$(shell echo $(BOARD_ON_CMD) > $(BOARD_FILE))
endif
BOARD := $(BOARD_ON_CMD)
else
BOARD := $(CURRENT_BOARD)
ifeq ($(BOARD),)
# auto-select if only one board exists
ifeq ($(words $(AVAILABLE_BOARDS)),1)
BOARD := $(word 1,$(AVAILABLE_BOARDS))
$(shell echo $(BOARD) > $(BOARD_FILE))
endif
endif
endif

ifeq ($(BOARD),)
$(error no board selected: run 'make lunch' first)
endif

# first build: fall back to defconfig
ifeq ($(wildcard $(CONFIG_FILE)),)
ifeq ($(wildcard $(DEFCONFIG)),)
$(error defconfig not found: $(DEFCONFIG), check BOARD=$(BOARD))
endif
$(shell cp $(DEFCONFIG) $(CONFIG_FILE))
endif

endif   # board resolution (skipped for lunch/clean/distclean)

-include $(CONFIG_FILE)

# devicetree file is bound to the board via CONFIG_BOARD_DTS in defconfig
DT_FILE = $(strip $(CONFIG_BOARD_DTS))

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)
ifeq ($(DT_FILE),)
$(error CONFIG_BOARD_DTS not set in configs/$(BOARD)_defconfig)
endif
endif

FLASH_START := 0x08000000
RAM_START   := 0x20000000

BUILD_DIR   = build
BIN_DIR     = $(BUILD_DIR)/bin
OBJ_DIR     = $(BUILD_DIR)/obj
GEN_DIR     = $(BUILD_DIR)/generated
DTS_DIR     = $(BUILD_DIR)/dts

AUTOCONF    = $(GEN_DIR)/autoconf.h
DTB         = $(DTS_DIR)/$(BOARD).dtb
DTS_PP      = $(DTS_DIR)/$(BOARD).dts.pp
DT_HEADER   = $(GEN_DIR)/devicetree_generated.h

MCU_SERIES  = GD32F10x
MCU_CPU     = cortex-m3

COMPILER    = /usr/local/arm/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-
CC          = $(COMPILER)gcc
AS          = $(COMPILER)gcc
LD          = $(COMPILER)gcc
OBJCOPY     = $(COMPILER)objcopy
SIZE        = $(COMPILER)size
CPP         = cpp
PYTHON      ?= python3

# per-driver Makefiles: drivers/<name>/Makefile appends to obj-$(CONFIG_xxx)
# (Linux-style sub-Makefiles; adding a driver requires no top-level edit)
obj-y :=
define add-drivers
drv-dir := $(patsubst ./%,%,$(1))
include $(2)
endef
$(foreach mf,$(wildcard $(ROOT_DIR)/drivers/*/Makefile),$(eval $(call add-drivers,$(patsubst %/,%,$(dir $(mf))),$(mf))))
drv-dir :=
DRIVER_SOURCES  = $(addprefix $(ROOT_DIR)/,$(obj-y))
DRIVER_INCLUDES = $(foreach d,$(wildcard $(ROOT_DIR)/drivers/*/),-I$(d))

MCU_FLAGS   = -mcpu=$(MCU_CPU) -mthumb -mfloat-abi=soft

OPT         = -Os

CFLAGS      = $(MCU_FLAGS) $(OPT) -Wall -fdata-sections -ffunction-sections
CFLAGS     += -std=gnu11 -MMD -MP -MF"$(@:%.o=%.d)"
CFLAGS     += -D$(MCU_SERIES) -DGD32F10X_HD -DUSE_STDPERIPH_DRIVER
CFLAGS     += -DFLASH_START=$(FLASH_START) -DRAM_START=$(RAM_START)
CFLAGS     += -I$(GEN_DIR) -include $(AUTOCONF)

ASFLAGS     = $(MCU_FLAGS) -c

LD_SCRIPT   = $(ROOT_DIR)/vendor/cmsis/device/gd32f10x_flash.ld
LDFLAGS     = $(MCU_FLAGS) $(OPT) -T$(LD_SCRIPT)
LDFLAGS    += -Wl,-Map="$(BUILD_DIR)/$(TARGET).map"
LDFLAGS    += -Wl,--gc-sections -Wl,--print-memory-usage
LDFLAGS    += -specs=nano.specs -specs=nosys.specs
LDFLAGS    += -Wl,--start-group -lc -lm -lnosys -Wl,--end-group
LDFLAGS    += -Wl,--defsym=FLASH_START=$(FLASH_START)
LDFLAGS    += -Wl,--defsym=RAM_START=$(RAM_START)

INCLUDES    = -I$(ROOT_DIR)/vendor/cmsis/core \
              -I$(ROOT_DIR)/vendor/cmsis/device \
              -I$(ROOT_DIR)/vendor/fwlib/include \
              -I$(ROOT_DIR)/user \
              $(DRIVER_INCLUDES)

DTS_INCLUDES = -I$(dir $(DT_FILE)) \
               -I$(ROOT_DIR)/dts \
               -I$(ROOT_DIR)/dts/include

C_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.c) \
              $(wildcard $(ROOT_DIR)/vendor/fwlib/source/*.c) \
              $(wildcard $(ROOT_DIR)/user/*.c) \
              $(DRIVER_SOURCES)

ASM_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.S)

C_OBJECTS     = $(C_SOURCES:$(ROOT_DIR)/%.c=$(OBJ_DIR)/%.o)
ASM_OBJECTS   = $(ASM_SOURCES:$(ROOT_DIR)/%.S=$(OBJ_DIR)/%.o)
OBJECTS       = $(ASM_OBJECTS) $(C_OBJECTS)

DEP_FILES     = $(OBJECTS:.o=.d)

all: $(BIN_DIR)/$(TARGET).bin $(BIN_DIR)/$(TARGET).hex | show-board

.PHONY: show-board
show-board:
	@echo "Board: $(BOARD)    DeviceTree: $(DT_FILE)"

$(AUTOCONF): $(CONFIG_FILE) $(wildcard Kconfig drivers/Kconfig) scripts/kconfigconf.py
	@mkdir -p $(@D)
	$(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) --autoconf $@

$(DTB): $(DT_FILE) $(BOARD_FILE) $(wildcard dts/*.dtsi) $(wildcard dts/include/dt-bindings/**/*.h)
	@mkdir -p $(@D)
	$(CPP) -E -x assembler-with-cpp -nostdinc -undef $(DTS_INCLUDES) -o $(DTS_PP) $<
	dtc -I dts -O dtb -o $@ $(DTS_PP)

$(DT_HEADER): $(DTB) scripts/gen_devicetree.py
	$(PYTHON) scripts/gen_devicetree.py --dtb $< --out $@

$(BIN_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	@mkdir -p $(@D)
	$(OBJCOPY) -O binary $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).bin

$(BIN_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	@mkdir -p $(@D)
	$(OBJCOPY) -O ihex $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).hex

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS) $(AUTOCONF) $(DT_HEADER)
	@mkdir -p $(@D)
	$(LD) $(OBJECTS) $(LDFLAGS) -o $@
	$(SIZE) $@

$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.c $(AUTOCONF) $(DT_HEADER)
	@mkdir -p $(@D)
	$(CC) -c $(CFLAGS) $(INCLUDES) -o $@ $<

$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.S
	@mkdir -p $(@D)
	$(AS) -c $(ASFLAGS) $(INCLUDES) -o $@ $<

lunch:
	@i=0; cur=0; \
	if [ -n "$(BOARD_ON_CMD)" ]; then \
		sel="$(BOARD_ON_CMD)"; \
	else \
		echo "current board: $(if $(CURRENT_BOARD),$(CURRENT_BOARD),<none>)"; \
		for b in $(AVAILABLE_BOARDS); do \
			i=$$((i+1)); \
			if [ "$$b" = "$(CURRENT_BOARD)" ]; then \
				cur=$$i; \
				echo "   * $$i. $$b   <- current"; \
			else \
				echo "     $$i. $$b"; \
			fi; \
		done; \
		if [ "$$i" -eq 0 ]; then \
			exit 1; \
		fi; \
		def=$${cur:-1}; \
		printf "select board [1-%d] (default %s): " "$$i" "$$def"; \
		read n; \
		[ -z "$$n" ] && n=$$def; \
		case "$$n" in *[!0-9]*|'') echo "error: '$$n' is not a number"; exit 1;; esac; \
		if [ "$$n" -lt 1 ] || [ "$$n" -gt "$$i" ]; then \
			echo "error: index $$n out of range (1~$$i)"; \
			exit 1; \
		fi; \
		sel=`echo "$(AVAILABLE_BOARDS)" | cut -d' ' -f "$$n"`; \
	fi; \
	valid=0; \
	for b in $(AVAILABLE_BOARDS); do \
		if [ "$$b" = "$$sel" ] && [ -f "$(ROOT_DIR)/configs/$${sel}_defconfig" ]; then valid=1; break; fi; \
	done; \
	if [ "$$valid" != "1" ]; then \
		echo "error: board '$$sel' not found"; \
		exit 1; \
	fi; \
	dts=`sed -n 's/^CONFIG_BOARD_DTS=//p' "$(ROOT_DIR)/configs/$${sel}_defconfig" | head -1`; \
	if [ ! -f "$$dts" ]; then \
		echo "error: devicetree not found: $$dts"; \
		exit 1; \
	fi; \
	echo "$$sel" > $(BOARD_FILE); \
	cp "$(ROOT_DIR)/configs/$${sel}_defconfig" $(CONFIG_FILE); \
	echo "board: $$sel"; \
	echo "devicetree: $$dts"

defconfig:
	@cp $(DEFCONFIG) $(CONFIG_FILE)
	@echo "restored $(DEFCONFIG) -> $(CONFIG_FILE)"

-include $(DEP_FILES)

clean:
	rm -rf $(BUILD_DIR)

distclean: clean
	rm -f $(CONFIG_FILE) $(BOARD_FILE)

download: $(BIN_DIR)/$(TARGET).bin
	@openocd \
	    -f interface/jlink.cfg \
	    -c "transport select swd" \
	    -f target/stm32f1x.cfg \
	    -c "adapter speed 2000" \
	    -c "init" \
	    -c "reset halt" \
	    -c "flash write_image erase $(BIN_DIR)/$(TARGET).bin $(FLASH_START)" \
	    -c "verify_image $(BIN_DIR)/$(TARGET).bin $(FLASH_START)" \
	    -c "reset run" \
	    -c "exit"

.PHONY: all clean distclean defconfig lunch show-board download
