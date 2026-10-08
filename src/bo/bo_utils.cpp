// bo_utils.cpp
#include "bo_utils.h"

#include <cstdlib>
#include <iostream>

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