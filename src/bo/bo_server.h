#pragma once

#include <string>

#include "bo_utils.h"

namespace bo {

class BoServer {
public:
    BoServer(const std::string& host, int port);

    void start();

private:
    std::string host_;
    int         port_;

    static void handle_client(
#ifdef _WIN32
        SOCKET sock
#else
        int sock
#endif
    );
};

} // namespace bo