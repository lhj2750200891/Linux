/*
 * devicetree_generated.h —— 由 scripts/gen_devicetree.py 自动生成, 请勿手改
 * 源: build/dts/gd32f103re.dtb
 * 修改硬件请编辑 boards/ 下设备树(.dts), 重新编译即可。
 */
#ifndef BUILD_GENERATED_DEVICETREE_H
#define BUILD_GENERATED_DEVICETREE_H

/* 根节点信息 */
#define DT_MODEL "GD32F103RE generic board"
#define DT_ROOT_COMPATIBLE "gd,gd32f103re-generic"

#define DT_SYSTICK_CLOCK_FREQUENCY 108000000

#define DT_LEDS_COUNT 3
#define DT_LEDS_INSTANCES \
	{ .port = 2, .pin = 13, .mode = 0x10, .level = 1 }, \
	{ .port = 2, .pin = 9, .mode = 0x10, .level = 1 }, \
	{ .port = 2, .pin = 8, .mode = 0x10, .level = 1 }

#define DT_LED1_IDX 0
#define DT_LED2_IDX 1
#define DT_LED3_IDX 2

#define DT_KEYS_COUNT 4
#define DT_KEYS_INSTANCES \
	{ .port = 0, .pin = 7, .mode = 0x48, .level = 0 }, \
	{ .port = 2, .pin = 4, .mode = 0x48, .level = 0 }, \
	{ .port = 2, .pin = 5, .mode = 0x48, .level = 0 }, \
	{ .port = 0, .pin = 0, .mode = 0x28, .level = 1 }

#define DT_KEY1_IDX 0
#define DT_KEY2_IDX 1
#define DT_KEY3_IDX 2
#define DT_KEY4_IDX 3

#define DT_MATRIX_KEYS_ROW_COUNT 4
#define DT_MATRIX_KEYS_ROW_INSTANCES \
	{ .port = 2, .pin = 0, .mode = 0x10, .level = 0 }, \
	{ .port = 2, .pin = 1, .mode = 0x10, .level = 0 }, \
	{ .port = 2, .pin = 2, .mode = 0x10, .level = 0 }, \
	{ .port = 2, .pin = 3, .mode = 0x10, .level = 0 }

#define DT_MATRIX_KEYS_COL_COUNT 3
#define DT_MATRIX_KEYS_COL_INSTANCES \
	{ .port = 0, .pin = 4, .mode = 0x48, .level = 0 }, \
	{ .port = 0, .pin = 5, .mode = 0x48, .level = 0 }, \
	{ .port = 0, .pin = 6, .mode = 0x48, .level = 0 }


#endif
