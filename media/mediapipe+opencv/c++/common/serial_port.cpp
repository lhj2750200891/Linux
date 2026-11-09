#include "serial_port.hpp"
#include "timing.hpp"

#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <cerrno>

static speed_t to_speed(int baud) {
    switch (baud) {
        case 9600:    return B9600;
        case 115200:  return B115200;
        case 460800:  return B460800;
        case 921600:  return B921600;
        case 1000000: return B1000000;
        case 2000000: return B2000000;
        default:      return B1000000;
    }
}

SerialPort::~SerialPort() { close(); }

bool SerialPort::open(const std::string& dev, int baud) {
    close();
    fd_ = ::open(dev.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd_ < 0) return false;
    termios tio{};
    if (tcgetattr(fd_, &tio) != 0) { close(); return false; }
    cfmakeraw(&tio);                                   // raw模式: 无行缓冲/无转义
    speed_t sp = to_speed(baud);
    cfsetispeed(&tio, sp);
    cfsetospeed(&tio, sp);
    tio.c_cflag |= CLOCAL | CREAD;
    tio.c_cflag &= ~(CSTOPB | PARENB | CSIZE);
    tio.c_cflag |= CS8;                                // 8N1
    tio.c_cc[VMIN]  = 0;                               // 非阻塞读: 没数据立即返回
    tio.c_cc[VTIME] = 0;
    if (tcsetattr(fd_, TCSANOW, &tio) != 0) { close(); return false; }
    tcflush(fd_, TCIOFLUSH);
    return true;
}

void SerialPort::close() {
    if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
}

bool SerialPort::write_all(const std::vector<uint8_t>& data) {
    if (fd_ < 0) return false;
    size_t off = 0;
    while (off < data.size()) {
        ssize_t r = ::write(fd_, data.data() + off, data.size() - off);
        if (r < 0) {
            if (errno == EAGAIN || errno == EINTR) { sleep_ms(1); continue; }
            return false;
        }
        off += (size_t)r;
    }
    return true;
}

void SerialPort::drain_input() {
    if (fd_ < 0) return;
    uint8_t buf[256];
    while (::read(fd_, buf, sizeof buf) > 0) {}
}

bool SerialPort::wait_bytes(size_t n, int timeout_ms, std::vector<uint8_t>& out) {
    out.clear();
    if (fd_ < 0) return false;
    std::vector<uint8_t> acc;
    double t0 = now_s();
    while (now_s() - t0 < timeout_ms / 1000.0) {
        uint8_t buf[64];
        ssize_t r = ::read(fd_, buf, sizeof buf);
        if (r > 0) acc.insert(acc.end(), buf, buf + r);
        if (acc.size() >= n) {
            out.assign(acc.begin(), acc.begin() + (long)n);
            return true;
        }
        sleep_ms(1);
    }
    return false;
}
