# GD32F10x Makefile (Kconfig + compile-time devicetree + multi-board/multi-app)
#
# Targets:
#   make lunch [BOARD=<name> [APP=<name>]]   两级选择: 版型 -> 应用 (交互或直接指定)
#   make                                     build -> build/bin/$(BOARD)_$(APP).bin
#   make defconfig                           按当前 版型+应用 恢复默认配置
#   make clean / distclean / download
#
# 目录约定:
#   版型(板卡): configs/<板型>_defconfig + arm/boards/<板型>/<板型>.dts
#   应用:      application/<板型>/<应用>/ (Makefile 必需, defconfig 可选覆盖板级)

ROOT_DIR    = .
TARGET      = $(BOARD)_$(APP)

BOARD_FILE  = .board
APP_FILE    = .app
CONFIG_FILE = .config

AVAILABLE_BOARDS = $(patsubst %_defconfig,%,$(notdir $(wildcard $(ROOT_DIR)/configs/*_defconfig)))

BOARD_ON_CMD := $(if $(filter command%,$(origin BOARD)),$(BOARD),)
APP_ON_CMD   := $(if $(filter command%,$(origin APP)),$(APP),)

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)

# ---------------- 版型解析 ----------------
CURRENT_BOARD := $(shell cat $(BOARD_FILE) 2>/dev/null)

ifneq ($(BOARD_ON_CMD),)
ifneq ($(CURRENT_BOARD),)
ifneq ($(CURRENT_BOARD),$(BOARD_ON_CMD))
$(error BOARD=$(BOARD_ON_CMD) conflicts with current board '$(CURRENT_BOARD)', switch via: make lunch BOARD=$(BOARD_ON_CMD))
endif
endif
BOARD := $(BOARD_ON_CMD)
$(shell echo $(BOARD_ON_CMD) > $(BOARD_FILE))
else
BOARD := $(CURRENT_BOARD)
ifeq ($(BOARD),)
# 只有一个版型时自动选择
ifeq ($(words $(AVAILABLE_BOARDS)),1)
BOARD := $(word 1,$(AVAILABLE_BOARDS))
$(shell echo $(BOARD) > $(BOARD_FILE))
endif
endif
endif

ifeq ($(BOARD),)
$(error no board selected: run 'make lunch' first)
endif

ifeq ($(wildcard $(ROOT_DIR)/configs/$(BOARD)_defconfig),)
$(error defconfig not found: configs/$(BOARD)_defconfig, check BOARD=$(BOARD))
endif

# ---------------- 应用解析 ----------------
CURRENT_APP := $(shell cat $(APP_FILE) 2>/dev/null)

ifeq ($(wildcard $(ROOT_DIR)/application),)
$(error application/ directory not found)
endif
# 该版型下的可用应用 (application/<板型>/<应用>/Makefile)
BOARD_APPS := $(shell for d in $(ROOT_DIR)/application/$(BOARD)/*/; do [ -f "$$d/Makefile" ] && basename $$d; done)

ifneq ($(APP_ON_CMD),)
ifneq ($(CURRENT_APP),)
ifneq ($(CURRENT_APP),$(APP_ON_CMD))
$(error APP=$(APP_ON_CMD) conflicts with current app '$(CURRENT_APP)', switch via: make lunch APP=$(APP_ON_CMD))
endif
endif
APP := $(APP_ON_CMD)
$(shell echo $(APP_ON_CMD) > $(APP_FILE))
else
APP := $(CURRENT_APP)
ifeq ($(APP),)
# 只有一个应用时自动选择
ifeq ($(words $(BOARD_APPS)),1)
APP := $(word 1,$(BOARD_APPS))
$(shell echo $(APP) > $(APP_FILE))
endif
endif
endif

ifeq ($(APP),)
$(error no app selected for board '$(BOARD)': run 'make lunch' first)
endif

ifeq ($(filter $(APP),$(BOARD_APPS)),)
$(error app '$(APP)' not found under application/$(BOARD)/ (has Makefile?), available: $(BOARD_APPS))
endif

# ---------------- 配置文件 ----------------
# 应用自带 defconfig 时优先于板级默认 (整个 .config 以它为准)
APP_DEFCONFIG    = application/$(BOARD)/$(APP)/defconfig
BOARD_DEFCONFIG  = configs/$(BOARD)_defconfig
SELECT_DEFCONFIG = $(if $(wildcard $(ROOT_DIR)/$(APP_DEFCONFIG)),$(APP_DEFCONFIG),$(BOARD_DEFCONFIG))

ifeq ($(wildcard $(CONFIG_FILE)),)
$(shell cp $(ROOT_DIR)/$(SELECT_DEFCONFIG) $(CONFIG_FILE))
endif

endif   # 版型/应用解析 (lunch/clean/distclean 时跳过)

# .config 存在但比 Kconfig 旧 (新增符号/修改默认) 时, 解析期先重新生成补全,
# 保证本条 make 就能拿到完整 CONFIG_* 变量 —— 否则 obj-$(CONFIG_xxx) 展开为空,
# 对应驱动被静默漏编, 到链接才 undefined reference (btimer/gtimer 踩过的坑)
ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)
ifeq ($(wildcard $(CONFIG_FILE)),)
$(shell cp $(ROOT_DIR)/$(SELECT_DEFCONFIG) $(CONFIG_FILE))
$(shell $(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) >/dev/null 2>&1)
else ifneq ($(shell find $(ROOT_DIR)/Kconfig $(ROOT_DIR)/drivers/Kconfig -newer $(CONFIG_FILE) 2>/dev/null),)
$(shell $(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) >/dev/null 2>&1)
endif
endif

-include $(CONFIG_FILE)

# devicetree file is bound to the board via CONFIG_BOARD_DTS in defconfig
DT_FILE = $(strip $(CONFIG_BOARD_DTS))

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)
ifeq ($(DT_FILE),)
$(error CONFIG_BOARD_DTS not set in $(SELECT_DEFCONFIG))
endif
ifeq ($(wildcard $(ROOT_DIR)/$(DT_FILE)),)
$(error devicetree not found: $(DT_FILE))
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

# ---------------- 输出控制 (仿 Linux kbuild) ----------------
# 默认: 每步一行简短回显 "  CC      build/obj/xxx.o"
# V=1:  输出完整命令行 (调试构建问题时用)
SHELL = /bin/bash
.SHELLFLAGS = -o pipefail -c
ifeq ("$(origin V)", "command line")
  ifeq ($(V),1)
    qcmd    = $2
    qcmd_ld = $2
  endif
endif
# qcmd_ld: LD 专用 —— 过滤 libc_nano "note:" / link 路径前缀噪音 (诊断错误不受影响)
ifndef qcmd
  qcmd    = @echo '  $1' && $2
endif
ifndef qcmd_ld
  # ld 打印 note/warning 到 stdout, gcc 传递的到 stderr —— 两路都过滤已知噪音
  # libnosys 半链接桩 (closer/fstatr/isattyr/lseekr/readr/writer) 的 5 组 note+warning 是已知噪音:
  # 按库成员名过滤整段 (both the 'in function' 行和 'is not implemented' 行)
  LD_NOISE = grep -vE ': note:|LOAD segment with RWX|libc_a-(closer|fstatr|isattyr|lseekr|readr|writer)\.o|_(close|fstat|isatty|lseek|read|write) is not implemented'
  qcmd_ld = @echo '  $1' && ( $2 ) > >($(LD_NOISE)) 2> >($(LD_NOISE) >&2)
endif

# ---------------- 源文件收集 (Linux 风格子 Makefile) ----------------
# 驱动: drivers/<name>/Makefile 全部 include -> obj-$(CONFIG_xxx) += ...
# 应用: application/<板型>/<应用>/Makefile 只 include 当前选中的 -> obj-y += ...
obj-y :=
define add-drivers
drv-dir := $(patsubst ./%,%,$(1))
include $(2)
endef
$(foreach mf,$(wildcard $(ROOT_DIR)/drivers/*/Makefile),$(eval $(call add-drivers,$(patsubst %/,%,$(dir $(mf))),$(mf))))
drv-dir :=

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)
app-dir := application/$(BOARD)/$(APP)
include $(ROOT_DIR)/$(app-dir)/Makefile
app-dir :=
endif

DEV_APP_SOURCES = $(addprefix $(ROOT_DIR)/,$(obj-y))
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
              -I$(ROOT_DIR)/arm/include \
              -I$(ROOT_DIR)/application/$(BOARD)/$(APP) \
              $(DRIVER_INCLUDES)

# 设备树 include 路径: 板级 dts 所在目录 + SoC dtsi(arm/core) + dt-bindings(arm/include)
DTS_INCLUDES = -I$(dir $(DT_FILE)) \
               -I$(ROOT_DIR)/arm/core \
               -I$(ROOT_DIR)/arm/include

C_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.c) \
              $(wildcard $(ROOT_DIR)/vendor/fwlib/source/*.c) \
              $(DEV_APP_SOURCES)

ASM_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.S)

C_OBJECTS     = $(C_SOURCES:$(ROOT_DIR)/%.c=$(OBJ_DIR)/%.o)
ASM_OBJECTS   = $(ASM_SOURCES:$(ROOT_DIR)/%.S=$(OBJ_DIR)/%.o)
OBJECTS       = $(ASM_OBJECTS) $(C_OBJECTS)

DEP_FILES     = $(OBJECTS:.o=.d)

all: $(BIN_DIR)/$(TARGET).bin $(BIN_DIR)/$(TARGET).hex | show-board

.PHONY: show-board
show-board:
	@echo "Board: $(BOARD)    App: $(APP)    DeviceTree: $(DT_FILE)"

$(AUTOCONF): $(CONFIG_FILE) $(wildcard Kconfig drivers/Kconfig) scripts/kconfigconf.py
	@mkdir -p $(@D)
	$(call qcmd,GEN     $@,$(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) --autoconf $@)

$(DTB): $(DT_FILE) $(BOARD_FILE) $(APP_FILE) $(wildcard arm/core/*.dtsi) $(wildcard arm/include/dt-bindings/**/*.h)
	@mkdir -p $(@D)
	$(call qcmd,DTC     $@,$(CPP) -E -x assembler-with-cpp -nostdinc -undef $(DTS_INCLUDES) -o $(DTS_PP) $< && dtc -I dts -O dtb -o $@ $(DTS_PP))

$(DT_HEADER): $(DTB) scripts/gen_devicetree.py
	$(call qcmd,GEN     $@,$(PYTHON) scripts/gen_devicetree.py --dtb $< --out $@)

$(BIN_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	@mkdir -p $(@D)
	$(call qcmd,OBJCOPY $@,$(OBJCOPY) -O binary $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).bin)

$(BIN_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	@mkdir -p $(@D)
	$(call qcmd,OBJCOPY $@,$(OBJCOPY) -O ihex $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).hex)

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS) $(AUTOCONF) $(DT_HEADER)
	@mkdir -p $(@D)
	$(call qcmd_ld,LD     $@,$(LD) $(OBJECTS) $(LDFLAGS) -o $@ && $(SIZE) $@)

$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.c $(AUTOCONF) $(DT_HEADER)
	@mkdir -p $(@D)
	$(call qcmd,CC      $@,$(CC) -c $(CFLAGS) $(INCLUDES) -o $@ $<)

$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.S
	@mkdir -p $(@D)
	$(call qcmd,AS      $@,$(AS) -c $(ASFLAGS) $(INCLUDES) -o $@ $<)

# 两级 lunch: 1) 版型  2) 该版型下的应用
# 直接指定: make lunch BOARD=gd32f103re APP=uart_echo (带 APP 则全程免交互)
lunch:
	@set -e; \
	# ---------- 1. 选版型 ----------; \
	if [ -n "$(BOARD_ON_CMD)" ]; then \
		sel_b="$(BOARD_ON_CMD)"; \
	else \
		echo "current board: $(if $(CURRENT_BOARD),$(CURRENT_BOARD),<none>)"; \
		i=0; cur=0; \
		for b in $(AVAILABLE_BOARDS); do \
			i=$$((i+1)); \
			if [ "$$b" = "$(CURRENT_BOARD)" ]; then \
				cur=$$i; echo "   * $$i. $$b   <- current"; \
			else \
				echo "     $$i. $$b"; \
			fi; \
		done; \
		[ "$$i" -eq 0 ] && { echo "error: no boards (configs/*_defconfig)"; exit 1; }; \
		def=$${cur:-1}; [ "$$def" = "0" ] && def=1; \
		printf "select board [1-%d] (default %s): " "$$i" "$$def"; \
		read n; \
		[ -z "$$n" ] && n=$$def; \
		case "$$n" in *[!0-9]*|'') echo "error: '$$n' is not a number"; exit 1;; esac; \
		[ "$$n" -lt 1 ] || [ "$$n" -gt "$$i" ] && { echo "error: index $$n out of range (1~$$i)"; exit 1; }; \
		sel_b=`echo "$(AVAILABLE_BOARDS)" | cut -d' ' -f "$$n"`; \
	fi; \
	[ -f "$(ROOT_DIR)/configs/$${sel_b}_defconfig" ] || { echo "error: board '$$sel_b' not found"; exit 1; }; \
	echo "$$sel_b" > $(BOARD_FILE); \
	# ---------- 2. 选应用 (该版型下) ----------; \
	apps=""; \
	for d in $(ROOT_DIR)/application/$$sel_b/*/; do \
		[ -f "$$d/Makefile" ] && apps="$$apps$$(basename $$d) "; \
	done; \
	[ -z "$$apps" ] && { echo "error: no apps under application/$$sel_b/ (need Makefile)"; exit 1; }; \
	if [ -n "$(APP_ON_CMD)" ]; then \
		sel_a="$(APP_ON_CMD)"; \
	else \
		echo "board: $$sel_b"; \
		i=0; cur=0; \
		cur_app=; [ -f $(APP_FILE) ] && cur_app=$$(cat $(APP_FILE)); \
		for a in $$apps; do \
			i=$$((i+1)); \
			if [ "$$a" = "$$cur_app" ]; then \
				cur=$$i; echo "   * $$i. $$a   <- current"; \
			else \
				echo "     $$i. $$a"; \
			fi; \
		done; \
		def=$${cur:-1}; [ "$$def" = "0" ] && def=1; \
		printf "select app [1-%d] (default %s): " "$$i" "$$def"; \
		read n; \
		[ -z "$$n" ] && n=$$def; \
		case "$$n" in *[!0-9]*|'') echo "error: '$$n' is not a number"; exit 1;; esac; \
		[ "$$n" -lt 1 ] || [ "$$n" -gt "$$i" ] && { echo "error: index $$n out of range (1~$$i)"; exit 1; }; \
		sel_a=`echo "$$apps" | cut -d' ' -f "$$n"`; \
		sel_a=$$(echo $$sel_a); \
	fi; \
	echo "$$apps" | grep -qw "$$sel_a" || { echo "error: app '$$sel_a' not found under application/$$sel_b/"; exit 1; }; \
	echo "$$sel_a" > $(APP_FILE); \
	# ---------- 3. 应用配置 (应用自带 defconfig 优先) ----------; \
	if [ -f "$(ROOT_DIR)/application/$$sel_b/$$sel_a/defconfig" ]; then \
		src="application/$$sel_b/$$sel_a/defconfig"; \
	else \
		src="configs/$${sel_b}_defconfig"; \
	fi; \
	dts=`sed -n 's/^CONFIG_BOARD_DTS=//p' "$(ROOT_DIR)/$$src" | head -1`; \
	[ -n "$$dts" ] || { echo "error: CONFIG_BOARD_DTS not set in $$src"; exit 1; }; \
	[ -f "$(ROOT_DIR)/$$dts" ] || { echo "error: devicetree not found: $$dts"; exit 1; }; \
	cp "$(ROOT_DIR)/$$src" $(CONFIG_FILE); \
	$(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) >/dev/null; \
	echo "board: $$sel_b"; \
	echo "app:   $$sel_a"; \
	echo "config: $$src"; \
	echo "devicetree: $$dts"

defconfig:
	@cp $(ROOT_DIR)/$(SELECT_DEFCONFIG) $(CONFIG_FILE)
	@$(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) >/dev/null
	@echo "restored $(SELECT_DEFCONFIG) -> $(CONFIG_FILE)"

-include $(DEP_FILES)

clean:
	rm -rf $(BUILD_DIR)

distclean: clean
	rm -f $(CONFIG_FILE) $(BOARD_FILE) $(APP_FILE)

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
