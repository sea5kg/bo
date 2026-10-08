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
  MD5 md5 = MD5(str);
  return md5.hexdigest();
}

std::string md5_by_file(const std::string &filepath) {
  std::ifstream f(filepath, std::ifstream::binary);
  if (!f) {
    return "Could not open file";
  }

  // get length of file:
  f.seekg(0, f.end);
  int nBufferSize = f.tellg();
  f.seekg(0, f.beg);

  char *pBuffer = new char[nBufferSize];

  // read data as a block:
  f.read(pBuffer, nBufferSize);
  if (!f) {
    delete[] pBuffer;
    // f.close();
    return "Could not read file. Only " + std::to_string(f.gcount()) +
           " could be read";
  }
  f.close();

  MD5 md5;
  // deepcode ignore insecureHash: legacy support
  md5.update(pBuffer, nBufferSize);
  md5.finalize();
  return md5.hexdigest();
}

} // namespace bo