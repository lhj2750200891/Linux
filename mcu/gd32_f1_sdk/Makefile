###############################################################################
# GD32F10x Makefile (框架版: Kconfig 配置 + 编译期设备树)
# 适用于 GD32F10x (Cortex-M3)
#
# 构建流程:
#   1) .config 不存在时, 自动从 configs/$(BOARD)_defconfig 复制
#   2) scripts/kconfigconf.py     : Kconfig + .config -> build/generated/autoconf.h
#                                   (autoconf.h 被强制包含进所有 C 文件)
#   3) cpp + dtc                  : boards/$(BOARD)/$(BOARD).dts -> build/dts/*.dtb
#   4) scripts/gen_devicetree.py  : dtb -> build/generated/devicetree_generated.h
#                                   (引脚信息编译期进固件, 驱动只认这个头文件)
#   5) .config 中的 CONFIG_xxx 通过 obj-y 决定哪些驱动参与编译
#
# 常用命令:
#   make lunch                      交互式选择板卡: 输入序号, 直接回车=默认(当前板卡)
#   make lunch BOARD=<板卡名>       免交互直接选择板卡
#   make                            编译当前板卡固件 -> build/bin/<板卡名>.bin
#   make defconfig                  恢复当前板卡默认配置 (configs/<板卡>_defconfig)
#   make clean                      清理 build/
#   make distclean                  清理 build/ + .config + .board (回到未选择状态)
#   make download                   OpenOCD + J-Link 烧录当前板卡固件
#
# 多板卡约定(一个工程多块板, 无需新建工程):
#   每块板 = configs/<板卡>_defconfig (板卡身份: 指定 CONFIG_BOARD_DTS 设备树 + 驱动裁剪)
#          + 该 defconfig 声明的 .dts 设备树文件
#   切换板卡只需 make lunch, 驱动代码完全共用
###############################################################################

# 项目根目录 (固件按板卡命名: build/bin/<板卡名>.bin)
ROOT_DIR    = .
TARGET      = $(BOARD)

# ===== 板卡选择 =====
# 选择结果持久化在 .board 文件中, 由 make lunch 写入
BOARD_FILE   = .board
CONFIG_FILE  = .config
DEFCONFIG    = configs/$(BOARD)_defconfig
# 一块板 = boards/ 下有目录, 且 configs/ 下有 <板名>_defconfig
AVAILABLE_BOARDS = $(foreach b,$(sort $(notdir $(patsubst %/,%,$(dir $(wildcard $(ROOT_DIR)/boards/*/))))),$(if $(wildcard $(ROOT_DIR)/configs/$(b)_defconfig),$(b)))
CURRENT_BOARD := $(shell cat $(BOARD_FILE) 2>/dev/null)
# 命令行显式传入的 BOARD (make lunch BOARD=xxx 时用)
BOARD_ON_CMD := $(if $(filter command%,$(origin BOARD)),$(BOARD),)

# 板卡解析只对构建类目标执行; lunch/clean/distclean 跳过
ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)

ifneq ($(BOARD_ON_CMD),)
# make BOARD=xxx: 与已选板卡一致才放行, 切换板卡必须走 make lunch
ifneq ($(CURRENT_BOARD),)
ifneq ($(CURRENT_BOARD),$(BOARD_ON_CMD))
$(error BOARD=$(BOARD_ON_CMD) 与当前板卡 '$(CURRENT_BOARD)' 不一致, 切换板卡请运行: make lunch BOARD=$(BOARD_ON_CMD))
endif
else
# 首次构建: 采纳命令行板卡并记录
CURRENT_BOARD := $(BOARD_ON_CMD)
$(shell echo $(BOARD_ON_CMD) > $(BOARD_FILE))
endif
BOARD := $(BOARD_ON_CMD)
else
BOARD := $(CURRENT_BOARD)
ifeq ($(BOARD),)
# 从未选择: 工程里只有一块板时自动选中并记录
ifeq ($(words $(AVAILABLE_BOARDS)),1)
BOARD := $(word 1,$(AVAILABLE_BOARDS))
$(shell echo $(BOARD) > $(BOARD_FILE))
endif
endif
endif

ifeq ($(BOARD),)
$(error 未选择板卡: 请先运行 'make lunch' 选择板卡)
endif

# 首次构建: .config 不存在时自动使用当前板卡的默认配置
ifeq ($(wildcard $(CONFIG_FILE)),)
ifeq ($(wildcard $(DEFCONFIG)),)
$(error 未找到板级配置 $(DEFCONFIG), 请检查 BOARD=$(BOARD) 是否正确)
endif
$(shell cp $(DEFCONFIG) $(CONFIG_FILE))
endif

endif   # 板卡解析结束 (lunch/clean/distclean 跳过)

# 读入配置: CONFIG_xxx 在 Makefile 中变为变量 (驱动裁剪 + 设备树选择)
-include $(CONFIG_FILE)

# 设备树由 defconfig 中的 CONFIG_BOARD_DTS 指定 (板卡与硬件描述在此绑定)
DT_FILE = $(strip $(CONFIG_BOARD_DTS))

ifeq ($(filter lunch clean distclean,$(MAKECMDGOALS)),)
ifeq ($(DT_FILE),)
$(error defconfig 未指定设备树: 请在 configs/$(BOARD)_defconfig 中声明 CONFIG_BOARD_DTS=<设备树路径>)
endif
endif

# 地址
FLASH_START := 0x08000000
RAM_START   := 0x20000000

# 目录配置
BUILD_DIR   = build
BIN_DIR     = $(BUILD_DIR)/bin
OBJ_DIR     = $(BUILD_DIR)/obj
GEN_DIR     = $(BUILD_DIR)/generated
DTS_DIR     = $(BUILD_DIR)/dts

# 生成文件
AUTOCONF    = $(GEN_DIR)/autoconf.h
DTB         = $(DTS_DIR)/$(BOARD).dtb
DTS_PP      = $(DTS_DIR)/$(BOARD).dts.pp
DT_HEADER   = $(GEN_DIR)/devicetree_generated.h

# 目标芯片配置
MCU_SERIES  = GD32F10x
MCU_CPU     = cortex-m3

# 编译器配置
COMPILER    = /usr/local/arm/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-
CC          = $(COMPILER)gcc
AS          = $(COMPILER)gcc
LD          = $(COMPILER)gcc
OBJCOPY     = $(COMPILER)objcopy
SIZE        = $(COMPILER)size
CPP         = cpp
PYTHON      ?= python3

# 驱动裁剪 (内核风格 obj-y): obj-$(CONFIG_xxx) 展开为 obj-y/obj-n, 只收集 obj-y
obj-$(CONFIG_DRIVER_SYSTICK)    += drivers/systick/systick_gd32.c
obj-$(CONFIG_DRIVER_GPIO_GD32)  += drivers/gpio/gpio_gd32.c
obj-$(CONFIG_DRIVER_LED)        += drivers/led/led_gd32.c
obj-$(CONFIG_DRIVER_KEY)        += drivers/key/key_gd32.c
obj-$(CONFIG_DRIVER_MATRIX_KEY) += drivers/matrix_key/matrix_key_gd32.c
DRIVER_SOURCES  = $(addprefix $(ROOT_DIR)/,$(obj-y))   # 统一为 ./xxx 路径, 与 C_OBJECTS 转换规则一致
DRIVER_INCLUDES = $(foreach d,$(wildcard $(ROOT_DIR)/drivers/*/),-I$(d))

# 编译选项
# MCU 编译参数 (Cortex-M3, 无 FPU, 软浮点)
MCU_FLAGS   = -mcpu=$(MCU_CPU) -mthumb -mfloat-abi=soft

# 优化级别
OPT         = -Os

# C 编译标志
CFLAGS      = $(MCU_FLAGS) $(OPT) -Wall -fdata-sections -ffunction-sections
CFLAGS     += -std=gnu11 -MMD -MP -MF"$(@:%.o=%.d)"
CFLAGS     += -D$(MCU_SERIES) -DGD32F10X_HD -DUSE_STDPERIPH_DRIVER
CFLAGS     += -DFLASH_START=$(FLASH_START) -DRAM_START=$(RAM_START)     # 定义闪存和RAM起始地址,可以在代码中使用这些宏
CFLAGS     += -I$(GEN_DIR) -include $(AUTOCONF)                         # 强制包含配置头文件, 所有 C 文件都能用 CONFIG_xxx

# 汇编编译标志
ASFLAGS     = $(MCU_FLAGS) -c

# 链接标志
LD_SCRIPT   = $(ROOT_DIR)/vendor/cmsis/device/gd32f10x_flash.ld
LDFLAGS     = $(MCU_FLAGS) $(OPT) -T$(LD_SCRIPT)
LDFLAGS    += -Wl,-Map="$(BUILD_DIR)/$(TARGET).map"
LDFLAGS    += -Wl,--gc-sections -Wl,--print-memory-usage
LDFLAGS    += -specs=nano.specs -specs=nosys.specs
LDFLAGS    += -Wl,--start-group -lc -lm -lnosys -Wl,--end-group
LDFLAGS    += -Wl,--defsym=FLASH_START=$(FLASH_START)   # 定义闪存起始地址为链接器符号 FLASH_START，可以在链接脚本中使用这个符号来设置代码段的起始地址
LDFLAGS    += -Wl,--defsym=RAM_START=$(RAM_START)  # 定义RAM起始地址为链接器符号 RAM_START，可以在链接脚本中使用这个符号来设置数据段的起始地址

# 包含目录
INCLUDES    = -I$(ROOT_DIR)/vendor/cmsis/core \
              -I$(ROOT_DIR)/vendor/cmsis/device \
              -I$(ROOT_DIR)/vendor/fwlib/include \
              -I$(ROOT_DIR)/user \
              $(DRIVER_INCLUDES)

# 设备树预处理参数 (板卡 dts 所在目录 + SoC dtsi + dt-bindings)
DTS_INCLUDES = -I$(dir $(DT_FILE)) \
               -I$(ROOT_DIR)/dts \
               -I$(ROOT_DIR)/dts/include

# 源文件 (vendor/ 为芯片厂提供内容, 按目录通配)
C_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.c) \
              $(wildcard $(ROOT_DIR)/vendor/fwlib/source/*.c) \
              $(wildcard $(ROOT_DIR)/user/*.c) \
              $(DRIVER_SOURCES)

# 汇编路径
ASM_SOURCES   = $(wildcard $(ROOT_DIR)/vendor/cmsis/device/*.S)

# 目标文件
C_OBJECTS     = $(C_SOURCES:$(ROOT_DIR)/%.c=$(OBJ_DIR)/%.o)
ASM_OBJECTS   = $(ASM_SOURCES:$(ROOT_DIR)/%.S=$(OBJ_DIR)/%.o)
OBJECTS       = $(ASM_OBJECTS) $(C_OBJECTS)

# 依赖文件 (由 -MMD 生成, 头文件改动自动触发重编译)
DEP_FILES     = $(OBJECTS:.o=.d)

# Makefile 语法
# 目标：依赖
# 	命令

# 默认目标
all: $(BIN_DIR)/$(TARGET).bin $(BIN_DIR)/$(TARGET).hex | show-board

.PHONY: show-board
show-board:
	@echo "板卡: $(BOARD)    设备树: $(DT_FILE)"

# ===== 配置生成 =====
# Kconfig 文件变动时重新生成 (脚本会补全 .config 中缺失的默认值)
$(AUTOCONF): $(CONFIG_FILE) $(wildcard Kconfig drivers/Kconfig) scripts/kconfigconf.py
	@echo "生成配置头文件: $@"
	@mkdir -p $(@D)
	$(PYTHON) scripts/kconfigconf.py --kconfig Kconfig --config $(CONFIG_FILE) --autoconf $@

# ===== 设备树生成 =====
# 1) cpp 预处理 -> 2) dtc 编译 DTB -> 3) python 生成 C 头文件
# .board 也作为依赖: lunch 切换板卡后, 已存在的旧 DTB(mtime 较旧)必须强制重建,
# 否则共用路径的 devicetree_generated.h 不会重新生成, 新板会拿上一块板的设备树编译
$(DTB): $(DT_FILE) $(BOARD_FILE) $(wildcard dts/*.dtsi) $(wildcard dts/include/dt-bindings/**/*.h)
	@echo "编译设备树: $<"
	@mkdir -p $(@D)
	$(CPP) -E -x assembler-with-cpp -nostdinc -undef $(DTS_INCLUDES) -o $(DTS_PP) $<
	dtc -I dts -O dtb -o $@ $(DTS_PP)

$(DT_HEADER): $(DTB) scripts/gen_devicetree.py
	@echo "生成设备树头文件: $@"
	$(PYTHON) scripts/gen_devicetree.py --dtb $< --out $@

# 二进制文件
$(BIN_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	@echo "生成 BIN 文件: $(BIN_DIR)/$(TARGET).bin"
	@mkdir -p $(@D)
	$(OBJCOPY) -O binary $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).bin

# HEX文件
$(BIN_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	@echo "生成 HEX 文件: $(BIN_DIR)/$(TARGET).hex"
	@mkdir -p $(@D)
	$(OBJCOPY) -O ihex $(BUILD_DIR)/$(TARGET).elf $(BIN_DIR)/$(TARGET).hex

# ELF文件
$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS) $(AUTOCONF) $(DT_HEADER)
	@echo "链接目标文件: $@"
	@mkdir -p $(@D)
	$(LD) $(OBJECTS) $(LDFLAGS) -o $@
	$(SIZE) $@
	@echo "构建完成: $(TARGET).elf"

# 编译C文件 (依赖生成头文件: 配置/设备树任何变动都会重新编译)
$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.c $(AUTOCONF) $(DT_HEADER)
	@echo "编译 C 文件: $<"
	@mkdir -p $(@D)
	$(CC) -c $(CFLAGS) $(INCLUDES) -o $@ $<

# 编译.S汇编文件
$(OBJ_DIR)/%.o: $(ROOT_DIR)/%.S
	@echo "编译 ASM 文件: $<"
	@mkdir -p $(@D)
	$(AS) -c $(ASFLAGS) $(INCLUDES) -o $@ $<

# ===== 板卡选择 (类比 Android / 瑞芯微 lunch) =====
# make lunch               交互式: 列出编号菜单, 输入序号, 回车=默认(当前板卡)
# make lunch BOARD=<名称>  免交互: 直接选择(脚本/CI 用)
# 选择后写入 .board 与 .config, 之后 make 即编译该板固件
lunch:
	@echo "================================================"
	@echo " 当前板卡: $(if $(CURRENT_BOARD),$(CURRENT_BOARD),<未选择>)"
	@echo " 可选板卡 (configs/ 下有对应 _defconfig 的板):"
	@i=0; cur=0; \
	for b in $(AVAILABLE_BOARDS); do \
		i=$$((i+1)); \
		if [ "$$b" = "$(CURRENT_BOARD)" ]; then \
			cur=$$i; \
			echo "   * $$i. $$b   <- 当前"; \
		else \
			echo "     $$i. $$b"; \
		fi; \
	done; \
	if [ "$$i" -eq 0 ]; then \
		echo "错误: 没有可用板卡 (缺少 configs/*_defconfig)"; \
		exit 1; \
	fi; \
	if [ -n "$(BOARD_ON_CMD)" ]; then \
		sel="$(BOARD_ON_CMD)"; \
	else \
		def=$${cur:-1}; \
		printf "请选择板卡序号 [%s] (回车=默认): " "$$def"; \
		read n; \
		[ -z "$$n" ] && n=$$def; \
		case "$$n" in *[!0-9]*|'') echo "错误: '$$n' 不是数字序号"; exit 1;; esac; \
		if [ "$$n" -lt 1 ] || [ "$$n" -gt "$$i" ]; then \
			echo "错误: 序号 $$n 超出范围 (1~$$i)"; \
			exit 1; \
		fi; \
		sel=`echo "$(AVAILABLE_BOARDS)" | cut -d' ' -f "$$n"`; \
	fi; \
	valid=0; \
	for b in $(AVAILABLE_BOARDS); do \
		if [ "$$b" = "$$sel" ]; then valid=1; break; fi; \
	done; \
	if [ "$$valid" != "1" ]; then \
		echo "错误: 板卡 '$$sel' 不存在 (缺少 configs/$${sel}_defconfig)"; \
		exit 1; \
	fi; \
	if ! grep -q '^CONFIG_BOARD_DTS=' "$(ROOT_DIR)/configs/$${sel}_defconfig"; then \
		echo "错误: configs/$${sel}_defconfig 缺少 CONFIG_BOARD_DTS= 设备树声明"; \
		exit 1; \
	fi; \
	dts=`sed -n 's/^CONFIG_BOARD_DTS=//p' "$(ROOT_DIR)/configs/$${sel}_defconfig" | head -1`; \
	if [ ! -f "$$dts" ]; then \
		echo "错误: defconfig 声明的设备树不存在: $$dts"; \
		exit 1; \
	fi; \
	echo "$$sel" > $(BOARD_FILE); \
	cp "$(ROOT_DIR)/configs/$${sel}_defconfig" $(CONFIG_FILE); \
	echo ""; \
	echo "已选择板卡: $$sel"; \
	echo "设备树    : $$dts  (由 defconfig 的 CONFIG_BOARD_DTS 指定)"; \
	echo "配置就绪  : 运行 make 编译, 固件输出 $(BIN_DIR)/$$sel.bin"

# 从当前板卡的 defconfig 恢复默认配置
defconfig:
	@cp $(DEFCONFIG) $(CONFIG_FILE)
	@echo "已恢复默认配置 $(DEFCONFIG) -> $(CONFIG_FILE), 重新 make 即可生效"

# 包含依赖文件
-include $(DEP_FILES)

clean:
	@echo "清理构建文件..."
	rm -rf $(BUILD_DIR)

distclean: clean
	@echo "清理配置与板卡选择..."
	rm -f $(CONFIG_FILE) $(BOARD_FILE)

download: $(BIN_DIR)/$(TARGET).bin
	@echo "Cortex-M3 开始使用JLink V32g 烧录..."
	@echo "OpenOCD + J-Link 烧录 GD32F10x 需要安装OpenOCD驱动"
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
	@if [ $$? -eq 0 ]; then \
		echo "Cortex-M3 烧录完成！！！"; \
	else \
		echo "Cortex-M3 烧录失败！！！"; \
	fi

.PHONY: all clean distclean defconfig lunch show-board download
