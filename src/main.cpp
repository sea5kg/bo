// bo.cpp
// Аналог утилиты "bo" на C++17
// Компиляция: g++ -std=c++17 -O2 -pthread bo.cpp -o bo -lssl -lcrypto

#ifdef _WIN32
#include <tchar.h>
#endif

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <sys/stat.h>

#include "bo/bo_client_socket_protocol.h"
#include "bo/bo_utils.h"
#include "bo/bo_server.h"


namespace fs = std::filesystem;

constexpr const char *VERSION = "v0.0.2";
constexpr size_t BUF_READ_SIZE = 65536;
constexpr size_t SEND_BUFFER = 512;
constexpr int DEFAULT_PORT = 4319;

std::vector<std::string> get_all_files(const fs::path &startdir) {
  std::vector<std::string> result;
  for (auto it = fs::recursive_directory_iterator(
           startdir, fs::directory_options::skip_permission_denied);
       it != fs::recursive_directory_iterator(); ++it) {
    const auto &p = it->path();
    if (it->is_directory() && p.filename() == ".git") {
      it.disable_recursion_pending();
      continue;
    }
    if (it->is_regular_file()) {
      result.push_back(fs::relative(p, startdir).generic_string());
    }
  }
  return result;
}

struct FileInfo {
  std::string required_sync = "NONE"; // NONE / UPDATE / DELETE
  std::string md5;
  long long size = 0;
  long long last_modify = 0;
  int version = 0;
};

class FilesCache {
public:
  FilesCache(const std::string &cache_path)
      : cache_path_(cache_path),
        cache_path_to_update_(cache_path.substr(0, cache_path.size() - 4) +
                              "_to_update.yml") {
    load();
  }

  bool has(const std::string &file) const { return files_.count(file) > 0; }

  void add(const std::string &file, const fs::path &fullpath) {
    FileInfo info;
    info.required_sync = "UPDATE";
    info.md5 = bo::md5_by_file(fullpath.string());
    info.size = static_cast<long long>(fs::file_size(fullpath));
    auto ftime = fs::last_write_time(fullpath);
    info.last_modify =
        static_cast<long long>(std::chrono::duration_cast<std::chrono::seconds>(
                                   ftime.time_since_epoch())
                                   .count());
    files_[file] = info;
  }

  void update(const std::string &file, const std::string &sync) {
    auto &info = files_[file];
    if (!sync.empty())
      info.required_sync = sync;
    info.version++;
  }

  void remove(const std::string &file) { files_.erase(file); }

  const std::map<std::string, FileInfo> &files() const { return files_; }
  std::map<std::string, FileInfo> &files() { return files_; }

  std::string cache_path() const { return cache_path_; }
  std::string cache_path_to_update() const { return cache_path_to_update_; }

  int number_of_files_to_update() const {
    int n = 0;
    for (const auto &[_, i] : files_)
      if (i.required_sync != "NONE")
        ++n;
    return n;
  }

  void rescan(const fs::path &workdir, bool force_update) {
    std::cout << "Scanning files...\n";
    auto start = std::chrono::steady_clock::now();

    auto current = get_all_files(workdir);
    std::map<std::string, bool> current_set;
    for (const auto &f : current)
      current_set[f] = true;

    int changes = 0;
    for (const auto &rel : current) {
      fs::path full = workdir / rel;
      if (!has(rel)) {
        add(rel, full);
        ++changes;
      } else {
        auto &info = files_[rel];
        auto mtime = static_cast<long long>(
            std::chrono::duration_cast<std::chrono::seconds>(
                fs::last_write_time(full).time_since_epoch())
                .count());
        if (mtime != info.last_modify) {
          info.required_sync = "UPDATE";
          info.md5 = bo::md5_by_file(full.string());
          info.size = static_cast<long long>(fs::file_size(full));
          info.last_modify = mtime;
          ++changes;
        }
        if (force_update) {
          info.required_sync = "UPDATE";
          ++changes;
        }
      }
    }
    for (auto &[file, info] : files_) {
      if (!current_set.count(file)) {
        info.required_sync = "DELETE";
        ++changes;
      }
    }

    auto end = std::chrono::steady_clock::now();
    double sec = std::chrono::duration<double>(end - start).count();
    std::cout << "Done. Found all files: " << current.size()
              << ". Changes: " << changes << ", Elapsed " << sec << " sec\n";
  }

  void save() {
    write_file(cache_path_, false);
    write_file(cache_path_to_update_, true);
  }

private:
  std::map<std::string, FileInfo> files_;
  std::string cache_path_;
  std::string cache_path_to_update_;

  // Простейший формат: file|required_sync|md5|size|last_modify
  void load() {
    std::ifstream f(cache_path_);
    if (!f)
      return;
    std::string line;
    while (std::getline(f, line)) {
      if (line.empty())
        continue;
      std::istringstream ss(line);
      std::string file, sync, md5, size, lm;
      std::getline(ss, file, '|');
      std::getline(ss, sync, '|');
      std::getline(ss, md5, '|');
      std::getline(ss, size, '|');
      std::getline(ss, lm, '|');
      FileInfo info;
      info.required_sync = sync.empty() ? "NONE" : sync;
      info.md5 = md5;
      info.size = size.empty() ? 0 : std::stoll(size);
      info.last_modify = lm.empty() ? 0 : std::stoll(lm);
      files_[file] = info;
    }
  }

  void write_file(const std::string &path, bool only_updates) {
    std::ofstream f(path);
    if (!f)
      return;
    for (const auto &[file, info] : files_) {
      if (only_updates && info.required_sync == "NONE")
        continue;
      f << file << '|' << info.required_sync << '|' << info.md5 << '|'
        << info.size << '|' << info.last_modify << '\n';
    }
  }
};

class BoClientSocketHandler {
public:
  BoClientSocketHandler(const std::string &host, int port,
                        const std::string &target_dir)
      : host_(host), port_(port), target_dir_(target_dir) {}

  void run_sync(FilesCache &cache) {
    std::string cache_md5 = bo::md5_by_file(cache.cache_path_to_update());
    long long cache_size =
        static_cast<long long>(fs::file_size(cache.cache_path_to_update()));

    BoClientSocketProtocol proto(host_, port_, 15);
    proto.send_param("TARGET_DIR", target_dir_);
    proto.send_param("CACHE_MD5", cache_md5);
    proto.send_param("CACHE_SIZE", std::to_string(cache_size));
    proto.send_param("SEND_BUFFER_SIZE", std::to_string(SEND_BUFFER));
    proto.send_param("CACHE_SEND", "1");
    proto.send_file(cache.cache_path_to_update());

    auto start = std::chrono::steady_clock::now();
    int synced = 0;
    int total = cache.number_of_files_to_update();
    auto print_stats = [&](int done, int all) {
      double sec = std::chrono::duration<double>(
                       std::chrono::steady_clock::now() - start)
                       .count();
      double remaining =
          (done > 0 && all > done) ? (all - done) / (done / sec) : 0.0;
      std::cout << "Updated " << done << "/" << all << " at " << sec
                << " sec. Remaining: " << remaining << " sec\n";
    };

    while (true) {
      std::string action = proto.action_request();
      if (action == "ACTIONS_COMPLETED")
        break;
      if (action.rfind("ACTION_DELETED ", 0) == 0) {
        std::string file = action.substr(15);
        cache.remove(file);
        ++synced;
        print_stats(synced, total);
        if (synced % 100 == 0)
          cache.save();
      } else if (action.rfind("ACTION_SEND_ME_FILE ", 0) == 0) {
        std::string file = action.substr(19);
        std::string full = (fs::path(workdir_) / file).string();
        proto.send_file(full);
        cache.update(file, "NONE");
        ++synced;
        print_stats(synced, total);
        if (synced % 100 == 0)
          cache.save();
      } else {
        std::cout << "ERROR UNKNOWN ACTION -> " << action << "\n";
      }
    }
    print_stats(synced, total);
    cache.save();
  }

  void run_command(const std::string &subdir,
                   const std::vector<std::string> &commands) {
    BoClientSocketProtocol proto(host_, port_, -1);
    proto.send_param("TARGET_DIR", target_dir_);
    proto.send_param("SUB_DIR", subdir);

    std::string json = "[";
    for (size_t i = 0; i < commands.size(); ++i) {
      json += "\"" + commands[i] + "\"";
      if (i + 1 < commands.size())
        json += ",";
    }
    json += "]";
    proto.send_param("RUN_COMMAND", json);

    while (proto.output_request()) {
    }
  }

  void set_workdir(const std::string &w) { workdir_ = w; }

private:
  std::string host_;
  int port_;
  std::string target_dir_;
  std::string workdir_;
};

struct ServerConfig {
  std::string host = "127.0.0.1";
  int port = DEFAULT_PORT;
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
  std::string home_dir;
  std::vector<WorkdirConfig> workdirs;

  void init() {
    const char *home = std::getenv("HOME");
    home_dir = std::string(home ? home : ".") + "/.bo-by-sea5kg";
    fs::create_directories(home_dir);
    config_path = home_dir + "/config.yml";
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

// ---------------------------------------------------------------
// Точка входа
// ---------------------------------------------------------------
static void print_help() {
  std::cout << "Usage:\n"
               "    'bo config init' - add current directory to config\n"
               "    'bo config info' - print info about current directory\n"
               "    'bo config deinit' - remove current directory from config\n"
               "    'bo config command' - Init command for current directory\n"
               "    'bo config remove-command <cmd_name>' - remove command\n"
               "    'bo config ls' - print configs\n"
               "    'bo config path' - path to config file\n"
               "    'bo sync' - partial sync to remote server\n"
               "    'bo sync -f' - force sync all files to remote server\n"
               "    'bo remote run <cmd> <arg1> ... <argN>' - call command on "
               "remote host\n"
               "    'bo server' - start server\n\n";
}

int main(int argc, char **argv) {
  std::cout
      << "Welcome to bo (" << VERSION << ") c++ version!\n"
      << "Utility for sync files (like rsync) and "
         "run build on remote server (or Virtual Machine in local network).\n";

  bo::init_win_sockets _init_win_sockets_;

  BoConfig config;
  config.init();

  fs::path current_dir = fs::current_path();
  std::string cur = current_dir.string();
  WorkdirConfig *wd = config.find(cur);

  std::vector<std::string> args(argv + 1, argv + argc);

  auto has_arg = [&](std::initializer_list<const char *> names) {
    for (auto &a : args)
      for (auto n : names)
        if (a == n)
          return true;
    return false;
  };

  if (has_arg({"help", "/?", "-h", "--help"}) || args.empty()) {
    print_help();
    return 0;
  }

  if (args[0] == "config") {
    if (args.size() < 2) {
      print_help();
      return 0;
    }
    const std::string &sub = args[1];

    if (sub == "init") {
      if (config.find_exact(cur))
        bo::fatal(4, "Already initialized directory: " + cur);
      std::string server, target;
      std::cout << "Server: ";
      std::getline(std::cin, server);
      std::cout << "Target dir: ";
      std::getline(std::cin, target);
      WorkdirConfig w;
      w.workdir = cur;
      w.server.host = bo::trim(server);
      w.server.port = DEFAULT_PORT;
      w.server.target_dir = bo::trim(target);
      std::string hash_src =
          cur + "|" + w.server.target_dir + "|" + w.server.host;
      w.server.cache_path =
          config.home_dir + "/" + bo::md5_by_string(hash_src) + ".yml";
      config.workdirs.push_back(w);
      config.save();
      std::cout << "Done.\n";
    } else if (sub == "deinit") {
      if (!wd)
        bo::fatal(5, "Not found initialize directory: " + cur);
      for (size_t i = 0; i < config.workdirs.size(); ++i)
        if (config.workdirs[i].workdir == wd->workdir) {
          config.workdirs.erase(config.workdirs.begin() + i);
          break;
        }
      config.save();
      std::cout << "Done.\n";
    } else if (sub == "ls") {
      for (const auto &w : config.workdirs) {
        std::cout << "Dir: " << w.workdir << "\n";
        std::cout << "  -> Server 'base'\n";
        std::cout << "     - Host: " << w.server.host << "\n";
        std::cout << "     - Target Directory: " << w.server.target_dir << "\n";
        std::cout << "     - Cache: " << w.server.cache_path << "\n";
      }
      std::cout << "\n";
    } else if (sub == "path") {
      std::cout << "BO_CONFIG_FILEPATH: " << config.config_path << "\n";
    } else if (sub == "info") {
      if (!wd)
        bo::fatal(4, "Not initialized current directory: " + cur);
      std::cout << "\nWorkdir: " << wd->workdir << "\n";
      std::cout << "Target host: " << wd->server.host << ":" << wd->server.port
                << "\n";
      std::cout << "Target directory: " << wd->server.target_dir << "\n";
      std::cout << "Cache Files Info: " << wd->server.cache_path << "\n\n";
    } else {
      print_help();
      bo::fatal(3, "Unknown sub command '" + sub + "'");
    }
    return 0;
  }

  if (args[0] == "sync") {
    if (!wd)
      bo::fatal(6, "Not found config for directory: " + cur);
    bool force = has_arg({"-f", "--force"});
    std::cout << "Start syncing files\n    >from: " << wd->workdir
              << "\n    >to: " << wd->server.host << ":" << wd->server.port
              << "\n";

    FilesCache cache(wd->server.cache_path);
    cache.rescan(wd->workdir, force);
    cache.save();

    BoClientSocketHandler handler(wd->server.host, wd->server.port,
                                  wd->server.target_dir);
    handler.set_workdir(wd->workdir);
    handler.run_sync(cache);
    return 0;
  }

  if (args[0] == "server") {
    bo::BoServer server("0.0.0.0", DEFAULT_PORT);
    server.start();
    return 0;
  }

  if (args[0] == "remote") {
    if (!wd)
      bo::fatal(6, "Not found config for directory: " + cur);
    if (args.size() < 3)
      bo::fatal(10, "Usage: bo remote run <cmd> ...");
    if (args[1] == "run") {
      std::cout << "Run command on remote host " << wd->server.host << ":"
                << wd->server.port << "\n";
      std::string subdir = cur.substr(wd->workdir.size() + 1);
      std::vector<std::string> cmds(args.begin() + 2, args.end());

      BoClientSocketHandler handler(wd->server.host, wd->server.port,
                                    wd->server.target_dir);
      handler.run_command(subdir, cmds);
      return 0;
    }
    bo::fatal(11, "Unknown remote subcommand '" + args[1] + "'");
  }

  if (wd && wd->commands.count(args[0])) {
    for (const auto &cmd : wd->commands[args[0]]) {
      auto pos = cmd.find(':');
      if (pos == std::string::npos)
        bo::fatal(701, "Expected '<target>: ...' in command");
      std::string target = bo::trim(cmd.substr(0, pos));
      std::string value = bo::trim(cmd.substr(pos + 1));

      if (target == "local") {
        std::cout << "local> " << value << "\n";
        if (std::system(value.c_str()) != 0)
          bo::fatal(702, "Local command failed: " + value);
      } else if (target == "remote-run") {
        std::cout << "remote-run (" << wd->server.host << ":" << wd->server.port
                  << ")> " << value << "\n";
        std::string subdir = cur.substr(wd->workdir.size() + 1);
        BoClientSocketHandler handler(wd->server.host, wd->server.port,
                                      wd->server.target_dir);
        handler.run_command(subdir, {value});
      } else {
        bo::fatal(701, "Unexpected target '" + target + "' in command");
      }
    }
    return 0;
  }

  print_help();
  bo::fatal(104, "Could not understand please call 'bo help'");
}