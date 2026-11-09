#pragma once
// CyberHand 舵机协议帧构造/解析(纯函数, 无状态), 对应 python 版同名函数
// 帧格式: FF FF | FE | LEN | 83 | 2A | 02 | (ID,位置高,位置低)xN | 校验(~sum&0xFF, 不含FF FF)
#include <cstddef>
#include <cstdint>
#include <map>
#include <vector>

namespace cyber {

// 多舵机同步位置指令帧. pos: {ID: 位置1~1024}
std::vector<uint8_t> sync_write_frame(const std::map<int, int>& pos);

// 读取舵机当前位置指令: FF FF ID 04 02 38 02 校验
std::vector<uint8_t> read_position_cmd(int sid);

// 解析读位应答: FF FF ID 04 00 位置高 位置低 校验, 位置=(高<<8|低)+1; 非法返回-1
int parse_position(const uint8_t* rx, size_t len);

}  // namespace cyber
