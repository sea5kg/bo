// bo_utils.cpp
#include "bo_utils.h"
#include "third_party/md5/md5.h"

#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>

namespace bo {

[[noreturn]] void fatal(int code, const std::string &msg) {
  std::cerr << "\nERROR (" << code << ") " << msg << "\n";
  std::exit(-1);
}

std::string trim(const std::string &s) {
  size_t a = s.find_first_not_of(" \t\r\n");
  if (a == std::string::npos)
    return "";
  size_t b = s.find_last_not_of(" \t\r\n");
  return s.substr(a, b - a + 1);
}

std::string md5_by_string(const std::string &str) {
  MD5 md5(str);
  return md5.hexdigest();
}

std::string md5_by_file(const std::string &filepath) {
  std::ifstream f(filepath, std::ios::binary);
  if (!f) {
    return "NO-HASH: Could not open file. NO-HASH";
  }

  MD5 md5;
  char buf[65536];
  while (f) {
    f.read(buf, sizeof(buf));
    const std::streamsize n = f.gcount();
    if (n > 0)
      md5.update(buf, static_cast<unsigned int>(n));
  }
  md5.finalize();
  return md5.hexdigest();
}

// ---------------------------------------------------------------
// Winsock RAII
// ---------------------------------------------------------------
#ifdef _WIN32
namespace {
WSADATA g_wsa_data;
bool    g_wsa_initialized = false;
} // namespace
#endif

init_win_sockets::init_win_sockets() {
#ifdef _WIN32
  if (!g_wsa_initialized) {
    if (WSAStartup(MAKEWORD(2, 2), &g_wsa_data) != 0) {
      fatal(1, "WSAStartup failed");
    }
    g_wsa_initialized = true;
  }
#endif
}
init_win_sockets::~init_win_sockets() {
#ifdef _WIN32
  if (g_wsa_initialized) {
    WSACleanup();
    g_wsa_initialized = false;
  }
#endif
}

} // namespace bo