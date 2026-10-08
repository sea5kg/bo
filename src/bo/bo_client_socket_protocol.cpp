#include "bo_client_socket_protocol.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <iostream>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>
#include "bo_utils.h"

namespace {

constexpr size_t SEND_BUFFER = 512;

}

BoClientSocketProtocol::BoClientSocketProtocol(const std::string &host,
                                               int port, int timeout)
    : host_(host), port_(port), timeout_(timeout) {

  sock_ = ::socket(AF_INET, SOCK_STREAM, 0);
  if (sock_ < 0)
    bo::fatal(10, "Socket creation failed");

  if (timeout_ > 0) {
    struct timeval tv{timeout_, 0};
    setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock_, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
  }

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(port_));
  inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);

  if (::connect(sock_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) < 0) {
    if (errno == ECONNREFUSED)
      bo::fatal(9, "Connection refused");
    bo::fatal(10, std::string("Socket error: ") + std::strerror(errno));
  }

  char buf[1024] = {0};
  ssize_t n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n > 0) {
    std::string welcome(buf, static_cast<size_t>(n));
    std::cout << "WELCOME " << bo::trim(welcome) << "\n";
  }
}

BoClientSocketProtocol::~BoClientSocketProtocol() {
  if (sock_ >= 0)
    ::close(sock_);
}

BoClientSocketProtocol::BoClientSocketProtocol(
    BoClientSocketProtocol &&other) noexcept
    : host_(std::move(other.host_)), port_(other.port_),
      timeout_(other.timeout_), sock_(other.sock_) {
  other.sock_ = -1;
}

BoClientSocketProtocol &
BoClientSocketProtocol::operator=(BoClientSocketProtocol &&other) noexcept {
  if (this != &other) {
    if (sock_ >= 0)
      ::close(sock_);
    host_ = std::move(other.host_);
    port_ = other.port_;
    timeout_ = other.timeout_;
    sock_ = other.sock_;
    other.sock_ = -1;
  }
  return *this;
}

// ---------------------------------------------------------------
// Отправка параметра
// ---------------------------------------------------------------
void BoClientSocketProtocol::send_param(const std::string &name,
                                        const std::string &value) {
  std::string cmd = name + " " + value + "\n";
  ::send(sock_, cmd.data(), cmd.size(), 0);

  char buf[1024] = {0};
  ssize_t n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n <= 0 || std::string(buf, 8) != "ACCEPTED") {
    bo::fatal(557, std::string("Expected [ACCEPTED] but got [") +
                   std::string(buf, n > 0 ? static_cast<size_t>(n) : 0) + "]");
  }
}

// ---------------------------------------------------------------
// ACTION_REQUEST
// ---------------------------------------------------------------
std::string BoClientSocketProtocol::action_request() {
  std::string cmd = "ACTION_REQUEST\n";
  ::send(sock_, cmd.data(), cmd.size(), 0);

  char buf[1024] = {0};
  ssize_t n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n <= 0)
    return "NO_CONNECTION";
  return bo::trim(std::string(buf, static_cast<size_t>(n)));
}

// ---------------------------------------------------------------
// OUTPUT_REQUEST
// ---------------------------------------------------------------
bool BoClientSocketProtocol::output_request() {
  std::string cmd = "OUTPUT_REQUEST\n";
  ::send(sock_, cmd.data(), cmd.size(), 0);

  char buf[4096] = {0};
  ssize_t n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n <= 0)
    return false;

  std::string resp(buf, static_cast<size_t>(n));

  if (resp.rfind("OUTPUT ", 0) == 0) {
    std::cout << resp.substr(7) << std::flush;
    return true;
  }
  if (resp.rfind("OUTPUT_FINISHED ", 0) == 0) {
    std::cout << ">>>> Exit status: " << resp.substr(16) << "\n\n";
    return false;
  }
  if (resp.rfind("OUTPUT_FAILED ", 0) == 0) {
    std::cout << ">>>> FAILED status: " << resp.substr(14) << "\n\n";
    return false;
  }
  return true;
}

void BoClientSocketProtocol::send_file(const std::string &filepath) {
  std::ifstream f(filepath, std::ios::binary);
  if (!f)
    bo::fatal(600, "Cannot open file " + filepath);

  std::vector<char> buf(SEND_BUFFER);
  while (f) {
    f.read(buf.data(), static_cast<std::streamsize>(buf.size()));
    std::streamsize n = f.gcount();
    if (n > 0)
      ::send(sock_, buf.data(), static_cast<size_t>(n), 0);
  }
  ::send(sock_, "", 0, 0);

  char resp[1024] = {0};
  ssize_t n = ::recv(sock_, resp, sizeof(resp) - 1, 0);
  if (n <= 0 || std::string(resp, 8) != "ACCEPTED") {
    bo::fatal(8, std::string("Expected [ACCEPTED] but got [") +
                 std::string(resp, n > 0 ? static_cast<size_t>(n) : 0) + "]");
  }
}