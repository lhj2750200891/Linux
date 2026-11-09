#include "protocol.hpp"

namespace cyber {

std::vector<uint8_t> sync_write_frame(const std::map<int, int>& pos) {
    std::vector<uint8_t> body{0xFE, (uint8_t)(3 + 3 * pos.size() + 1), 0x83, 0x2A, 0x02};
    for (const auto& kv : pos) {                     // std::map天然按ID升序, 同python sorted(pos)
        int v = kv.second;
        if (v < 1) v = 1;
        if (v > 1024) v = 1024;
        v -= 1;
        body.push_back((uint8_t)kv.first);
        body.push_back((uint8_t)((v >> 8) & 0xFF));
        body.push_back((uint8_t)(v & 0xFF));
    }
    int sum = 0;
    for (uint8_t b : body) sum += b;
    std::vector<uint8_t> frame{0xFF, 0xFF};
    frame.insert(frame.end(), body.begin(), body.end());
    frame.push_back((uint8_t)((~sum) & 0xFF));
    return frame;
}

std::vector<uint8_t> read_position_cmd(int sid) {
    std::vector<uint8_t> body{(uint8_t)sid, 0x04, 0x02, 0x38, 0x02};
    int sum = 0;
    for (uint8_t b : body) sum += b;
    std::vector<uint8_t> frame{0xFF, 0xFF};
    frame.insert(frame.end(), body.begin(), body.end());
    frame.push_back((uint8_t)((~sum) & 0xFF));
    return frame;
}

int parse_position(const uint8_t* rx, size_t len) {
    if (len >= 8 && rx[0] == 0xFF && rx[1] == 0xFF) {
        return ((rx[5] << 8) | rx[6]) + 1;
    }
    return -1;
}

}  // namespace cyber
