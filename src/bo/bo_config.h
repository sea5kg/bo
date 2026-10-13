#pragma once

#include "bo_global.h"
#include <filesystem>
#include <sstream>

struct ServerConfig {
  std::string host = "127.0.0.1";
  int port = bo::DEFAULT_PORT;
  std::string target_dir;
  std::string cache_path;
};

struct WorkdirConfig {
  std::string workdir;
  ServerConfig server; // base
  std::map<std::string, std::vector<std::string>> commands;
};

class BoConfig {
public:
  std::string config_path;
  std::string bo_home_config_dir;
  std::vector<WorkdirConfig> workdirs;

  void init() {
    const char *bo_home = std::getenv("BO_HOME");
    // std::cout << "bo_home: " << bo_home << std::endl;
    if (bo_home) {
      bo_home_config_dir = std::string(bo_home);
    } else {
      std::cout << "env.BO_HOME not found " << std::endl;
      const char *home = std::getenv("HOME");
      bo_home_config_dir = std::string(home ? home : ".") + "/.bo-by-sea5kg";
    }
    std::cout << "bo_home_config_dir " << bo_home_config_dir << std::endl;
    std::filesystem::create_directories(bo_home_config_dir);
    config_path = bo_home_config_dir + "/config.yml";
    load();
  }

  void load() {
    workdirs.clear();
    std::ifstream f(config_path);
    if (!f)
      return;
    std::string line;
    WorkdirConfig cur;
    bool in_workdir = false;
    while (std::getline(f, line)) {
      line = bo::trim(line);
      if (line.empty())
        continue;
      if (line.rfind("workdir:", 0) == 0) {
        if (in_workdir)
          workdirs.push_back(cur);
        cur = WorkdirConfig{};
        cur.workdir = bo::trim(line.substr(8));
        in_workdir = true;
      } else if (line.rfind("host:", 0) == 0) {
        cur.server.host = bo::trim(line.substr(5));
      } else if (line.rfind("port:", 0) == 0) {
        cur.server.port = std::stoi(bo::trim(line.substr(5)));
      } else if (line.rfind("target_dir:", 0) == 0) {
        cur.server.target_dir = bo::trim(line.substr(11));
      } else if (line.rfind("cache_path:", 0) == 0) {
        cur.server.cache_path = bo::trim(line.substr(11));
      }
    }
    if (in_workdir)
      workdirs.push_back(cur);
  }

  void save() {
    std::ofstream f(config_path);
    for (const auto &w : workdirs) {
      f << "workdir: " << w.workdir << "\n";
      f << "host: " << w.server.host << "\n";
      f << "port: " << w.server.port << "\n";
      f << "target_dir: " << w.server.target_dir << "\n";
      f << "cache_path: " << w.server.cache_path << "\n";
    }
  }

  WorkdirConfig *find(const std::string &dir) {
    for (auto &w : workdirs)
      if (dir.rfind(w.workdir, 0) == 0)
        return &w;
    return nullptr;
  }

  WorkdirConfig *find_exact(const std::string &dir) {
    for (auto &w : workdirs)
      if (w.workdir == dir)
        return &w;
    return nullptr;
  }
};