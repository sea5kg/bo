// bo_utils.h
#pragma once

#include <string>

namespace bo {

[[noreturn]] void fatal(int code, const std::string &msg);

std::string trim(const std::string &s);

std::string md5_by_string(const std::string &str);
std::string md5_by_file(const std::string &filepath);

} // namespace bo
