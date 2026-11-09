#pragma once
// 串口收发(termios raw 8N1), 对应 python 版的 serial.Serial
#include <cstdint>
#include <string>
#include <vector>

class SerialPort {
public:
    SerialPort() = default;
    ~SerialPort();
    SerialPort(const SerialPort&) = delete;
    SerialPort& operator=(const SerialPort&) = delete;

    // 打开串口, raw 8N1, 非阻塞. 成功返回true
    bool open(const std::string& dev, int baud);
    void close();
    bool is_open() const { return fd_ >= 0; }

    // 写完整帧, 失败返回false(调用方抛异常/报错)
    bool write_all(const std::vector<uint8_t>& data);

    // 读走输入缓冲区里现有的所有字节并丢弃(清杂散应答, 对应 python reset_input_buffer)
    void drain_input();

    // 等待收到至少n字节(超时timeout_ms), 读到的前n字节放out; 成功返回true
    bool wait_bytes(size_t n, int timeout_ms, std::vector<uint8_t>& out);

private:
    int fd_ = -1;
};
