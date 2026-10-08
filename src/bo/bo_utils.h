#pragma once

#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
using socklen_t = int;
using ssize_t = SSIZE_T; // в MSVC нет ssize_t
#define CLOSE_SOCKET(s) closesocket(s)
#define SOCKET_ERRNO WSAGetLastError()
#define ECONNREFUSED_WIN WSAECONNREFUSED
#else
#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#define CLOSE_SOCKET(s) ::close(s)
#define SOCKET_ERRNO errno
#define ECONNREFUSED_WIN ECONNREFUSED
#endif

namespace bo {

[[noreturn]] void fatal(int code, const std::string &msg);

std::string trim(const std::string &s);

std::string md5_by_string(const std::string &str);
std::string md5_by_file(const std::string &filepath);

class init_win_sockets {
public:
  init_win_sockets();
  ~init_win_sockets();
};

} // namespace bo
