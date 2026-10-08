#pragma once

#include <string>

class BoClientSocketProtocol {
public:
  BoClientSocketProtocol(const std::string &host, int port, int timeout = 15);
  ~BoClientSocketProtocol();

  BoClientSocketProtocol(const BoClientSocketProtocol &) = delete;
  BoClientSocketProtocol &operator=(const BoClientSocketProtocol &) = delete;

  BoClientSocketProtocol(BoClientSocketProtocol &&other) noexcept;
  BoClientSocketProtocol &operator=(BoClientSocketProtocol &&other) noexcept;

  void send_param(const std::string &name, const std::string &value);
  std::string action_request();
  bool output_request();
  void send_file(const std::string &filepath);

private:
  std::string host_;
  int port_;
  int timeout_;
  int sock_ = -1;
};