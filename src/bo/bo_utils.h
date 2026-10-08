// bo_utils.h
#pragma once

#include <string>

[[noreturn]] void fatal(int code, const std::string &msg);

std::string trim(const std::string &s);