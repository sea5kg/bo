#include "bo_client_socket_protocol.h"
#include "bo_utils.h"

#include <fstream>
#include <iostream>
#include <vector>

#ifdef _WIN32
// winsock2.h уже подключён в bo_utils.h
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace {
constexpr size_t SEND_BUFFER = 512;
}

// ---------------------------------------------------------------
// Конструктор
// ---------------------------------------------------------------
BoClientSocketProtocol::BoClientSocketProtocol(const std::string &host,
                                               int port, int timeout)
    : host_(host), port_(port), timeout_(timeout) {

#ifdef _WIN32
  sock_ = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (sock_ == INVALID_SOCKET)
    bo::fatal(10, "Socket creation failed");
#else
  sock_ = ::socket(AF_INET, SOCK_STREAM, 0);
  if (sock_ < 0)
    bo::fatal(10, "Socket creation failed");
#endif

  if (timeout_ > 0) {
#ifdef _WIN32
    DWORD tv = static_cast<DWORD>(timeout_ * 1000); // мс
    setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char *>(&tv), sizeof(tv));
    setsockopt(sock_, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char *>(&tv), sizeof(tv));
#else
    struct timeval tv{timeout_, 0};
    setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock_, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif
  }

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(port_));

#ifdef _WIN32
  if (InetPtonA(AF_INET, host_.c_str(), &addr.sin_addr) != 1) {
    // попытка resolve через getaddrinfo
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo *res = nullptr;
    if (getaddrinfo(host_.c_str(), nullptr, &hints, &res) != 0 || !res) {
      bo::fatal(10, "Cannot resolve host: " + host_);
    }
    addr.sin_addr = reinterpret_cast<sockaddr_in *>(res->ai_addr)->sin_addr;
    freeaddrinfo(res);
  }
#else
  inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);
#endif

  if (::connect(sock_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr))
#ifdef _WIN32
      == SOCKET_ERROR
#else
      < 0
#endif
  ) {
    int err = SOCKET_ERRNO;
    if (err == ECONNREFUSED_WIN)
      bo::fatal(9, "Connection refused");
    bo::fatal(10, "Socket error: " + std::to_string(err));
  }

  char buf[1024] = {0};
  int n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n > 0) {
    std::string welcome(buf, static_cast<size_t>(n));
    std::cout << "WELCOME " << bo::trim(welcome) << "\n";
  }
}

// ---------------------------------------------------------------
// Деструктор
// ---------------------------------------------------------------
BoClientSocketProtocol::~BoClientSocketProtocol() {
#ifdef _WIN32
  if (sock_ != INVALID_SOCKET)
    CLOSE_SOCKET(sock_);
#else
  if (sock_ >= 0)
    CLOSE_SOCKET(sock_);
#endif
}

// ---------------------------------------------------------------
// Перемещение
// ---------------------------------------------------------------
BoClientSocketProtocol::BoClientSocketProtocol(
    BoClientSocketProtocol &&other) noexcept
    : host_(std::move(other.host_)), port_(other.port_),
      timeout_(other.timeout_), sock_(other.sock_) {
#ifdef _WIN32
  other.sock_ = INVALID_SOCKET;
#else
  other.sock_ = -1;
#endif
}

BoClientSocketProtocol &
BoClientSocketProtocol::operator=(BoClientSocketProtocol &&other) noexcept {
  if (this != &other) {
#ifdef _WIN32
    if (sock_ != INVALID_SOCKET)
      CLOSE_SOCKET(sock_);
#else
    if (sock_ >= 0)
      CLOSE_SOCKET(sock_);
#endif
    host_ = std::move(other.host_);
    port_ = other.port_;
    timeout_ = other.timeout_;
    sock_ = other.sock_;
#ifdef _WIN32
    other.sock_ = INVALID_SOCKET;
#else
    other.sock_ = -1;
#endif
  }
  return *this;
}

// ---------------------------------------------------------------
// send_param
// ---------------------------------------------------------------
void BoClientSocketProtocol::send_param(const std::string &name,
                                        const std::string &value) {
  std::string cmd = name + " " + value + "\n";
  ::send(sock_, cmd.data(), static_cast<int>(cmd.size()), 0);

  char buf[1024] = {0};
  int n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n <= 0 || std::string(buf, 8) != "ACCEPTED") {
    bo::fatal(557, std::string("Expected [ACCEPTED] but got [") +
                   std::string(buf, n > 0 ? static_cast<size_t>(n) : 0) + "]");
  }
}

// ---------------------------------------------------------------
// action_request
// ---------------------------------------------------------------
std::string BoClientSocketProtocol::action_request() {
  std::string cmd = "ACTION_REQUEST\n";
  ::send(sock_, cmd.data(), static_cast<int>(cmd.size()), 0);

  char buf[1024] = {0};
  int n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
  if (n <= 0)
    return "NO_CONNECTION";
  return bo::trim(std::string(buf, static_cast<size_t>(n)));
}

// ---------------------------------------------------------------
// output_request
// ---------------------------------------------------------------
bool BoClientSocketProtocol::output_request() {
  std::string cmd = "OUTPUT_REQUEST\n";
  ::send(sock_, cmd.data(), static_cast<int>(cmd.size()), 0);

  char buf[4096] = {0};
  int n = ::recv(sock_, buf, sizeof(buf) - 1, 0);
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

// ---------------------------------------------------------------
// send_file
// ---------------------------------------------------------------
void BoClientSocketProtocol::send_file(const std::string &filepath) {
  std::ifstream f(filepath, std::ios::binary);
  if (!f)
    bo::fatal(600, "Cannot open file " + filepath);

  std::vector<char> buf(SEND_BUFFER);
  while (f) {
    f.read(buf.data(), static_cast<std::streamsize>(buf.size()));
    std::streamsize n = f.gcount();
    if (n > 0)
      ::send(sock_, buf.data(), static_cast<int>(n), 0);
  }
  ::send(sock_, "", 0, 0);

  char resp[1024] = {0};
  int n = ::recv(sock_, resp, sizeof(resp) - 1, 0);
  if (n <= 0 || std::string(resp, 8) != "ACCEPTED") {
    bo::fatal(8, std::string("Expected [ACCEPTED] but got [") +
                 std::string(resp, n > 0 ? static_cast<size_t>(n) : 0) + "]");
  }
}