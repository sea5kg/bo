#include "bo_server.h"

#include <iostream>
#include <thread>

namespace bo {

namespace {
constexpr const char* VERSION = "v0.0.2";
}

BoServer::BoServer(const std::string& host, int port)
    : host_(host), port_(port) {}

void BoServer::start() {
#ifdef _WIN32
    SOCKET srv = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (srv == INVALID_SOCKET)
        fatal(20, "Socket creation failed");
#else
    int srv = ::socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0)
        fatal(20, "Socket creation failed");
#endif

    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR,
               reinterpret_cast<const char*>(&opt), sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(static_cast<uint16_t>(port_));

    if (::bind(srv, reinterpret_cast<sockaddr*>(&addr), sizeof(addr))
#ifdef _WIN32
        == SOCKET_ERROR
#else
        < 0
#endif
    ) {
        fatal(20, "Bind failed");
    }

    if (::listen(srv, 10)
#ifdef _WIN32
        == SOCKET_ERROR
#else
        < 0
#endif
    ) {
        fatal(21, "Listen failed");
    }

    std::cout << "Start service listening " << host_ << ":" << port_ << "\n";

    while (true) {
        sockaddr_in cli{};
        socklen_t len = sizeof(cli);

#ifdef _WIN32
        SOCKET cli_sock = ::accept(srv, reinterpret_cast<sockaddr*>(&cli), &len);
        if (cli_sock == INVALID_SOCKET)
            continue;
#else
        int cli_sock = ::accept(srv, reinterpret_cast<sockaddr*>(&cli), &len);
        if (cli_sock < 0)
            continue;
#endif

        std::thread([cli_sock] { handle_client(cli_sock); }).detach();
    }
}

void BoServer::handle_client(
#ifdef _WIN32
    SOCKET sock
#else
    int sock
#endif
) {
    std::string welcome =
        std::string("Welcome to bo server (") + VERSION + ")\nTARGET_DIR? ";
    ::send(sock, welcome.data(), static_cast<int>(welcome.size()), 0);

    char buf[1024];
    while (true) {
        int n = ::recv(sock, buf, static_cast<int>(sizeof(buf) - 1), 0);
        if (n <= 0)
            break;
        buf[n] = '\0';
        std::string line = trim(buf);

        if (line.rfind("TARGET_DIR ", 0) == 0) {
            ::send(sock, "ACCEPTED", 8, 0);
        } else if (line == "ACTION_REQUEST") {
            ::send(sock, "ACTIONS_COMPLETED", 17, 0);
        } else {
            ::send(sock, "ACCEPTED", 8, 0);
        }
    }
    CLOSE_SOCKET(sock);
}

} // namespace bo