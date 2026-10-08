cmake_minimum_required(VERSION 3.18)

project(bo)

# include(${CMAKE_CURRENT_SOURCE_DIR}/src.wsjcpp/CMakeLists.txt)

#### BEGIN_WSJCPP_APPEND
#### END_WSJCPP_APPEND

set(CMAKE_CXX_STANDARD 17)
set(EXECUTABLE_OUTPUT_PATH ${bo_SOURCE_DIR})
# set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake/Modules/")

# Sources

# include header dirs
list (APPEND WSJCPP_INCLUDE_DIRS "src")

# main
list (APPEND WSJCPP_SOURCES "src/bo/bo_utils.cpp")
list (APPEND WSJCPP_SOURCES "src/bo/bo_client_socket_protocol.cpp")
list (APPEND WSJCPP_SOURCES "src/main.cpp")

include_directories(${WSJCPP_INCLUDE_DIRS})

add_executable (bo ${WSJCPP_SOURCES})

target_link_libraries(bo -lpthread -lssl -lcrypto ${WSJCPP_LIBRARIES} )

install(
    TARGETS
        bo
    RUNTIME DESTINATION
        ${CMAKE_INSTALL_PREFIX}/bin
)

# enable testing functionality
enable_testing()
# add_subdirectory(src/tests)
